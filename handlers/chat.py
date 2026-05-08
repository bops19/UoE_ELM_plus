"""Streaming chat handler (/chat)."""

import json
import time

import openai
from flask import Response, stream_with_context

from model_catalog import (
    model_supports_flex_service_tier,
    model_supports_priority_service_tier,
    model_supports_reasoning_effort,
    model_uses_responses_api,
    normalize_service_tier,
)
from session_store import (
    ensure_session,
    insert_message,
    refresh_session_title,
    update_message,
)
from usage_history import token_history_scope, usage_cost
from vm_service import build_usage_view

from handler_dependencies import (
    _append_token_usage_log,
    _check_rate_limit,
    _context_message_payload,
    _current_user_content,
    _db,
    _deep_research_has_data_source,
    _deep_research_tools,
    _error_response,
    _estimate_request_input_tokens,
    _estimate_text_tokens,
    _is_computer_use_preview_model,
    _load_active_attachments,
    _normalize_deep_research_mcp_profile_id,
    _normalize_deep_research_tools_selection,
    _normalize_include_web_search,
    _now_ms,
    _openai_client,
    _prepare_context,
    _preview_for_log,
    _reasoning_stage_line,
    _request_id,
    _security_log,
    _system_prompt,
    _usage_payload,
    _validated_json_body,
    divider,
    log,
)


