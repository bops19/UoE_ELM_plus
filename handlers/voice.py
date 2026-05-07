"""Handlers for voice / audio / transcription / TTS endpoints."""

import base64
import io
import json
import time

from flask import request

from prompt_presets_store import load_prompt_presets
from prompt_session_service import normalize_session_text
from session_store import (
    ensure_session,
    insert_message,
    refresh_session_title,
    session_detail,
    update_message,
)
from transcription_utils import (
    _raw_api_response_text,
    _transcription_text,
    _transcription_to_dict,
    _transcription_value_to_python,
    _write_diarize_debug_snapshot,
    transcription_segment_payload as _transcription_segment_payload,
)
from usage_history import token_history_scope, usage_cost
from vm_service import build_session_view, build_usage_view

from handler_dependencies import (
    AUDIO_CHAT_FORMAT,
    AUDIO_CHAT_TRANSCRIBE_MODEL,
    AUDIO_CHAT_VOICE,
    OPENAI_TIMEOUT_SEC,
    PROMPT_PRESETS_FILE,
    REALTIME_DEFAULT_VOICE,
    REQUEST_BODY_MAX_BYTES,
    TTS_OUTPUT_FORMAT,
    _append_token_usage_log,
    _assistant_supported_voices,
    _audio_mime_type_for_format,
    _chat_message_text,
    _check_rate_limit,
    _combine_usage_payloads,
    _context_message_payload,
    _current_user_content,
    _db,
    _derive_title,
    _error_response,
    _load_active_attachments,
    _mint_realtime_client_secret,
    _model_supports_segment_timestamps,
    _now_ms,
    _openai_client,
    _prepare_context,
    _reject_oversized_multipart,
    _safe_get,
    _safe_openai_call,
    _security_log,
    _single_shot_interaction,
    _system_prompt,
    _transcription_prompt,
    _transcription_source_label,
    _tts_supported_voices,
    _validated_json_body,
    _voice_session_instructions,
    _voice_usage_payload,
    divider,
    log,
)


def bootstrap_voice_session(session_id):
    data, err = _validated_json_body(allowed_keys={"model", "useCase", "voice"})
    if err:
        return err
    model = (data.get("model") or "").strip()
    use_case = data.get("useCase", "voice")
    voice = normalize_session_text(data.get("voice", REALTIME_DEFAULT_VOICE)) or REALTIME_DEFAULT_VOICE
    if not model:
        return _error_response("model is required", 400, "voice_model_required")
    supported_voices = _assistant_supported_voices(model)
    if supported_voices and voice not in supported_voices:
        return _error_response(
            f"{voice} is not available for {model}. Choose one of: {', '.join(supported_voices)}.",
            400,
            "voice_invalid_voice",
        )

    try:
        with _db() as conn:
            ensure_session(conn, session_id, use_case)
            instructions = _voice_session_instructions(conn, session_id)
            conn.commit()
        secret_payload = _mint_realtime_client_secret(model, instructions, voice=voice)

    except RuntimeError:
        return _error_response("Realtime bootstrap service is unavailable.", 503, "voice_bootstrap_unavailable")
    except Exception as exc:
        _security_log("VOICE BOOT", f"{type(exc).__name__}: {str(exc)[:300]}")
        return _error_response("Could not start realtime voice session.", 502, "voice_bootstrap_failed")

    client_secret = (
        _safe_get(secret_payload, "value")
        or _safe_get(secret_payload, "client_secret", "value")
        or _safe_get(secret_payload, "clientSecret", "value")
    )
    if not client_secret:
        return _error_response("Realtime bootstrap did not return a client secret", 502, "voice_bootstrap_invalid_response")

    expires_at = (
        _safe_get(secret_payload, "expires_at")
        or _safe_get(secret_payload, "client_secret", "expires_at")
        or _safe_get(secret_payload, "clientSecret", "expiresAt")
    )
    session_type = _safe_get(secret_payload, "session", "type", default="realtime")

    return {
        "clientSecret": client_secret,
        "expiresAt": expires_at,
        "model": model,
        "voice": voice,
        "transcriptionModel": "gpt-4o-mini-transcribe",
        "sessionType": session_type,
    }


