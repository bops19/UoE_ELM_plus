"""Prompt/context budgeting helpers extracted from app.py."""

import sqlite3

from model_catalog import context_window_for_model, use_case_keys
from prompt_presets_store import find_prompt_preset
from prompt_session_service import normalize_use_case, use_case_supports_prompt_setup
from session_store import session_messages_before


def estimate_text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def message_context_text(message: dict) -> str:
    content = message.get("content") or ""
    msg_type = message.get("msgType") or "text"
    if msg_type == "text":
        return content
    if msg_type == "image":
        return "[Assistant generated an image]"
    if msg_type == "audio":
        return "[Assistant generated audio]"
    if msg_type == "embed":
        payload = message.get("payload") or {}
        return f"[Embedding generated: {payload.get('dimensions', 0)} dimensions]"
    return content


def estimate_message_tokens(message: dict) -> int:
    role = message.get("role", "assistant")
    return estimate_text_tokens(f"{role}: {message_context_text(message)}")


def estimate_messages_tokens(messages: list[dict]) -> int:
    return sum(estimate_message_tokens(message) for message in messages)


def estimate_content_tokens(content) -> int:
    if isinstance(content, str):
        return estimate_text_tokens(content)
    if not isinstance(content, list):
        return 0
    total = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        text_value = block.get("text")
        if block_type in ("text", "input_text") and isinstance(text_value, str):
            total += estimate_text_tokens(text_value)
    return total


def system_prompt(
    summary_text: str,
    preset_instructions: str = "",
    preset_context: str = "",
    custom_prompt: str = "",
    custom_context: str = "",
    *,
    base_system_prompt: str,
) -> str:
    parts = [
        base_system_prompt,
        (
            "When preset instructions or chat-specific instructions are provided below, treat them as active "
            "response requirements for this chat. Follow them throughout the reply unless a higher-priority "
            "policy prevents it."
        ),
    ]
    if preset_instructions:
        parts.append(
            "Selected prompt preset instructions (apply these as the default style and behavior for every reply in this chat):\n"
            f"{preset_instructions}"
        )
    if preset_context:
        parts.append(
            "Selected prompt preset context (use this as persistent background context when it helps answer the user):\n"
            f"{preset_context}"
        )
    if custom_prompt:
        parts.append(
            "Chat-specific instructions (apply these in addition to the selected preset instructions):\n"
            f"{custom_prompt}"
        )
    if custom_context:
        parts.append(
            "Persistent chat context (treat this as background context for the conversation):\n"
            f"{custom_context}"
        )
    if summary_text:
        parts.append(
            "Conversation summary for continuity (use this for context, not as a user request):\n"
            f"{summary_text}"
        )
    if preset_instructions or preset_context or custom_prompt or custom_context:
        parts.append("Before answering, make sure the response reflects the active instructions and context above.")
    return "\n\n".join(parts)


def estimate_request_input_tokens(
    summary_text: str,
    prior_messages: list[dict],
    user_content,
    preset_instructions: str = "",
    preset_context: str = "",
    custom_prompt: str = "",
    custom_context: str = "",
    *,
    base_system_prompt: str,
) -> int:
    system_tokens = estimate_text_tokens(
        system_prompt(
            summary_text,
            preset_instructions,
            preset_context,
            custom_prompt,
            custom_context,
            base_system_prompt=base_system_prompt,
        )
    )
    history_tokens = estimate_messages_tokens(prior_messages)
    user_tokens = estimate_content_tokens(user_content)
    return max(0, system_tokens + history_tokens + user_tokens)


def context_window_for_selected_model(model: str, *, max_history_tokens: int) -> int:
    context_window = context_window_for_model(model)
    if context_window:
        return context_window
    return max_history_tokens * 5


def conversation_budget_for_model(
    model: str,
    *,
    max_history_tokens: int,
    history_context_ratio: float,
    attachment_budget_ratio: float,
) -> tuple[int, int]:
    context_window = context_window_for_selected_model(model, max_history_tokens=max_history_tokens)
    total_budget = min(max_history_tokens, max(2_000, int(context_window * history_context_ratio)))
    attachment_budget = max(1_000, int(total_budget * attachment_budget_ratio))
    conversation_budget = max(1_500, total_budget - attachment_budget)
    return conversation_budget, attachment_budget


def take_tail_that_fits(messages: list[dict], budget_tokens: int) -> list[dict]:
    if budget_tokens <= 0 or not messages:
        return []
    selected: list[dict] = []
    used = 0
    for message in reversed(messages):
        cost = estimate_message_tokens(message)
        if selected and used + cost > budget_tokens:
            break
        if not selected and cost > budget_tokens:
            selected.append(message)
            break
        selected.append(message)
        used += cost
    selected.reverse()
    return selected


def summary_prompt(existing_summary: str, older_messages: list[dict]) -> str:
    transcript = []
    for message in older_messages:
        role = "User" if message.get("role") == "user" else "Assistant"
        transcript.append(f"{role}: {message_context_text(message)}")
    transcript_text = "\n\n".join(transcript)
    return (
        "Existing rolling summary:\n"
        f"{existing_summary or '(none)'}\n\n"
        "Older transcript to fold into the summary:\n"
        f"{transcript_text}\n\n"
        "Return an updated rolling summary that preserves instructions, facts, constraints, decisions, "
        "open questions, and active tasks. Keep it concise and under about 1500 tokens."
    )


