import datetime
import re


def normalize_export_format(value: str | None, default_value: str = "md") -> str:
    candidate = (value or default_value or "md").strip().lower()
    return "txt" if candidate == "txt" else "md"


def export_mime_type(export_format: str) -> str:
    return "text/plain" if export_format == "txt" else "text/markdown"


def export_extension(export_format: str) -> str:
    return "txt" if export_format == "txt" else "md"


def slugify_title(value: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return (slug[:48] or "new-chat")


def export_timestamp(now: datetime.datetime | None = None) -> str:
    date_value = now or datetime.datetime.utcnow()
    return date_value.strftime("%Y-%m-%d-%H%M%S")


def response_export_filename(session_title: str, response_number: int, export_format: str) -> str:
    title = slugify_title(session_title)
    stamp = export_timestamp()
    extension = export_extension(export_format)
    ordinal = max(1, int(response_number or 1))
    return f"{title}-{stamp}-response-{ordinal}.{extension}"


def session_export_filename(session_title: str, export_format: str) -> str:
    title = slugify_title(session_title)
    stamp = export_timestamp()
    extension = export_extension(export_format)
    return f"{title}-{stamp}-session.{extension}"


def _message_usage_line(message: dict) -> str:
    usage = message.get("usage") or {}
    if not isinstance(usage, dict):
        return ""
    input_tokens = int(usage.get("input") or 0)
    output_tokens = int(usage.get("output") or 0)
    total_tokens = int(usage.get("total") or 0)
    if input_tokens <= 0 and output_tokens <= 0 and total_tokens <= 0:
        return ""
    if total_tokens <= 0:
        total_tokens = input_tokens + output_tokens
    return f"*Tokens: {input_tokens} in / {output_tokens} out — {total_tokens} total*\n\n"


def _assistant_message_block(message: dict) -> str:
    msg_type = str(message.get("msgType") or "text")
    if msg_type == "image":
        body = "*[Image generated]*"
    elif msg_type == "audio":
        body = "*[Audio generated]*"
    elif msg_type == "embed":
        payload = message.get("payload") or {}
        body = f"**Embedding** — model: {payload.get('model')}, dimensions: {payload.get('dimensions')}"
    elif msg_type == "moderation":
        payload = message.get("payload") or {}
        body = f"**Moderation** — flagged: {payload.get('flagged')}"
    else:
        body = str(message.get("content") or "")
        payload = message.get("payload") or {}
        if isinstance(payload, dict):
            segments = payload.get("transcriptSegments")
            if isinstance(segments, list) and segments:
                body += "\n\n#### Timestamped segments\n\n" + _render_transcript_segments_markdown(segments)
    return f"### Assistant\n\n{body}\n\n"


def _format_segment_time(seconds_value) -> str:
    try:
        total_seconds = max(0, int(float(seconds_value or 0)))
    except (TypeError, ValueError):
        total_seconds = 0
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _render_transcript_segments_markdown(segments: list[dict]) -> str:
    lines = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start_label = _format_segment_time(segment.get("startSec"))
        end_label = _format_segment_time(segment.get("endSec"))
        lines.append(f"- `[{start_label} - {end_label}]` {text}")
    return "\n".join(lines).strip()


def render_session_markdown(session: dict, preset: dict | None = None, selected_model: str | None = None) -> str:
    model = str(selected_model or "").strip() or "unknown"
    date_label = datetime.datetime.now().isoformat(sep=" ", timespec="seconds")
    out = f"# ELM+ Chat Export\n\n**Model:** {model}  \n**Date:** {date_label}\n\n---\n\n"

    if preset:
        out += f"## Selected Prompt Preset\n\n**Name:** {preset.get('name', '')}\n\n"
        if str(preset.get("instructions") or "").strip():
            out += f"### Instructions\n\n{preset.get('instructions')}\n\n"
        if str(preset.get("context") or "").strip():
            out += f"### Context\n\n{preset.get('context')}\n\n"
        out += "---\n\n"

    if str(session.get("prompt") or "").strip():
        out += f"## Saved Prompt\n\n{session.get('prompt')}\n\n---\n\n"
    if str(session.get("context") or "").strip():
        out += f"## Saved Context\n\n{session.get('context')}\n\n---\n\n"

    for message in session.get("messages") or []:
        role = str(message.get("role") or "")
        if role == "user":
            out += f"### You\n\n{message.get('content', '')}\n\n"
        elif role == "assistant":
            out += _assistant_message_block(message)
            out += _message_usage_line(message)
        else:
            continue
        out += "---\n\n"
    return out


def render_session_text(session: dict, preset: dict | None = None, selected_model: str | None = None) -> str:
    markdown = render_session_markdown(session, preset=preset, selected_model=selected_model)
    lines = [line for line in markdown.splitlines() if line.strip() != "---"]
    return "\n".join(lines).strip() + "\n"


def render_response_markdown(content: str, payload: dict | None = None) -> str:
    body = str(content or "")
    if isinstance(payload, dict):
        segments = payload.get("transcriptSegments")
        if isinstance(segments, list) and segments:
            segment_block = _render_transcript_segments_markdown(segments)
            if segment_block:
                body += "\n\n#### Timestamped segments\n\n" + segment_block
    return body


def render_response_text(content: str, payload: dict | None = None) -> str:
    body = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    if isinstance(payload, dict):
        segments = payload.get("transcriptSegments")
        if isinstance(segments, list) and segments:
            segment_lines = []
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                text = str(segment.get("text") or "").strip()
                if not text:
                    continue
                start_label = _format_segment_time(segment.get("startSec"))
                end_label = _format_segment_time(segment.get("endSec"))
                segment_lines.append(f"[{start_label} - {end_label}] {text}")
            if segment_lines:
                body += ("\n\nTimestamped segments\n\n" + "\n".join(segment_lines))
    return body