def persist_voice_turn(session_id):
    limited = _check_rate_limit("voice_turns")
    if limited:
        return limited
    data, err = _validated_json_body(
        allowed_keys={"sessionId", "userText", "assistantText", "model", "useCase", "userUsage", "assistantUsage", "userUsageModel", "elapsedSec"},
    )
    if err:
        return err
    payload_session_id = normalize_session_text(data.get("sessionId"))
    if payload_session_id and payload_session_id != session_id:
        return _error_response(
            "sessionId in payload does not match URL.",
            400,
            "voice_session_mismatch",
        )
    user_text = normalize_session_text(data.get("userText"))
    assistant_text = normalize_session_text(data.get("assistantText"))
    model = (data.get("model") or "").strip()
    use_case = data.get("useCase", "voice")
    user_usage = _voice_usage_payload(data.get("userUsage"), source="transcription")
    assistant_usage = _voice_usage_payload(data.get("assistantUsage"), source="realtime")
    user_usage_model = (data.get("userUsageModel") or "").strip()
    elapsed_sec = data.get("elapsedSec")
    try:
        elapsed_sec = float(elapsed_sec) if elapsed_sec is not None else None
    except (TypeError, ValueError):
        elapsed_sec = None

    if not user_text and not assistant_text:
        return _error_response("voice transcript text is required", 400, "voice_transcript_required")

    with _db() as conn:
        ensure_session(conn, session_id, use_case)
        if user_text:
            insert_message(
                conn,
                session_id,
                "user",
                user_text,
                msg_type="text",
                usage=user_usage,
                usage_model=user_usage_model or None,
                usage_cost=usage_cost(user_usage, user_usage_model) if user_usage and user_usage_model else None,
            )
        if assistant_text:
            assistant_cost = usage_cost(assistant_usage, model) if assistant_usage and model else None
            insert_message(
                conn,
                session_id,
                "assistant",
                assistant_text,
                msg_type="text",
                usage=assistant_usage,
                usage_model=model or None,
                usage_cost=assistant_cost,
                elapsed_sec=elapsed_sec,
            )
        refresh_session_title(conn, session_id)
        conn.commit()
        active_session_usage = token_history_scope(conn, session_id=session_id)
        detail = session_detail(conn, session_id, load_prompt_presets=lambda: load_prompt_presets(PROMPT_PRESETS_FILE))

    combined_usage = _combine_usage_payloads(user_usage, assistant_usage)
    user_cost = usage_cost(user_usage, user_usage_model) if user_usage and user_usage_model else 0.0
    assistant_cost = usage_cost(assistant_usage, model) if assistant_usage and model else 0.0
    turn_cost = user_cost + assistant_cost
    with _db() as conn:
        usage_view = build_usage_view(conn, session_id=session_id, voice_mode="realtime")

    return {
        "session": detail,
        "sessionView": build_session_view(detail),
        "usageView": usage_view,
        "usageSummary": {
            "activeSession": active_session_usage,
            "responseCost": turn_cost,
            "turnCost": turn_cost,
            "turnUsage": combined_usage,
        },
    }