def refresh_summary(
    conn: sqlite3.Connection,
    session_id: str,
    existing_summary: str,
    older_messages: list[dict],
    *,
    openai_client_factory,
    summary_model: str,
    response_text_fn,
    now_ms_fn,
    log_fn,
) -> str:
    if not older_messages:
        return existing_summary or ""

    try:
        response = openai_client_factory().responses.create(
            model=summary_model,
            instructions=(
                "You compress conversation history into a durable working memory. "
                "Do not add facts. Keep the result concise, structured, and faithful."
            ),
            input=summary_prompt(existing_summary, older_messages),
            store=False,
        )
        summary_text = response_text_fn(response)
    except Exception as exc:
        log_fn("⚠️ ", "SUMMARY    ", f"failed: {exc}")
        return existing_summary or ""

    if not summary_text:
        return existing_summary or ""

    conn.execute(
        """
        UPDATE sessions
        SET summary = ?, summary_message_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (summary_text, older_messages[-1]["id"], now_ms_fn(), session_id),
    )
    return summary_text


def prepare_context(
    conn: sqlite3.Connection,
    session_id: str,
    current_user_id: int,
    model: str,
    *,
    prompt_presets_file: str,
    max_recent_messages: int,
    max_history_tokens: int,
    history_context_ratio: float,
    attachment_budget_ratio: float,
    summary_model: str,
    openai_client_factory,
    response_text_fn,
    now_ms_fn,
    log_fn,
):
    session_row = conn.execute(
        "SELECT summary, summary_message_id, custom_prompt, custom_context, prompt_preset_id, use_case FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    summary_text = (session_row["summary"] or "") if session_row else ""
    summary_message_id = session_row["summary_message_id"] if session_row else None
    session_use_case = normalize_use_case((session_row["use_case"] or "") if session_row else "", use_case_keys())
    if use_case_supports_prompt_setup(session_use_case):
        custom_prompt = (session_row["custom_prompt"] or "") if session_row else ""
        custom_context = (session_row["custom_context"] or "") if session_row else ""
        prompt_preset_id = (session_row["prompt_preset_id"] or "") if session_row else ""
        preset = find_prompt_preset(prompt_presets_file, prompt_preset_id)
        preset_name = (preset or {}).get("name", "")
        preset_instructions = (preset or {}).get("instructions", "")
        preset_context = (preset or {}).get("context", "")
    else:
        custom_prompt = ""
        custom_context = ""
        preset_name = ""
        preset_instructions = ""
        preset_context = ""

    all_previous = session_messages_before(conn, session_id, before_id=current_user_id)
    recent_messages = all_previous[-max_recent_messages:]
    older_messages = all_previous[:-max_recent_messages] if len(all_previous) > max_recent_messages else []
    unsummarized_older = [
        message for message in older_messages
        if not summary_message_id or message["id"] > summary_message_id
    ]

    conversation_budget, attachment_budget = conversation_budget_for_model(
        model,
        max_history_tokens=max_history_tokens,
        history_context_ratio=history_context_ratio,
        attachment_budget_ratio=attachment_budget_ratio,
    )
    if unsummarized_older and estimate_messages_tokens(unsummarized_older) > conversation_budget:
        summary_text = refresh_summary(
            conn,
            session_id,
            summary_text,
            unsummarized_older,
            openai_client_factory=openai_client_factory,
            summary_model=summary_model,
            response_text_fn=response_text_fn,
            now_ms_fn=now_ms_fn,
            log_fn=log_fn,
        )
        unsummarized_older = []

    summary_tokens = estimate_text_tokens(summary_text)
    recent_tokens = estimate_messages_tokens(recent_messages)
    remaining_budget = max(0, conversation_budget - summary_tokens - recent_tokens)
    included_older = take_tail_that_fits(unsummarized_older, remaining_budget)

    return (
        summary_text,
        included_older + recent_messages,
        attachment_budget,
        preset_name,
        preset_instructions,
        preset_context,
        custom_prompt,
        custom_context,
    )


def session_instruction_parts(conn: sqlite3.Connection, session_id: str, *, prompt_presets_file: str):
    session_row = conn.execute(
        """
        SELECT summary, custom_prompt, custom_context, prompt_preset_id, use_case
        FROM sessions
        WHERE id = ?
        """,
        (session_id,),
    ).fetchone()
    if not session_row:
        return "", "", "", "", "", ""

    summary_text = (session_row["summary"] or "").strip()
    session_use_case = normalize_use_case(session_row["use_case"] or "", use_case_keys())
    if use_case_supports_prompt_setup(session_use_case):
        custom_prompt = (session_row["custom_prompt"] or "").strip()
        custom_context = (session_row["custom_context"] or "").strip()
        prompt_preset_id = (session_row["prompt_preset_id"] or "").strip()
        preset = find_prompt_preset(prompt_presets_file, prompt_preset_id) or {}
        preset_name = (preset.get("name") or "").strip()
        preset_instructions = (preset.get("instructions") or "").strip()
        preset_context = (preset.get("context") or "").strip()
    else:
        custom_prompt = ""
        custom_context = ""
        preset_name = ""
        preset_instructions = ""
        preset_context = ""

    return (
        summary_text,
        preset_name,
        preset_instructions,
        preset_context,
        custom_prompt,
        custom_context,
    )


def voice_session_instructions(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    prompt_presets_file: str,
    base_system_prompt: str,
) -> str:
    (
        summary_text,
        _preset_name,
        preset_instructions,
        preset_context,
        custom_prompt,
        custom_context,
    ) = session_instruction_parts(conn, session_id, prompt_presets_file=prompt_presets_file)

    base_prompt = system_prompt(
        summary_text,
        preset_instructions=preset_instructions,
        preset_context=preset_context,
        custom_prompt=custom_prompt,
        custom_context=custom_context,
        base_system_prompt=base_system_prompt,
    )
    voice_guidance = (
        "You are speaking aloud in a live voice session. Keep responses concise, natural, and easy to follow. "
        "Prefer one or two short spoken paragraphs unless the user explicitly asks for more detail."
    )
    return f"{base_prompt}\n\n{voice_guidance}".strip()
