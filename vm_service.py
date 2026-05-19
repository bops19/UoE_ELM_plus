import copy
import sqlite3

from model_catalog import MODEL_METADATA, normalize_service_tier, pricing_for_model
from usage_history import build_usage_history_payload


def _format_cost(value: float | int | None) -> str:
    amount = float(value or 0.0)
    if amount == 0:
        return "$0.000000"
    if amount < 0.000001:
        return "< $0.000001"
    return f"${amount:.6f}"


def _format_price_per_million(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"${float(value):.2f} / 1M"


def _format_price_per_million_chars(value: float | int | None) -> str:
    if value is None:
        return "—"
    return f"${float(value):.2f} / 1M chars"


def _empty_usage() -> dict:
    return {"input": 0, "output": 0, "total": 0, "reasoning": 0}


def _merge_usage(first: dict | None, second: dict | None) -> dict | None:
    if not first and not second:
        return None
    totals = _empty_usage()
    for usage in (first or {}, second or {}):
        totals["input"] += int(usage.get("input") or 0)
        totals["output"] += int(usage.get("output") or 0)
        totals["total"] += int(usage.get("total") or 0) or (
            int(usage.get("input") or 0) + int(usage.get("output") or 0)
        )
        totals["reasoning"] += int(usage.get("reasoning") or 0)
    totals["total"] = max(totals["total"], totals["input"] + totals["output"])
    return totals


def _resolve_model_meta(model: str | None) -> dict | None:
    model_value = str(model or "").strip()
    if not model_value:
        return None
    direct = MODEL_METADATA.get(model_value)
    if direct:
        canonical = direct.get("canonicalModelId")
        if isinstance(canonical, str) and canonical in MODEL_METADATA:
            return MODEL_METADATA[canonical]
        return direct
    for key, meta in MODEL_METADATA.items():
        if model_value.startswith(key):
            canonical = meta.get("canonicalModelId")
            if isinstance(canonical, str) and canonical in MODEL_METADATA:
                return MODEL_METADATA[canonical]
            return meta
    return None


def _normalize_msg_type(message: dict) -> str:
    msg_type = str(message.get("msgType") or "text")
    if msg_type in {"text", "image", "audio", "embed"}:
        return msg_type
    payload = message.get("payload") if isinstance(message.get("payload"), dict) else {}
    payload_mime = str(payload.get("mime") or "")
    if isinstance(payload.get("b64"), str) and payload_mime.startswith("audio/"):
        return "audio"
    if isinstance(payload.get("b64"), str) and payload_mime.startswith("image/"):
        return "image"
    if isinstance(payload.get("dimensions"), int) and isinstance(payload.get("preview"), list):
        return "embed"
    return "text"


def _usage_scope_view(scope: dict) -> dict:
    totals = copy.deepcopy(scope.get("totals") or _empty_usage())
    totals_cost = float(totals.get("cost") or 0.0)
    totals["costDisplay"] = _format_cost(totals_cost)

    rows = []
    for row in (scope.get("rows") or []):
        next_row = dict(row)
        next_row["costDisplay"] = _format_cost(next_row.get("cost"))
        rows.append(next_row)

    return {
        "totals": totals,
        "rows": rows,
    }


def build_usage_view(conn: sqlite3.Connection, session_id: str | None, voice_mode: str | None = None) -> dict:
    payload = build_usage_history_payload(conn, session_id=session_id or None)
    active_scope = _usage_scope_view(payload.get("activeSession") or {})
    today_scope = _usage_scope_view(payload.get("today") or {})
    week_scope = _usage_scope_view(payload.get("week") or {})
    month_scope = _usage_scope_view(payload.get("month") or {})
    all_time_scope = _usage_scope_view(payload.get("allTime") or {})
    if payload.get("today", {}).get("date"):
        today_scope["date"] = payload["today"]["date"]

    last_response = {
        "usage": None,
        "cost": 0.0,
        "costDisplay": _format_cost(0.0),
        "elapsedSec": None,
        "elapsedDisplay": "",
    }

    if session_id:
        rows = conn.execute(
            """
            SELECT role, usage_json, usage_cost, elapsed_sec
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        combine_user = str(voice_mode or "").strip() in {"voice", "realtime", "turn", "audio", "transcribe", "transcription"}
        for index in range(len(rows) - 1, -1, -1):
            row = rows[index]
            if row["role"] != "assistant":
                continue
            usage = row["usage_json"]
            assistant_usage = None
            if usage:
                import json

                try:
                    assistant_usage = json.loads(usage)
                except Exception:
                    assistant_usage = None
            assistant_cost = float(row["usage_cost"] or 0.0)
            merged_usage = assistant_usage
            merged_cost = assistant_cost
            if combine_user:
                for user_index in range(index - 1, -1, -1):
                    candidate = rows[user_index]
                    if candidate["role"] == "assistant":
                        break
                    if candidate["role"] != "user":
                        continue
                    user_usage_json = candidate["usage_json"]
                    user_usage = None
                    if user_usage_json:
                        try:
                            user_usage = json.loads(user_usage_json)
                        except Exception:
                            user_usage = None
                    merged_usage = _merge_usage(user_usage, assistant_usage)
                    merged_cost = float(candidate["usage_cost"] or 0.0) + assistant_cost
                    break
            if merged_usage:
                elapsed_sec = row["elapsed_sec"]
                elapsed_value = float(elapsed_sec) if isinstance(elapsed_sec, (int, float)) else None
                last_response = {
                    "usage": merged_usage,
                    "cost": merged_cost,
                    "costDisplay": _format_cost(merged_cost),
                    "elapsedSec": elapsed_value,
                    "elapsedDisplay": f"{elapsed_value:.1f}s" if isinstance(elapsed_value, float) else "",
                }
                break

    return {
        "lastResponse": last_response,
        "activeSession": active_scope,
        "today": today_scope,
        "week": week_scope,
        "month": month_scope,
        "allTime": all_time_scope,
        "panels": {
            "chatCostDisplay": active_scope["totals"]["costDisplay"],
            "dayCostDisplay": today_scope["totals"]["costDisplay"],
            "allTimeCostDisplay": all_time_scope["totals"]["costDisplay"],
        },
    }


def build_catalog_view(
    selected_model: str | None,
    voice_mode: str | None = None,
    service_tier: str | None = None,
) -> dict:
    model = str(selected_model or "").strip()
    selected_meta = _resolve_model_meta(model)
    normalized_tier = normalize_service_tier(service_tier)
    selected_pricing = pricing_for_model(model, normalized_tier) if model else None
    input_price = (selected_pricing or {}).get("input") if selected_pricing else (selected_meta.get("inputPricePerMtok") if selected_meta else None)
    cached_input_price = (selected_pricing or {}).get("cached_input") if selected_pricing else (selected_meta.get("cachedInputPricePerMtok") if selected_meta else None)
    output_price = (selected_pricing or {}).get("output") if selected_pricing else (selected_meta.get("outputPricePerMtok") if selected_meta else None)
    speech_price = selected_meta.get("speechGenerationPricePerMchar") if selected_meta else None
    audio_input_price = (selected_pricing or {}).get("audio_input") if selected_pricing else (selected_meta.get("audioInputPricePerMtok") if selected_meta else None)
    audio_output_price = (selected_pricing or {}).get("audio_output") if selected_pricing else (selected_meta.get("audioOutputPricePerMtok") if selected_meta else None)
    if audio_input_price in (None, 0):
        audio_input_price = input_price
    if audio_output_price in (None, 0):
        audio_output_price = output_price

    transcribe_meta = _resolve_model_meta("gpt-4o-mini-transcribe")
    transcribe_input = (transcribe_meta.get("audioInputPricePerMtok") if transcribe_meta else None) or (
        transcribe_meta.get("inputPricePerMtok") if transcribe_meta else None
    )
    transcribe_output = (transcribe_meta.get("audioOutputPricePerMtok") if transcribe_meta else None) or (
        transcribe_meta.get("outputPricePerMtok") if transcribe_meta else None
    )

    mode = str(voice_mode or "").strip()
    if mode == "transcribe":
        voice_footer = (
            "This transcription model returns text without segment timestamps. Use whisper-1 for timestamped transcripts. "
            "Speaker diarization is temporarily unavailable."
        )
    elif mode == "turn":
        voice_footer = "Totals include both the turn-based audio reply and gpt-4o-mini-transcribe transcript cost."
    else:
        voice_footer = "Totals include both the realtime reply and gpt-4o-mini-transcribe transcript cost."

    tts_uses_character_pricing = isinstance(speech_price, (int, float)) and float(speech_price) > 0
    tts_footer = (
        "Static pricing only. Legacy speech models bill by generated characters and do not report turn cost live in this tab."
        if tts_uses_character_pricing
        else "Static pricing only. gpt-4o-mini-tts bills for text input and audio output, but live turn cost is not tracked in this tab."
    )

    return {
        "selectedModel": model,
        "voiceMode": mode,
        "serviceTier": normalized_tier,
        "selectedModelInputPriceStr": _format_price_per_million(input_price) if selected_meta else "—",
        "selectedModelCachedInputPriceStr": _format_price_per_million(cached_input_price) if selected_meta else "—",
        "selectedModelOutputPriceStr": _format_price_per_million(output_price) if selected_meta else "—",
        "voicePrimaryAudioInputPriceLabel": (
            "Transcribe in / 1M"
            if mode == "transcribe"
            else ("Audio model in / 1M" if mode == "turn" else "Realtime audio in / 1M")
        ),
        "voicePrimaryAudioOutputPriceLabel": (
            "Transcribe out / 1M"
            if mode == "transcribe"
            else ("Audio model out / 1M" if mode == "turn" else "Realtime audio out / 1M")
        ),
        "voicePrimaryAudioInputPriceStr": _format_price_per_million(audio_input_price) if selected_meta else "—",
        "voicePrimaryAudioOutputPriceStr": _format_price_per_million(audio_output_price) if selected_meta else "—",
        "voiceTranscriptionInputPriceStr": _format_price_per_million(transcribe_input) if transcribe_meta else "—",
        "voiceTranscriptionOutputPriceStr": _format_price_per_million(transcribe_output) if transcribe_meta else "—",
        "voicePricingFooter": voice_footer,
        "ttsUsesCharacterPricing": bool(tts_uses_character_pricing),
        "ttsSpeechGenerationPriceStr": _format_price_per_million_chars(speech_price) if tts_uses_character_pricing else "—",
        "ttsTextInputPriceStr": _format_price_per_million(input_price) if selected_meta else "—",
        "ttsAudioOutputPriceStr": _format_price_per_million(audio_output_price) if selected_meta else "—",
        "ttsPricingFooter": tts_footer,
    }


def build_session_view(detail: dict | None) -> dict | None:
    if not isinstance(detail, dict):
        return None
    messages = []
    for message in detail.get("messages") or []:
        if not isinstance(message, dict):
            continue
        next_message = dict(message)
        next_message["msgType"] = _normalize_msg_type(next_message)
        usage_cost = next_message.get("usageCost")
        next_message["usageCostDisplay"] = _format_cost(usage_cost) if isinstance(usage_cost, (int, float)) else ""
        elapsed = next_message.get("elapsedSec")
        next_message["elapsedDisplay"] = f"{float(elapsed):.1f}s" if isinstance(elapsed, (int, float)) else ""
        messages.append(next_message)

    attachments = []
    for attachment in detail.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        attachments.append(dict(attachment))

    return {
        **detail,
        "messages": messages,
        "attachments": attachments,
        "messageCount": len([item for item in messages if item.get("role") == "user"]),
        "attachmentCount": len(attachments),
    }