def create_audio_turn(session_id):
    limited = _check_rate_limit("audio_turn")
    if limited:
        return limited
    oversized = _reject_oversized_multipart(REQUEST_BODY_MAX_BYTES)
    if oversized:
        return oversized
    uploaded_audio = request.files.get("audio")
    model = (request.form.get("model") or "gpt-audio-mini").strip()
    use_case = request.form.get("useCase", "audio")
    voice = normalize_session_text(request.form.get("voice", AUDIO_CHAT_VOICE)) or AUDIO_CHAT_VOICE
    active_attachment_ids = [value for value in request.form.getlist("activeAttachmentIds") if value]

    if not uploaded_audio:
        return _error_response("audio file is required", 400, "audio_file_required")

    audio_bytes = uploaded_audio.read()
    if not audio_bytes:
        return _error_response("audio file is empty", 400, "audio_file_empty")
    supported_voices = _assistant_supported_voices(model)
    if supported_voices and voice not in supported_voices:
        return _error_response(
            f"{voice} is not available for {model}. Choose one of: {', '.join(supported_voices)}.",
            400,
            "audio_invalid_voice",
        )

    audio_name = (uploaded_audio.filename or "turn.webm").strip() or "turn.webm"
    transcript_file = io.BytesIO(audio_bytes)
    transcript_file.name = audio_name

    assistant_message_id = None
    started_at = time.monotonic()

    try:
        transcription, openai_err = _safe_openai_call(
            lambda: _openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).audio.transcriptions.create(
                model=AUDIO_CHAT_TRANSCRIBE_MODEL,
                file=transcript_file,
                response_format="json",
            ),
            error_code="audio_transcription_failed",
            unavailable_error_code="audio_transcription_unavailable",
            label="audio.transcriptions.create",
        )
        if openai_err:
            return openai_err
        user_text = normalize_session_text(getattr(transcription, "text", None) or _safe_get(transcription, "text", default=""))
        if not user_text:
            return _error_response("Could not transcribe the audio turn", 502, "audio_transcription_empty")

        transcription_usage = _voice_usage_payload(
            getattr(transcription, "usage", None) or _safe_get(transcription, "usage", default={}),
            source="transcription",
        )
        transcription_cost = usage_cost(transcription_usage, AUDIO_CHAT_TRANSCRIBE_MODEL) if transcription_usage else None

        with _db() as conn:
            ensure_session(conn, session_id, use_case)
            user_message_id = insert_message(
                conn,
                session_id,
                "user",
                user_text,
                msg_type="text",
                usage=transcription_usage,
                usage_model=AUDIO_CHAT_TRANSCRIBE_MODEL,
                usage_cost=transcription_cost,
                status="complete",
            )
            refresh_session_title(conn, session_id)
            assistant_message_id = insert_message(conn, session_id, "assistant", "", status="pending")
            summary_text, prior_messages, attachment_budget, preset_name, preset_instructions, preset_context, custom_prompt, custom_context = _prepare_context(
                conn,
                session_id,
                user_message_id,
                model,
            )
            attachments = _load_active_attachments(conn, session_id, active_attachment_ids)
            conn.commit()

        user_content = _current_user_content(user_text, attachments, False, attachment_budget)
        messages = [{"role": "system", "content": _system_prompt(summary_text, preset_instructions, preset_context, custom_prompt, custom_context)}]
        messages.extend(_context_message_payload(message) for message in prior_messages)
        messages.append({"role": "user", "content": user_content})

        completion, openai_err = _safe_openai_call(
            lambda: _openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).chat.completions.create(
                model=model,
                messages=messages,
                modalities=["text", "audio"],
                audio={"voice": voice, "format": AUDIO_CHAT_FORMAT},
                store=False,
            ),
            error_code="audio_generation_failed",
            unavailable_error_code="audio_generation_unavailable",
            label="chat.completions.create(audio)",
        )
        if openai_err:
            return openai_err
        choice_message = completion.choices[0].message if completion.choices else None
        assistant_audio_b64 = _safe_get(choice_message, "audio", "data", default="") or ""
        assistant_text = normalize_session_text(_chat_message_text(choice_message))
        assistant_usage = _voice_usage_payload(
            getattr(completion, "usage", None) or _safe_get(completion, "usage", default={}),
            source="audio_chat",
        )
        assistant_cost = usage_cost(assistant_usage, model) if assistant_usage else None
        elapsed_sec = max(0.0, time.monotonic() - started_at)

        with _db() as conn:
            update_message(
                conn,
                assistant_message_id,
                content=assistant_text or "[Audio reply generated]",
                msg_type="text",
                usage=assistant_usage,
                usage_model=model,
                usage_cost=assistant_cost,
                elapsed_sec=elapsed_sec,
                status="complete",
            )
            conn.commit()
            active_session_usage = token_history_scope(conn, session_id=session_id)
            detail = session_detail(conn, session_id, load_prompt_presets=lambda: load_prompt_presets(PROMPT_PRESETS_FILE))

        combined_usage = _combine_usage_payloads(transcription_usage, assistant_usage)
        turn_cost = (transcription_cost or 0.0) + (assistant_cost or 0.0)

        if transcription_usage and transcription_cost is not None:
            _append_token_usage_log({
                "timestamp": _now_ms(),
                "sessionId": session_id,
                "useCase": use_case,
                "model": AUDIO_CHAT_TRANSCRIBE_MODEL,
                "usage": transcription_usage,
                "cost": transcription_cost,
                "elapsedSec": elapsed_sec,
            })
        if assistant_usage and assistant_cost is not None and assistant_message_id:
            _append_token_usage_log({
                "timestamp": _now_ms(),
                "sessionId": session_id,
                "assistantMessageId": assistant_message_id,
                "useCase": use_case,
                "model": model,
                "usage": assistant_usage,
                "cost": assistant_cost,
                "elapsedSec": elapsed_sec,
            })
        with _db() as conn:
            usage_view = build_usage_view(conn, session_id=session_id, voice_mode="turn")

        return {
            "session": detail,
            "sessionView": build_session_view(detail),
            "usageView": usage_view,
            "usageSummary": {
                "activeSession": active_session_usage,
                "responseCost": turn_cost,
                "turnCost": turn_cost,
                "turnUsage": combined_usage,
            },
            "audio": assistant_audio_b64,
            "audioMime": _audio_mime_type_for_format(AUDIO_CHAT_FORMAT),
            "voice": voice,
        }
    except Exception as exc:
        if assistant_message_id:
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content="[Request failed. Please retry.]",
                    elapsed_sec=max(0.0, time.monotonic() - started_at),
                    status="error",
                )
                conn.commit()
        _security_log("AUDIO TURN ", f"{type(exc).__name__}: {str(exc)[:300]}")
        return _error_response("Audio turn failed. Please retry.", 502, "audio_turn_failed")