def chat():
    limited = _check_rate_limit("chat")
    if limited:
        return limited
    data, err = _validated_json_body(
        allowed_keys={
            "sessionId",
            "userText",
            "effort",
            "model",
            "useCase",
            "activeAttachmentIds",
            "includeWebSearch",
            "deepResearchTools",
            "deepResearchMcpProfileId",
            "serviceTier",
        },
        required_keys={"sessionId", "userText"},
    )
    if err:
        return err
    session_id = data.get("sessionId")
    user_text = (data.get("userText") or "").strip()
    effort = data.get("effort")
    model = data.get("model", "gpt-4o")
    use_case = data.get("useCase", "general")
    active_attachment_ids = data.get("activeAttachmentIds") or []
    deep_tools_selection, deep_tools_selection_error = _normalize_deep_research_tools_selection(data.get("deepResearchTools"))
    if deep_tools_selection_error:
        return _error_response(deep_tools_selection_error, 400, "deep_research_tools_invalid")
    deep_mcp_profile_id, deep_mcp_profile_error = _normalize_deep_research_mcp_profile_id(data.get("deepResearchMcpProfileId"))
    if deep_mcp_profile_error:
        return _error_response(deep_mcp_profile_error, 400, "deep_research_mcp_profile_invalid")
    include_web_search, include_web_search_error = _normalize_include_web_search(data.get("includeWebSearch"))
    if include_web_search_error:
        return _error_response(include_web_search_error, 400, "include_web_search_invalid")
    raw_service_tier = str(data.get("serviceTier") or "").strip().lower()
    service_tier = None
    if raw_service_tier:
        normalized_service_tier = normalize_service_tier(raw_service_tier)
        if normalized_service_tier != raw_service_tier:
            return _error_response(
                "serviceTier must be one of: 'default', 'flex', 'priority'.",
                400,
                "service_tier_invalid",
            )
        if raw_service_tier == "priority" and not model_supports_priority_service_tier(model):
            return _error_response(
                f"serviceTier='priority' is not supported for model '{model}'.",
                400,
                "service_tier_model_not_supported",
            )
        if raw_service_tier == "flex" and not model_supports_flex_service_tier(model):
            return _error_response(
                f"serviceTier='flex' is not supported for model '{model}'.",
                400,
                "service_tier_model_not_supported",
            )
        service_tier = raw_service_tier
    if include_web_search and use_case not in {"general", "reasoning"}:
        return _error_response(
            "includeWebSearch is supported only for general and reasoning use cases.",
            400,
            "include_web_search_use_case_invalid",
        )
    if use_case == "computer" and _is_computer_use_preview_model(model):
        return _error_response(
            "Legacy computer-use-preview requires the dedicated /computer-runs/start route.",
            400,
            "computer_run_route_required",
            {"hint": "/computer-runs/start"},
        )
    deep_research_tools = None
    if use_case == "deep":
        deep_research_tools, unavailable_tools, profile_error = _deep_research_tools(
            deep_tools_selection,
            deep_mcp_profile_id,
        )
        if profile_error:
            return _error_response(profile_error, 400, "deep_research_mcp_profile_invalid")
        if unavailable_tools:
            return _error_response(
                "One or more selected deep research tools are not configured on the server.",
                400,
                "deep_research_tool_not_configured",
                {
                    "unavailableTools": unavailable_tools,
                    "hint": "Configure server env vars or disable unavailable tools in the Deep Research tab.",
                },
            )
        if not _deep_research_has_data_source(deep_research_tools):
            return _error_response(
                "Deep research requires at least one data source tool: web_search, file_search, or mcp.",
                400,
                "deep_research_data_source_required",
                {
                    "hint": "Enable Web, Files, or MCP in Deep Research tools.",
                },
            )
    use_responses_api = model_uses_responses_api(model)
    if include_web_search and not use_responses_api:
        return _error_response(
            "Web search in chat requires a model supported by the Responses API.",
            400,
            "include_web_search_model_not_supported",
            {"hint": "Choose a model routed through the Responses API for this tab."},
        )
    chat_web_tools = [{"type": "web_search"}] if include_web_search else None

    if not session_id or not user_text:
        return _error_response("missing sessionId or userText", 400, "chat_missing_required_fields")

    with _db() as conn:
        ensure_session(conn, session_id, use_case)
        user_message_id = insert_message(conn, session_id, "user", user_text, status="complete")
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

    user_content = _current_user_content(user_text, attachments, use_responses_api, attachment_budget)
    estimated_input_tokens = _estimate_request_input_tokens(
        summary_text,
        prior_messages,
        user_content,
        preset_instructions,
        preset_context,
        custom_prompt,
        custom_context,
    )
    turn = len([message for message in prior_messages if message["role"] == "user"]) + 1

    divider()
    log("💬", "NEW MESSAGE", f"(turn {turn})")
    log("🤖", "MODEL      ", model)
    log("🧠", "THINKING   ", effort or "none")
    if service_tier:
        log("⚙️ ", "SERVICE    ", service_tier)
    log("🔀", "API ROUTE  ", "Responses API" if use_responses_api else "Chat Completions")
    if use_case == "deep" and deep_research_tools:
        log(
            "🛠️ ",
            "TOOLS      ",
            "deep research tools: " + ", ".join(
                str(tool.get("type") or "").strip() or "unknown"
                for tool in deep_research_tools
            ),
        )
    elif chat_web_tools:
        log("🛠️ ", "TOOLS      ", "web search enabled")
    log("📝", "USER SAYS  ", f'"{user_text[:80]}{"..." if len(user_text) > 80 else ""}"')
    if preset_instructions:
        preset_label = preset_name or "Selected preset"
        log("🎯", "PROMPT     ", f"{preset_label}: {_preview_for_log(preset_instructions)}")
    if preset_context:
        log("📚", "PRESET CTX ", _preview_for_log(preset_context))
    if custom_prompt:
        log("✍️ ", "CHAT PROMPT", _preview_for_log(custom_prompt))
    if custom_context:
        log("🗂️ ", "CHAT CTX   ", _preview_for_log(custom_context))
    if not any([preset_instructions, preset_context, custom_prompt, custom_context]):
        log("🎯", "PROMPT     ", "none")
    log("📏", "INPUT EST. ", f"~{estimated_input_tokens} tokens")
    if attachments:
        log("📎", "FILES      ", f"{len(attachments)} active attachment(s) included")
    log("📡", "STREAMING  ", "started...")
    print("─" * 60, flush=True)
    assistant_control_payload = {
        "useCase": use_case,
        "model": model,
        "processingMode": (
            "flex" if service_tier == "flex"
            else "priority" if service_tier == "priority"
            else "standard"
        ),
        "serviceTier": service_tier or "default",
        "thinking": effort or "none",
        "includeWebSearch": include_web_search is True,
    }

    def generate():
        full_reply = ""
        chunk_count = 0
        usage = None
        stream = None
        estimated_output_tokens = 0
        last_progress_emit = 0.0
        last_reasoning_emit = 0.0
        started_at = time.monotonic()
        stream_started = False
        stage_reasoning_lines: list[str] = []
        reasoning_trace_lines: list[str] = []
        official_reasoning_summary = ""
        latest_reasoning = ""
        reasoning_status = "pending"
        reasoning_emit_interval = 0.6
        reasoning_chunk_interval = 12

        def process_event(stage: str, status: str, detail: str | None = None):
            payload = {
                "process": {
                    "stage": stage,
                    "status": status,
                }
            }
            if detail:
                payload["process"]["detail"] = detail
            return f"data: {json.dumps(payload)}\n\n"

        def reasoning_event(status: str | None = None, force=False):
            nonlocal last_reasoning_emit, latest_reasoning, reasoning_status
            now = time.monotonic()
            if not force and (now - last_reasoning_emit) < reasoning_emit_interval:
                return None
            last_reasoning_emit = now
            reasoning_status = status or ("streaming" if stream_started else "pending")
            if official_reasoning_summary.strip():
                latest_reasoning = official_reasoning_summary.strip()
            elif reasoning_trace_lines:
                latest_reasoning = "\n".join(reasoning_trace_lines[-6:])
            payload = {
                "reasoning": {
                    "summary": latest_reasoning or "Live reasoning will appear here as the draft takes shape.",
                    "status": reasoning_status,
                }
            }
            return f"data: {json.dumps(payload)}\n\n"

        def push_reasoning_line(stage: str, status: str, detail: str | None = None, force=False):
            line = _reasoning_stage_line(stage, status, detail)
            if not stage_reasoning_lines or stage_reasoning_lines[-1] != line:
                stage_reasoning_lines.append(line)
            return reasoning_event(force=force)

        def push_fallback_reasoning_trace(force=False):
            nonlocal latest_reasoning
            snapshot = full_reply.strip()
            if not snapshot:
                return None
            recent_line = snapshot.splitlines()[-1][:180]
            line = f"- Refining latest draft segment: \"{recent_line}\""
            if not reasoning_trace_lines or reasoning_trace_lines[-1] != line:
                reasoning_trace_lines.append(line)
                latest_reasoning = "\n".join(reasoning_trace_lines[-6:])
            return reasoning_event(status="streaming", force=force)

        def progress_event(force=False):
            nonlocal last_progress_emit, estimated_output_tokens
            now = time.monotonic()
            if not force and (now - last_progress_emit) < 0.5:
                return None
            last_progress_emit = now
            payload = {
                "progress": {
                    "input": estimated_input_tokens,
                    "output": estimated_output_tokens,
                    "total": estimated_input_tokens + estimated_output_tokens,
                    "estimated": True,
                }
            }
            return f"data: {json.dumps(payload)}\n\n"

        try:
            yield process_event("context_build", "done", "Context prepared")
            reasoning_update = push_reasoning_line("context_build", "done", "Context prepared", force=True)
            if reasoning_update:
                yield reasoning_update
            yield process_event(
                "attachment_prep",
                "done" if attachments else "done",
                f"{len(attachments)} active attachment(s)" if attachments else "No active attachments",
            )
            reasoning_update = push_reasoning_line(
                "attachment_prep",
                "done",
                f"{len(attachments)} active attachment(s)" if attachments else "No active attachments",
                force=True,
            )
            if reasoning_update:
                yield reasoning_update
            yield process_event("model_generating", "active", "Generating first tokens")
            reasoning_update = push_reasoning_line("model_generating", "active", "Generating first tokens", force=True)
            if reasoning_update:
                yield reasoning_update
            initial_progress = progress_event(force=True)
            if initial_progress:
                yield initial_progress

            if use_responses_api:
                input_messages = [_context_message_payload(message) for message in prior_messages]
                input_messages.append({"role": "user", "content": user_content})
                reasoning_config = {"summary": "detailed"}
                if effort:
                    reasoning_config["effort"] = effort
                    log("🧪", "REASONING  ", f"effort={effort} applied")
                kwargs = {
                    "model": model,
                    "input": input_messages,
                    "instructions": _system_prompt(summary_text, preset_instructions, preset_context, custom_prompt, custom_context),
                    "stream": True,
                    "store": False,
                    "reasoning": reasoning_config,
                }
                if use_case == "deep" and deep_research_tools:
                    kwargs["tools"] = deep_research_tools
                elif chat_web_tools:
                    kwargs["tools"] = chat_web_tools
                if service_tier:
                    kwargs["service_tier"] = service_tier

                stream = _openai_client().responses.create(**kwargs)
                for event in stream:
                    if event.type == "response.output_text.delta":
                        if not stream_started:
                            stream_started = True
                            yield process_event("model_generating", "done", "First token received")
                            yield process_event("streaming_response", "active", "Streaming response")
                            reasoning_update = push_reasoning_line("model_generating", "done", "First token received", force=True)
                            if reasoning_update:
                                yield reasoning_update
                            reasoning_update = push_reasoning_line("streaming_response", "active", "Streaming response", force=True)
                            if reasoning_update:
                                yield reasoning_update
                        chunk = event.delta
                        full_reply += chunk
                        chunk_count += 1
                        yield f"data: {json.dumps({'content': chunk})}\n\n"
                        estimated_output_tokens = max(estimated_output_tokens, _estimate_text_tokens(full_reply))
                        progress = progress_event()
                        if progress:
                            yield progress
                    elif event.type == "response.reasoning_summary_text.delta":
                        delta = getattr(event, "delta", "") or ""
                        if delta:
                            official_reasoning_summary += delta
                            latest_reasoning = official_reasoning_summary.strip()
                            reasoning_update = reasoning_event(status="streaming", force=True)
                            if reasoning_update:
                                yield reasoning_update
                    elif event.type == "response.completed":
                        usage = event.response.usage
            else:
                messages = [{"role": "system", "content": _system_prompt(summary_text, preset_instructions, preset_context, custom_prompt, custom_context)}]
                messages.extend(_context_message_payload(message) for message in prior_messages)
                messages.append({"role": "user", "content": user_content})
                kwargs = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                }
                if model_supports_reasoning_effort(model) and effort:
                    kwargs["reasoning_effort"] = effort
                    log("🧪", "REASONING  ", f"effort={effort} applied")
                elif model_supports_reasoning_effort(model):
                    log("🧪", "REASONING  ", "disabled (none selected)")
                else:
                    log("⚠️ ", "REASONING  ", f"not supported for {model}, skipping")
                if service_tier:
                    kwargs["service_tier"] = service_tier

                stream = _openai_client().chat.completions.create(**kwargs)
                for chunk in stream:
                    if chunk.usage:
                        usage = chunk.usage
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta
                    if delta.content:
                        if not stream_started:
                            stream_started = True
                            yield process_event("model_generating", "done", "First token received")
                            yield process_event("streaming_response", "active", "Streaming response")
                            reasoning_update = push_reasoning_line("model_generating", "done", "First token received", force=True)
                            if reasoning_update:
                                yield reasoning_update
                            reasoning_update = push_reasoning_line("streaming_response", "active", "Streaming response", force=True)
                            if reasoning_update:
                                yield reasoning_update
                        full_reply += delta.content
                        chunk_count += 1
                        yield f"data: {json.dumps({'content': delta.content})}\n\n"
                        estimated_output_tokens = max(estimated_output_tokens, _estimate_text_tokens(full_reply))
                        progress = progress_event()
                        if progress:
                            yield progress
                        if chunk_count % reasoning_chunk_interval == 0:
                            reasoning_update = push_fallback_reasoning_trace(force=(chunk_count <= 2))
                            if reasoning_update:
                                yield reasoning_update

            estimated_output_tokens = max(estimated_output_tokens, _estimate_text_tokens(full_reply))
            final_progress = progress_event(force=True)
            if final_progress:
                yield final_progress
            yield process_event("streaming_response", "done", "Streaming complete")
            reasoning_update = push_reasoning_line("streaming_response", "done", "Streaming complete", force=True)
            if reasoning_update:
                yield reasoning_update
            yield process_event("finalizing_usage", "active", "Saving response + usage")
            reasoning_update = push_reasoning_line("finalizing_usage", "active", "Saving response + usage", force=True)
            if reasoning_update:
                yield reasoning_update

            usage_data = _usage_payload(usage, responses_api=use_responses_api) if usage else None
            response_cost = usage_cost(usage_data, model, service_tier=service_tier) if usage_data else None
            elapsed_sec = max(0.0, time.monotonic() - started_at)
            reasoning_summary = official_reasoning_summary.strip() or latest_reasoning or "\n".join(reasoning_trace_lines[-6:]) or "Reasoning trace unavailable for this turn."
            reasoning_status = "complete" if reasoning_summary else "unavailable"
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content=full_reply,
                    payload={"control": assistant_control_payload},
                    usage=usage_data,
                    usage_model=model,
                    usage_cost=response_cost,
                    elapsed_sec=elapsed_sec,
                    reasoning_summary=reasoning_summary,
                    reasoning_status=reasoning_status,
                    status="complete",
                )
                conn.commit()
                active_session_usage = token_history_scope(conn, session_id=session_id)

            if usage_data and response_cost is not None:
                _append_token_usage_log({
                    "timestamp": _now_ms(),
                    "sessionId": session_id,
                    "assistantMessageId": assistant_message_id,
                    "useCase": use_case,
                    "model": model,
                    "usage": usage_data,
                    "cost": response_cost,
                    "elapsedSec": elapsed_sec,
                })
            with _db() as conn:
                usage_view = build_usage_view(conn, session_id=session_id, voice_mode="")

            yield process_event("finalizing_usage", "done", "Response saved")
            reasoning_update = push_reasoning_line("finalizing_usage", "done", "Response saved", force=True)
            if reasoning_update:
                yield reasoning_update
            yield process_event("completed", "done", "Response ready")
            reasoning_update = push_reasoning_line("completed", "done", "Response ready", force=True)
            if reasoning_update:
                yield reasoning_update
            yield f"data: {json.dumps({'reasoning': {'summary': reasoning_summary, 'status': reasoning_status}})}\n\n"
            if usage_data:
                yield f"data: {json.dumps({'usage': usage_data})}\n\n"
                yield f"data: {json.dumps({'usageView': usage_view})}\n\n"
            yield "data: [DONE]\n\n"
            divider()
            log("✅", "DONE       ", f"{chunk_count} chunks streamed")
            log(
                "🔢", "USAGE      ",
                f"in={usage_data['input']} out={usage_data['output']} total={usage_data['total']} reasoning={usage_data['reasoning']}"
                if usage_data else "usage=unavailable",
            )
            log("💡", "GPT SAYS   ", f'"{full_reply[:80]}{"..." if len(full_reply) > 80 else ""}"')
            print("─" * 60, flush=True)
            print(flush=True)
        except GeneratorExit:
            if stream is not None and hasattr(stream, "close"):
                try:
                    stream.close()
                except Exception:
                    pass
            elapsed_sec = max(0.0, time.monotonic() - started_at)
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content=full_reply or "[Response interrupted]",
                    elapsed_sec=elapsed_sec,
                    reasoning_summary=latest_reasoning or "Reasoning trace unavailable for interrupted response.",
                    reasoning_status="unavailable",
                    status="interrupted",
                )
                conn.commit()
            raise
        except Exception as exc:
            if stream is not None and hasattr(stream, "close"):
                try:
                    stream.close()
                except Exception:
                    pass
            elapsed_sec = max(0.0, time.monotonic() - started_at)

            is_overload = isinstance(exc, (openai.RateLimitError, openai.APIStatusError)) and (
                getattr(exc, "status_code", None) in (429, 529)
                or "too many requests" in str(exc).lower()
                or "overloaded" in str(exc).lower()
            )
            if is_overload and service_tier == "flex":
                user_message = "Flex processing is currently overloaded — please try again in a few minutes, or switch to the Default tier."
                error_code = "flex_overloaded"
            elif is_overload:
                user_message = "The API is currently overloaded — please try again in a few minutes."
                error_code = "api_overloaded"
            else:
                user_message = "Request failed. Please retry."
                error_code = "chat_generation_failed"

            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content=full_reply or f"[{user_message}]",
                    elapsed_sec=elapsed_sec,
                    reasoning_summary=latest_reasoning or "Reasoning trace unavailable because the request failed.",
                    reasoning_status="error",
                    status="error",
                )
                conn.commit()
            _security_log("CHAT ERR   ", f"{type(exc).__name__}: {str(exc)[:300]}")
            print("─" * 60, flush=True)
            yield process_event("completed", "error", "Request failed")
            yield f"data: {json.dumps({'error': user_message, 'errorCode': error_code, 'requestId': _request_id()})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")