def create_transcription_turn(session_id):
    limited = _check_rate_limit("transcription_turn")
    if limited:
        return limited
    oversized = _reject_oversized_multipart(REQUEST_BODY_MAX_BYTES)
    if oversized:
        return oversized
    uploaded_audio = request.files.get("audio")
    model = (request.form.get("model") or "gpt-4o-mini-transcribe").strip()
    use_case = request.form.get("useCase", "transcription")
    source_kind = (request.form.get("sourceKind") or "uploaded").strip().lower()

    if not uploaded_audio:
        return _error_response("audio file is required", 400, "transcription_audio_required")

    audio_bytes = uploaded_audio.read()
    if not audio_bytes:
        return _error_response("audio file is empty", 400, "transcription_audio_empty")

    audio_name = (uploaded_audio.filename or "transcription.webm").strip() or "transcription.webm"
    source_label = _transcription_source_label(source_kind, audio_name)
    transcript_file = io.BytesIO(audio_bytes)
    transcript_file.name = audio_name
    is_diarize_model = model.startswith("gpt-4o-transcribe-diarize")
    if is_diarize_model:
        return _error_response(
            "Speaker diarization is temporarily unavailable in this app. Use gpt-4o-transcribe or whisper-1 instead.",
            400,
            "transcription_diarize_unavailable",
        )
    timestamps_available = _model_supports_segment_timestamps(model)

    transcription_kwargs = {
        "model": model,
        "file": transcript_file,
    }
    if timestamps_available:
        transcription_kwargs["response_format"] = "verbose_json"
        transcription_kwargs["timestamp_granularities"] = ["segment"]
    elif is_diarize_model:
        transcription_kwargs["response_format"] = "diarized_json"
        transcription_kwargs["chunking_strategy"] = "auto"
    else:
        transcription_kwargs["response_format"] = "json"

    try:
        with _db() as conn:
            ensure_session(conn, session_id, use_case)
            transcription_prompt = _transcription_prompt(conn, session_id)
            conn.commit()

        if transcription_prompt and not is_diarize_model:
            transcription_kwargs["prompt"] = transcription_prompt

        raw_transcription_body = ""
        if is_diarize_model:
            raw_response, openai_err = _safe_openai_call(
                lambda: _openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).audio.transcriptions.with_raw_response.create(**transcription_kwargs),
                error_code="transcription_failed",
                unavailable_error_code="transcription_unavailable",
                label="audio.transcriptions.with_raw_response.create",
            )
            if openai_err:
                return openai_err
            raw_transcription_body = _raw_api_response_text(raw_response)
            try:
                parsed_body = json.loads(raw_transcription_body) if raw_transcription_body else {}
            except Exception:
                parsed_body = {}
            transcription_data = parsed_body if isinstance(parsed_body, dict) else {}
            transcription = transcription_data
        else:
            transcription, openai_err = _safe_openai_call(
                lambda: _openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).audio.transcriptions.create(**transcription_kwargs),
                error_code="transcription_failed",
                unavailable_error_code="transcription_unavailable",
                label="audio.transcriptions.create",
            )
            if openai_err:
                return openai_err
            transcription_data = _transcription_to_dict(transcription)

        transcription_data = _transcription_value_to_python(transcription_data)
        if not isinstance(transcription_data, dict):
            transcription_data = _transcription_to_dict(transcription)
        transcript_text = _transcription_text(transcription_data if is_diarize_model else transcription)
        if not transcript_text:
            if is_diarize_model:
                data_keys = []
                segment_keys = []
                debug_path = ""
                if isinstance(transcription_data, dict):
                    data_keys = sorted([str(key) for key in transcription_data.keys()])[:12]
                    raw_segments = transcription_data.get("segments")
                    if isinstance(raw_segments, list) and raw_segments:
                        first_segment = _transcription_to_dict(raw_segments[0]) or {}
                        if isinstance(first_segment, dict):
                            segment_keys = sorted([str(key) for key in first_segment.keys()])[:12]
                try:
                    debug_path = _write_diarize_debug_snapshot(transcription, transcription_data, raw_transcription_body)
                except Exception:
                    debug_path = ""
                keys_preview = ", ".join(data_keys) if data_keys else "none"
                segment_preview = ", ".join(segment_keys) if segment_keys else "none"
                debug_hint = f" Debug snapshot: {debug_path}." if debug_path else ""
                return {
                    "error": (
                        "Diarization completed, but no transcript text was returned in the model output. "
                        f"Top-level keys: {keys_preview}. First segment keys: {segment_preview}.{debug_hint}"
                    )
                }, 502
            return _error_response("Could not transcribe the audio input", 502, "transcription_empty")

        transcript_segments = _transcription_segment_payload(transcription) if timestamps_available else []
        timestamps_available = bool(transcript_segments)
        transcription_usage = _voice_usage_payload(
            getattr(transcription, "usage", None) or _safe_get(transcription_data, "usage", default={}) or _safe_get(transcription, "usage", default={}),
            source="transcription",
        )
        transcription_cost = usage_cost(transcription_usage, model) if transcription_usage else None

        user_payload = {
            "sourceKind": "uploaded" if source_kind == "uploaded" else "recorded",
            "sourceName": audio_name,
        }
        assistant_payload = {
            "transcriptSegments": transcript_segments,
            "hasSegmentTimestamps": timestamps_available,
            "timestampsAvailable": timestamps_available,
            "sourceKind": user_payload["sourceKind"],
            "sourceName": audio_name,
            "transcriptionModel": model,
        }

        with _db() as conn:
            ensure_session(conn, session_id, use_case)
            insert_message(
                conn,
                session_id,
                "user",
                source_label,
                msg_type="text",
                payload=user_payload,
            )
            assistant_message_id = insert_message(
                conn,
                session_id,
                "assistant",
                transcript_text,
                msg_type="text",
                payload=assistant_payload,
                usage=transcription_usage,
                usage_model=model,
                usage_cost=transcription_cost,
                status="complete",
            )
            session_row = conn.execute(
                "SELECT title FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            current_title = (session_row["title"] or "").strip() if session_row else ""
            if not current_title or current_title == "New chat":
                conn.execute(
                    "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
                    (_derive_title(transcript_text), _now_ms(), session_id),
                )
            conn.commit()
            active_session_usage = token_history_scope(conn, session_id=session_id)
            detail = session_detail(conn, session_id, load_prompt_presets=lambda: load_prompt_presets(PROMPT_PRESETS_FILE))

        if transcription_usage and transcription_cost is not None:
            _append_token_usage_log({
                "timestamp": _now_ms(),
                "sessionId": session_id,
                "assistantMessageId": assistant_message_id,
                "useCase": use_case,
                "model": model,
                "usage": transcription_usage,
                "cost": transcription_cost,
            })
        with _db() as conn:
            usage_view = build_usage_view(conn, session_id=session_id, voice_mode="transcribe")

        return {
            "session": detail,
            "sessionView": build_session_view(detail),
            "usageView": usage_view,
            "usageSummary": {
                "activeSession": active_session_usage,
                "responseCost": transcription_cost or 0.0,
                "turnCost": transcription_cost or 0.0,
                "turnUsage": transcription_usage,
            },
            "timestampsAvailable": timestamps_available,
            "sourceKind": user_payload["sourceKind"],
            "sourceName": audio_name,
        }
    except Exception as exc:
        _security_log("TRANSCRIBE ", f"{type(exc).__name__}: {str(exc)[:300]}")
        return _error_response("Transcription failed. Please retry.", 502, "transcription_failed")


def text_to_speech():
    limited = _check_rate_limit("chat")
    if limited:
        return limited
    data, err = _validated_json_body(
        allowed_keys={"sessionId", "useCase", "model", "text", "voice"},
        required_keys={"sessionId", "text"},
    )
    if err:
        return err
    session_id = data.get("sessionId")
    use_case = data.get("useCase", "tts")
    model = data.get("model", "tts-1")
    text = normalize_session_text(data.get("text", ""))
    voice = normalize_session_text(data.get("voice", "alloy")) or "alloy"
    if not text:
        return _error_response("text is required", 400, "tts_text_required")
    supported_voices = _tts_supported_voices(model)
    if supported_voices and voice not in supported_voices:
        return _error_response(
            f"{voice} is not available for {model}. Choose one of: {', '.join(supported_voices)}.",
            400,
            "tts_invalid_voice",
        )
    assistant_message_id, text = _single_shot_interaction(session_id, use_case, text)
    divider()
    log("🔊", "TTS        ", f"model={model}, voice={voice}")
    log("📝", "TEXT       ", f'"{text[:80]}{"..." if len(text) > 80 else ""}"')
    print("─" * 60, flush=True)
    try:
        response, openai_err = _safe_openai_call(
            lambda: _openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).audio.speech.create(
                model=model,
                input=text,
                voice=voice,
                response_format=TTS_OUTPUT_FORMAT,
            ),
            error_code="tts_failed",
            unavailable_error_code="tts_unavailable",
            label="audio.speech.create",
        )
        if openai_err:
            return openai_err
        audio_b64 = base64.b64encode(response.content).decode()
        audio_mime = _audio_mime_type_for_format(TTS_OUTPUT_FORMAT)
        detail = None
        if assistant_message_id:
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content="[Audio generated]",
                    msg_type="audio",
                    payload={"b64": audio_b64, "mime": audio_mime, "voice": voice, "model": model},
                    status="complete",
                )
                detail = session_detail(conn, session_id, load_prompt_presets=lambda: load_prompt_presets(PROMPT_PRESETS_FILE))
                conn.commit()
        log("✅", "TTS DONE   ", f"{len(audio_b64):,} chars b64")
        print(flush=True)
        usage_view = None
        if detail:
            with _db() as conn:
                usage_view = build_usage_view(conn, session_id=session_id, voice_mode="tts")
        return {"audio": audio_b64, "audioMime": audio_mime, "session": detail, "sessionView": build_session_view(detail), "usageView": usage_view}
    except Exception as exc:
        if assistant_message_id:
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content="[Request failed. Please retry.]",
                    status="error",
                )
                conn.commit()
        _security_log("TTS ERR    ", f"{type(exc).__name__}: {str(exc)[:300]}")
        print(flush=True)
        return _error_response("Text-to-speech failed. Please retry.", 502, "tts_failed")
