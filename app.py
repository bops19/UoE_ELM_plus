from flask import Flask, request, Response, stream_with_context, g, has_request_context, send_from_directory, redirect
import base64
import datetime
import hashlib
import io
import ipaddress
import json
import os
import re
import shutil
import sqlite3
import threading
import time
import urllib.request
import uuid
import zipfile
try:
    import resource
except Exception:
    resource = None
from werkzeug.exceptions import RequestEntityTooLarge
from export_service import (
    export_mime_type,
    normalize_export_format,
    render_response_markdown,
    render_response_text,
    render_session_markdown,
    render_session_text,
    response_export_filename,
    session_export_filename,
)
from model_catalog import (
    MODEL_METADATA,
    context_window_for_model,
    get_model_catalog_payload,
    model_supports_reasoning_effort,
    model_uses_responses_api,
    use_case_keys,
)
from prompt_session_service import (
    normalize_use_case,
    normalize_preset_name,
    normalize_session_text,
    normalize_session_update,
    use_case_supports_prompt_setup,
)
from prompt_presets_store import find_prompt_preset, load_prompt_presets, write_prompt_presets
from session_store import (
    assistant_response_ordinal,
    ensure_schema,
    ensure_session,
    insert_message,
    insert_session,
    refresh_session_title,
    serialize_message_row,
    session_detail,
    session_messages_before,
    session_selected_model,
    update_message,
)
from usage_history import build_usage_history_payload, token_history_scope, usage_cost
from vm_service import build_catalog_view, build_session_view, build_usage_view
from db_helpers import open_sqlite_db
import prompt_context_helpers
import request_helpers
from openai_client import (
    openai_api_key_fingerprint as _openai_api_key_fingerprint,
    openai_client as _openai_client,
    require_openai_api_key as _require_openai_api_key,
)
from transcription_utils import (
    transcription_segment_payload as _transcription_segment_payload,
    _raw_api_response_text,
    _transcription_text,
    _transcription_to_dict,
    _transcription_value_to_python,
    _write_diarize_debug_snapshot,
)
from computer_use_service import (
    ComputerRunError,
    ComputerRunManagerCore,
    ComputerRunManagerDeps,
    execute_computer_action,
    extract_computer_response,
    is_computer_use_preview_model,
    normalize_acknowledged_safety_checks,
    normalize_start_url,
)
from xml.etree import ElementTree
from errors import register_error_handlers, error_payload
from logging_config import configure_logging, configure_sentry
from auth import register_api_key_guard
from config import (
    ANGULAR_STATIC_DIR,
    API_KEY,
    ATTACHMENTS_DIR,
    ATTACHMENT_BUDGET_RATIO,
    APP_ENV,
    AUDIO_CHAT_FORMAT,
    AUDIO_CHAT_TRANSCRIBE_MODEL,
    AUDIO_CHAT_VOICE,
    BASE_SYSTEM_PROMPT,
    COMPUTER_USE_PREVIEW_DISPLAY_HEIGHT,
    COMPUTER_USE_PREVIEW_DISPLAY_WIDTH,
    COMPUTER_USE_PREVIEW_ENVIRONMENT,
    COMPUTER_USE_PREVIEW_MODEL,
    DB_FILE,
    DEEP_RESEARCH_DATA_SOURCE_TOOL_TYPES,
    DEEP_RESEARCH_MCP_PROFILES_JSON,
    DEEP_RESEARCH_MCP_SERVER_LABEL,
    DEEP_RESEARCH_MCP_SERVER_URL,
    DEEP_RESEARCH_TOOL_SELECTION_BOOL_KEYS,
    DEEP_RESEARCH_TOOL_SELECTION_KEYS,
    DEEP_RESEARCH_VECTOR_STORE_IDS,
    DEV_NAME_FRAGMENT_ALPHA,
    DEV_NAME_KEY_ALPHA,
    EMBEDDING_MODELS,
    EMBED_CHUNK_CHARS,
    EMBED_CHUNK_OVERLAP_CHARS,
    EMBED_SEARCH_TOP_K_MAX,
    HISTORY_CONTEXT_RATIO,
    IMAGE_EDIT_ALLOWED_MIME,
    IMAGE_EDIT_MAX_BYTES,
    IMAGE_MODERATION_LEVELS,
    IMAGE_OUTPUT_COUNTS,
    IMAGE_PROMPT_MAX_CHARS,
    IMAGE_SIZE_MAP,
    IMAGE_STYLE_GUIDANCE,
    IS_PRODUCTION,
    JSON_BODY_MAX_BYTES,
    LEGACY_SESSIONS_FILE,
    MAX_HISTORY_TOKENS,
    MAX_RECENT_MESSAGES,
    OPENAI_TIMEOUT_SEC,
    PROMPT_PRESETS_FILE,
    REALTIME_DEFAULT_VOICE,
    REQUEST_BODY_MAX_BYTES,
    SESSION_ARCHIVE_AFTER_DAYS,
    SESSION_DELETE_ARCHIVED_AFTER_DAYS,
    SUMMARY_MODEL,
    TEXT_FILE_EXTENSIONS,
    TOKEN_USAGE_LOG_FILE,
    TOOL_HANDOFF_EXTENSIONS,
    TTS_OUTPUT_FORMAT,
)

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None

_require_openai_api_key()

os.environ["FLASK_DEBUG"] = "0"
app = Flask(__name__)
app.config["DEBUG"] = False
app.config["API_KEY"] = API_KEY
configure_logging(app)
configure_sentry(app)
register_error_handlers(app)
register_api_key_guard(app)


app.config["MAX_CONTENT_LENGTH"] = REQUEST_BODY_MAX_BYTES

_RATE_LIMIT_DEFAULTS = {
    "chat": (30, 60),
    "computer_runs": (20, 60),
    "image": (20, 60),
    "image_edit": (15, 60),
    "audio_turn": (20, 60),
    "transcription_turn": (20, 60),
    "voice_turns": (60, 60),
    "project_mutation": (60, 60),
    "image_meta_mutation": (120, 60),
    "embed_index": (10, 60),
    "embed_search": (60, 60),
}
_RATE_LIMIT_TRUSTED_PROXIES_RAW = (os.getenv("RATE_LIMIT_TRUSTED_PROXIES") or "").strip()
_RATE_LIMIT_CLEANUP_INTERVAL_SEC = max(1, int(os.getenv("RATE_LIMIT_CLEANUP_INTERVAL_SEC", "120")))
_RATE_LIMIT_CLEANUP_MAX_ROWS = max(1, int(os.getenv("RATE_LIMIT_CLEANUP_MAX_ROWS", "5000")))
_RATE_LIMIT_LAST_CLEANUP_SEC = 0
_RATE_LIMIT_CLEANUP_LOCK = threading.Lock()


def log(emoji, label, message=""):
    time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{time}] {emoji}  {label} {message}", flush=True)


def _ensure_nofile_soft_limit(min_soft_limit: int = 4096) -> dict:
    if resource is None:
        return {"supported": False}
    try:
        soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
        target_limit = max(int(soft_limit), int(min_soft_limit))
        if hard_limit not in (-1, resource.RLIM_INFINITY):
            target_limit = min(target_limit, int(hard_limit))
        if target_limit > soft_limit:
            resource.setrlimit(resource.RLIMIT_NOFILE, (target_limit, hard_limit))
            soft_limit = target_limit
        return {
            "supported": True,
            "soft": int(soft_limit),
            "hard": int(hard_limit) if hard_limit not in (-1, resource.RLIM_INFINITY) else -1,
            "target": int(target_limit),
        }
    except Exception as exc:
        return {"supported": True, "error": f"{type(exc).__name__}: {exc}"}


_NOFILE_LIMIT_STATUS = _ensure_nofile_soft_limit(
    int(os.getenv("APP_MIN_NOFILE_SOFT", "4096"))
)


def _request_id() -> str:
    if not has_request_context():
        return "unknown"
    return getattr(g, "request_id", "unknown")


def _error_response(message: str, status: int, error_code: str, extra: dict | None = None):
    return error_payload(error_code, message, request_id=_request_id(), extra=extra), status


def _security_log(label: str, message: str):
    log("🛡️ ", label, f"[{_request_id()}] {message}")


def _parse_trusted_proxy_nets(raw_value: str) -> list[ipaddress._BaseNetwork]:
    nets: list[ipaddress._BaseNetwork] = []
    if not raw_value:
        return nets
    for candidate in raw_value.split(","):
        token = candidate.strip()
        if not token:
            continue
        try:
            nets.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            _security_log("RATE LIMIT ", f"invalid trusted proxy entry ignored: {token[:80]}")
    return nets


_RATE_LIMIT_TRUSTED_PROXY_NETS = _parse_trusted_proxy_nets(_RATE_LIMIT_TRUSTED_PROXIES_RAW)


def _parse_ip_address(value: str):
    token = (value or "").strip()
    if not token:
        return None
    try:
        return ipaddress.ip_address(token)
    except ValueError:
        return None


def _ip_in_trusted_proxies(ip_value: str) -> bool:
    parsed_ip = _parse_ip_address(ip_value)
    if parsed_ip is None:
        return False
    return any(parsed_ip in net for net in _RATE_LIMIT_TRUSTED_PROXY_NETS)


def _client_ip() -> str:
    remote_ip = _parse_ip_address(request.remote_addr or "")
    if remote_ip is None:
        return "unknown"

    if _ip_in_trusted_proxies(str(remote_ip)):
        forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
        if forwarded:
            for candidate in forwarded.split(","):
                forwarded_ip = _parse_ip_address(candidate)
                if forwarded_ip is not None:
                    return str(forwarded_ip)
    return str(remote_ip)


def _rate_limit_cleanup_if_due(conn: sqlite3.Connection, now_sec: int):
    global _RATE_LIMIT_LAST_CLEANUP_SEC
    if now_sec - _RATE_LIMIT_LAST_CLEANUP_SEC < _RATE_LIMIT_CLEANUP_INTERVAL_SEC:
        return
    with _RATE_LIMIT_CLEANUP_LOCK:
        if now_sec - _RATE_LIMIT_LAST_CLEANUP_SEC < _RATE_LIMIT_CLEANUP_INTERVAL_SEC:
            return
        deleted = conn.execute(
            """
            DELETE FROM rate_limit_windows
            WHERE rowid IN (
              SELECT rowid
              FROM rate_limit_windows
              WHERE expires_at_sec <= ?
              ORDER BY expires_at_sec ASC
              LIMIT ?
            )
            """,
            (now_sec, _RATE_LIMIT_CLEANUP_MAX_ROWS),
        ).rowcount
        if deleted:
            _security_log("RATE LIMIT ", f"cleanup deleted={deleted}")
        _RATE_LIMIT_LAST_CLEANUP_SEC = now_sec


def _rate_limit_retry_after(conn: sqlite3.Connection, bucket: str, limiter_key: str, now_sec: int, window_sec: int) -> int:
    oldest = conn.execute(
        """
        SELECT MIN(window_start_sec) AS oldest_window
        FROM rate_limit_windows
        WHERE bucket = ? AND limiter_key = ? AND window_start_sec > ?
        """,
        (bucket, limiter_key, now_sec - window_sec),
    ).fetchone()
    oldest_window = int((oldest["oldest_window"] if oldest else 0) or 0)
    if oldest_window <= 0:
        return 1
    return max(1, (oldest_window + window_sec) - now_sec)


def _check_rate_limit(bucket: str):
    return request_helpers.check_rate_limit(
        bucket,
        db_factory=_db,
        error_response=_error_response,
        security_log=_security_log,
        rate_limit_defaults=_RATE_LIMIT_DEFAULTS,
    )


def _openai_failure_response(error_code: str, unavailable_code: str | None = None):
    message = "Upstream service unavailable. Please retry shortly."
    status = 503
    resolved_code = unavailable_code or error_code
    return _error_response(message, status, resolved_code)


def _safe_openai_call(callable_fn, *, error_code: str, unavailable_error_code: str | None = None, label: str = "OPENAI"):
    try:
        return callable_fn(), None
    except Exception as exc:
        _security_log("PROVIDER ERR", f"{label}: {type(exc).__name__}: {str(exc)[:300]}")
        return None, _openai_failure_response(error_code, unavailable_code=unavailable_error_code)


def _validated_json_body(*, allowed_keys: set[str] | None = None, required_keys: set[str] | None = None):
    return request_helpers.validated_json_body(
        json_body_max_bytes=JSON_BODY_MAX_BYTES,
        error_response=_error_response,
        allowed_keys=allowed_keys,
        required_keys=required_keys,
    )


def _reject_oversized_multipart(max_bytes: int):
    return request_helpers.reject_oversized_multipart(
        max_bytes=max_bytes,
        error_response=_error_response,
    )


def _remove_session_files(session_ids: list[str]):
    for session_id in session_ids:
        safe_session_id = normalize_session_text(session_id or "")
        if not safe_session_id:
            continue
        session_dir = os.path.join(ATTACHMENTS_DIR, safe_session_id)
        if os.path.isdir(session_dir):
            shutil.rmtree(session_dir, ignore_errors=True)


def _normalize_deep_research_tools_selection(raw) -> tuple[dict[str, bool] | None, str | None]:
    if raw is None:
        return None, None
    if not isinstance(raw, dict):
        return None, "deepResearchTools must be an object with boolean tool flags."

    unexpected = sorted([str(key) for key in raw.keys() if key not in DEEP_RESEARCH_TOOL_SELECTION_KEYS])
    if unexpected:
        return None, f"Unknown deepResearchTools keys: {', '.join(unexpected)}"

    normalized: dict[str, bool] = {}
    for key in DEEP_RESEARCH_TOOL_SELECTION_BOOL_KEYS:
        value = raw.get(key)
        if value is None:
            normalized[key] = False
            continue
        if not isinstance(value, bool):
            return None, f"deepResearchTools.{key} must be a boolean."
        normalized[key] = value

    return normalized, None


def _normalize_deep_research_mcp_profile_id(raw) -> tuple[str | None, str | None]:
    if raw is None:
        return None, None
    if not isinstance(raw, str):
        return None, "deepResearchMcpProfileId must be a string."
    value = normalize_session_text(raw)
    if not value:
        return None, None
    return value, None


def _normalize_include_web_search(raw) -> tuple[bool, str | None]:
    if raw is None:
        return False, None
    if not isinstance(raw, bool):
        return False, "includeWebSearch must be a boolean."
    return raw, None


def _load_deep_research_mcp_profiles() -> list[dict]:
    profiles: list[dict] = []
    if DEEP_RESEARCH_MCP_SERVER_URL:
        profiles.append({
            "id": "default",
            "label": "Default MCP",
            "description": "Configured from DEEP_RESEARCH_MCP_SERVER_URL.",
            "server_label": DEEP_RESEARCH_MCP_SERVER_LABEL,
            "server_url": DEEP_RESEARCH_MCP_SERVER_URL,
            "require_approval": "never",
        })

    if DEEP_RESEARCH_MCP_PROFILES_JSON:
        try:
            parsed = json.loads(DEEP_RESEARCH_MCP_PROFILES_JSON)
        except Exception:
            parsed = []
            _security_log("CONFIG ERR ", "Invalid DEEP_RESEARCH_MCP_PROFILES_JSON; ignoring custom profiles.")
        if isinstance(parsed, list):
            for index, item in enumerate(parsed):
                if not isinstance(item, dict):
                    continue
                profile_id = normalize_session_text(str(item.get("id") or f"profile_{index+1}"))
                server_url = str(item.get("server_url") or "").strip()
                server_label = str(item.get("server_label") or profile_id or f"mcp_{index+1}").strip()
                if not profile_id or not server_url:
                    continue
                label = str(item.get("label") or profile_id).strip() or profile_id
                description = str(item.get("description") or "").strip()
                require_approval = str(item.get("require_approval") or "never").strip().lower()
                if require_approval not in {"always", "never"}:
                    require_approval = "never"
                profiles.append({
                    "id": profile_id,
                    "label": label,
                    "description": description,
                    "server_label": server_label,
                    "server_url": server_url,
                    "require_approval": require_approval,
                })

    deduped: list[dict] = []
    seen: set[str] = set()
    for profile in profiles:
        profile_id = profile.get("id")
        if not isinstance(profile_id, str) or not profile_id or profile_id in seen:
            continue
        seen.add(profile_id)
        deduped.append(profile)
    return deduped[:20]


DEEP_RESEARCH_MCP_PROFILES = _load_deep_research_mcp_profiles()
DEEP_RESEARCH_MCP_PROFILE_BY_ID = {
    str(profile.get("id")): profile
    for profile in DEEP_RESEARCH_MCP_PROFILES
    if isinstance(profile, dict) and isinstance(profile.get("id"), str)
}
DEEP_RESEARCH_DEFAULT_MCP_PROFILE_ID = (
    DEEP_RESEARCH_MCP_PROFILES[0]["id"] if DEEP_RESEARCH_MCP_PROFILES else None
)


def _resolve_deep_research_mcp_profile(profile_id: str | None) -> tuple[dict | None, str | None]:
    if profile_id:
        profile = DEEP_RESEARCH_MCP_PROFILE_BY_ID.get(profile_id)
        if not profile:
            return None, "Unknown deepResearchMcpProfileId."
        return profile, None
    if DEEP_RESEARCH_DEFAULT_MCP_PROFILE_ID:
        profile = DEEP_RESEARCH_MCP_PROFILE_BY_ID.get(DEEP_RESEARCH_DEFAULT_MCP_PROFILE_ID)
        if profile:
            return profile, None
    return None, None


def _deep_research_tools(
    selection: dict[str, bool] | None = None,
    mcp_profile_id: str | None = None,
) -> tuple[list[dict], list[str], str | None]:
    defaults = {
        "webSearch": True,
        "codeInterpreter": True,
        "fileSearch": False,
        "mcp": False,
    }
    selected = {**defaults, **(selection or {})}

    tools: list[dict] = []
    unavailable: list[str] = []

    if selected.get("webSearch"):
        tools.append({"type": "web_search"})

    if selected.get("codeInterpreter"):
        tools.append({
            "type": "code_interpreter",
            "container": {"type": "auto"},
        })

    if selected.get("fileSearch"):
        if DEEP_RESEARCH_VECTOR_STORE_IDS:
            tools.append({
                "type": "file_search",
                "vector_store_ids": DEEP_RESEARCH_VECTOR_STORE_IDS,
            })
        else:
            unavailable.append("file_search (set DEEP_RESEARCH_VECTOR_STORE_IDS)")

    if selected.get("mcp"):
        profile, profile_error = _resolve_deep_research_mcp_profile(mcp_profile_id)
        if profile_error:
            return tools, unavailable, profile_error
        if profile:
            tools.append({
                "type": "mcp",
                "server_label": profile.get("server_label") or DEEP_RESEARCH_MCP_SERVER_LABEL,
                "server_url": profile.get("server_url") or "",
                "require_approval": profile.get("require_approval") or "never",
            })
        else:
            unavailable.append("mcp (set DEEP_RESEARCH_MCP_SERVER_URL or DEEP_RESEARCH_MCP_PROFILES_JSON)")

    return tools, unavailable, None


def _deep_research_has_data_source(tools: list[dict]) -> bool:
    return any((tool.get("type") or "").strip() in DEEP_RESEARCH_DATA_SOURCE_TOOL_TYPES for tool in tools)


def _apply_session_retention(conn: sqlite3.Connection):
    now_ms = _now_ms()
    archive_cutoff = now_ms - max(0, SESSION_ARCHIVE_AFTER_DAYS) * 24 * 60 * 60 * 1000
    delete_cutoff = now_ms - max(0, SESSION_DELETE_ARCHIVED_AFTER_DAYS) * 24 * 60 * 60 * 1000

    try:
        conn.execute(
            """
            UPDATE sessions
            SET archived_at = ?
            WHERE archived_at IS NULL AND updated_at <= ?
            """,
            (now_ms, archive_cutoff),
        )

        stale_rows = conn.execute(
            """
            SELECT id
            FROM sessions
            WHERE archived_at IS NOT NULL AND archived_at <= ?
            """,
            (delete_cutoff,),
        ).fetchall()
        stale_ids = [str(row["id"]) for row in stale_rows if row and row["id"]]
        if stale_ids:
            placeholders = ", ".join(["?"] * len(stale_ids))
            conn.execute(f"DELETE FROM sessions WHERE id IN ({placeholders})", tuple(stale_ids))
            conn.commit()
            _remove_session_files(stale_ids)
            return
        conn.commit()
    except sqlite3.OperationalError as exc:
        if "readonly" in str(exc).lower():
            return
        raise


def divider():
    print(flush=True)
    print("─" * 60, flush=True)


def _now_ms() -> int:
    return int(datetime.datetime.now().timestamp() * 1000)


def _safe_get(obj, *path, default=None):
    current = obj
    for part in path:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(part)
        else:
            current = getattr(current, part, None)
    return default if current is None else current


def _compose_image_prompt(base_prompt: str, style: str) -> str:
    guidance = IMAGE_STYLE_GUIDANCE.get(style, "")
    if not guidance:
        return base_prompt
    return f"{base_prompt}\n\nStyle guidance: {guidance}"


def _decode_generated_images(response) -> list[dict]:
    images: list[dict] = []
    for item in (response.data or []):
        raw = None
        if getattr(item, "b64_json", None):
            raw = base64.b64decode(item.b64_json)
        elif getattr(item, "url", None):
            with urllib.request.urlopen(item.url) as result:
                raw = result.read()
        if not raw:
            continue
        if raw[:4] == b"\x89PNG":
            mime = "image/png"
        elif raw[:2] == b"\xff\xd8":
            mime = "image/jpeg"
        elif raw[:4] == b"RIFF":
            mime = "image/webp"
        else:
            mime = "image/png"
        images.append({"b64": base64.b64encode(raw).decode(), "mime": mime})
    return images


def _mapped_size_dimensions(size_value: str) -> tuple[int | None, int | None]:
    openai_size = IMAGE_SIZE_MAP.get(size_value, "")
    width = None
    height = None
    size_match = re.match(r"^(\d+)x(\d+)$", openai_size)
    if size_match:
        width = int(size_match.group(1))
        height = int(size_match.group(2))
    return width, height


def _embedding_model_or_default(model_value: str) -> str:
    candidate = normalize_session_text(model_value or "") or "text-embedding-3-large"
    return candidate


def _split_for_embedding(text: str, chunk_size: int = EMBED_CHUNK_CHARS, overlap: int = EMBED_CHUNK_OVERLAP_CHARS) -> list[str]:
    normalized = normalize_session_text(text or "")
    if not normalized:
        return []
    if chunk_size < 200:
        chunk_size = 200
    overlap = max(0, min(overlap, chunk_size // 2))
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunk = normalize_session_text(normalized[start:end])
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a <= 0.0 or norm_b <= 0.0:
        return -1.0
    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def _parse_embedding_vector(raw_value) -> list[float]:
    if isinstance(raw_value, list):
        values = raw_value
    elif isinstance(raw_value, str):
        try:
            values = json.loads(raw_value)
        except (TypeError, json.JSONDecodeError):
            return []
    else:
        return []
    output: list[float] = []
    for item in values:
        try:
            output.append(float(item))
        except (TypeError, ValueError):
            return []
    return output


def _derive_title(text: str) -> str:
    if not text:
        return "New chat"
    stripped = " ".join(str(text).split())
    return stripped[:42] + "…" if len(stripped) > 42 else stripped


def _preview_for_log(value: str, max_length: int = 180) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "file").strip("._")
    return cleaned or "file"


def _model_supports_segment_timestamps(model: str) -> bool:
    return (model or "").strip().startswith("whisper-1")

def _attachment_supports_text_extraction(mime_type: str, name: str) -> bool:
    ext = os.path.splitext(name or "")[1].lower()
    if mime_type.startswith("text/") or ext in TEXT_FILE_EXTENSIONS:
        return True
    return ext in {".docx", ".pdf"}


def _attachment_supports_tool_handoff(name: str, extraction_status: str) -> bool:
    ext = os.path.splitext(name or "")[1].lower()
    return extraction_status == "unsupported" and ext in TOOL_HANDOFF_EXTENSIONS


def _estimate_text_tokens(text: str) -> int:
    return prompt_context_helpers.estimate_text_tokens(text)


def _estimate_content_tokens(content) -> int:
    if isinstance(content, str):
        return _estimate_text_tokens(content)
    if not isinstance(content, list):
        return 0
    total = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        text_value = block.get("text")
        if block_type in ("text", "input_text") and isinstance(text_value, str):
            total += _estimate_text_tokens(text_value)
    return total


def _message_context_text(message: dict) -> str:
    return prompt_context_helpers.message_context_text(message)


def _estimate_message_tokens(message: dict) -> int:
    role = message.get("role", "assistant")
    return _estimate_text_tokens(f"{role}: {_message_context_text(message)}")


def _estimate_messages_tokens(messages: list[dict]) -> int:
    return prompt_context_helpers.estimate_messages_tokens(messages)


def _context_window_for_model(model: str) -> int:
    return prompt_context_helpers.context_window_for_selected_model(
        model,
        max_history_tokens=MAX_HISTORY_TOKENS,
    )


def _conversation_budget_for_model(model: str) -> tuple[int, int]:
    return prompt_context_helpers.conversation_budget_for_model(
        model,
        max_history_tokens=MAX_HISTORY_TOKENS,
        history_context_ratio=HISTORY_CONTEXT_RATIO,
        attachment_budget_ratio=ATTACHMENT_BUDGET_RATIO,
    )


def _estimate_request_input_tokens(
    summary_text: str,
    prior_messages: list[dict],
    user_content,
    preset_instructions: str = "",
    preset_context: str = "",
    custom_prompt: str = "",
    custom_context: str = "",
) -> int:
    return prompt_context_helpers.estimate_request_input_tokens(
        summary_text,
        prior_messages,
        user_content,
        preset_instructions,
        preset_context,
        custom_prompt,
        custom_context,
        base_system_prompt=BASE_SYSTEM_PROMPT,
    )


def _response_text(response) -> str:
    output_text = _safe_get(response, "output_text", default=None)
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    for output in _safe_get(response, "output", default=[]) or []:
        for content in _safe_get(output, "content", default=[]) or []:
            text_value = _safe_get(content, "text", default=None)
            if isinstance(text_value, str) and text_value:
                parts.append(text_value)
    return "\n".join(parts).strip()


def _chat_message_text(message) -> str:
    if not message:
        return ""
    audio_transcript = _safe_get(message, "audio", "transcript", default=None)
    if isinstance(audio_transcript, str) and audio_transcript.strip():
        return audio_transcript.strip()

    raw_content = _safe_get(message, "content", default=None)
    if isinstance(raw_content, str) and raw_content.strip():
        return raw_content.strip()
    if isinstance(raw_content, list):
        parts: list[str] = []
        for item in raw_content:
            if isinstance(item, dict):
                text_value = item.get("text")
                if isinstance(text_value, str) and text_value.strip():
                    parts.append(text_value.strip())
        return "\n".join(parts).strip()
    return ""


def _usage_payload(usage, responses_api=False):
    if not usage:
        return None

    if responses_api:
        input_tokens = int(_safe_get(usage, "input_tokens", default=0) or 0)
        output_tokens = int(_safe_get(usage, "output_tokens", default=0) or 0)
        reasoning_tokens = int(_safe_get(usage, "output_tokens_details", "reasoning_tokens", default=0) or 0)
    else:
        input_tokens = int(_safe_get(usage, "prompt_tokens", default=0) or 0)
        output_tokens = int(_safe_get(usage, "completion_tokens", default=0) or 0)
        reasoning_tokens = int(_safe_get(usage, "completion_tokens_details", "reasoning_tokens", default=0) or 0)

    fallback_total = input_tokens + output_tokens
    total_tokens = int(_safe_get(usage, "total_tokens", default=fallback_total) or fallback_total)

    return {
        "input": input_tokens,
        "output": output_tokens,
        "total": max(total_tokens, fallback_total),
        "reasoning": reasoning_tokens,
    }


def _voice_usage_payload(raw_usage, source: str | None = None):
    if not raw_usage:
        return None

    details_payload = _safe_get(raw_usage, "details", default={})
    details_payload = details_payload if isinstance(details_payload, dict) else {}

    input_tokens = int(
        _safe_get(raw_usage, "input", default=None)
        or _safe_get(raw_usage, "input_tokens", default=None)
        or _safe_get(raw_usage, "prompt_tokens", default=0)
        or 0
    )
    output_tokens = int(
        _safe_get(raw_usage, "output", default=None)
        or _safe_get(raw_usage, "output_tokens", default=None)
        or _safe_get(raw_usage, "completion_tokens", default=0)
        or 0
    )
    total_tokens = int(
        _safe_get(raw_usage, "total", default=None)
        or _safe_get(raw_usage, "total_tokens", default=(input_tokens + output_tokens))
        or (input_tokens + output_tokens)
    )
    reasoning_tokens = int(
        _safe_get(raw_usage, "reasoning", default=None)
        or _safe_get(raw_usage, "output_tokens_details", "reasoning_tokens", default=None)
        or _safe_get(raw_usage, "completion_tokens_details", "reasoning_tokens", default=0)
        or 0
    )

    input_details = _safe_get(raw_usage, "input_token_details", default={})
    if not isinstance(input_details, dict):
        input_details = _safe_get(raw_usage, "prompt_tokens_details", default={})
    input_details = input_details if isinstance(input_details, dict) else {}

    output_details = _safe_get(raw_usage, "output_token_details", default={})
    if not isinstance(output_details, dict):
        output_details = _safe_get(raw_usage, "completion_tokens_details", default={})
    output_details = output_details if isinstance(output_details, dict) else {}

    cached_details = input_details.get("cached_tokens_details") if isinstance(input_details.get("cached_tokens_details"), dict) else {}

    def _detail_int(primary: str, fallback):
        explicit = details_payload.get(primary)
        if explicit is not None:
            return int(explicit or 0)
        return int(fallback or 0)

    details = {
        "inputText": _detail_int("inputText", input_details.get("text_tokens")),
        "inputAudio": _detail_int("inputAudio", input_details.get("audio_tokens")),
        "inputImage": _detail_int("inputImage", input_details.get("image_tokens")),
        "inputCachedText": _detail_int("inputCachedText", cached_details.get("text_tokens")),
        "inputCachedAudio": _detail_int("inputCachedAudio", cached_details.get("audio_tokens")),
        "inputCachedImage": _detail_int("inputCachedImage", cached_details.get("image_tokens")),
        "outputText": _detail_int("outputText", output_details.get("text_tokens") or output_tokens),
        "outputAudio": _detail_int("outputAudio", output_details.get("audio_tokens")),
    }

    payload = {
        "input": input_tokens,
        "output": output_tokens,
        "total": max(total_tokens, input_tokens + output_tokens),
        "reasoning": reasoning_tokens,
        "details": details,
    }
    if source:
        payload["source"] = source
    return payload


def _combine_usage_payloads(*usages):
    totals = {
        "input": 0,
        "output": 0,
        "total": 0,
        "reasoning": 0,
    }
    details = {
        "inputText": 0,
        "inputAudio": 0,
        "inputImage": 0,
        "inputCachedText": 0,
        "inputCachedAudio": 0,
        "inputCachedImage": 0,
        "outputText": 0,
        "outputAudio": 0,
    }
    found = False

    for usage in usages:
        if not isinstance(usage, dict):
            continue
        found = True
        totals["input"] += int(usage.get("input") or 0)
        totals["output"] += int(usage.get("output") or 0)
        totals["total"] += int(usage.get("total") or 0)
        totals["reasoning"] += int(usage.get("reasoning") or 0)
        usage_details = usage.get("details") if isinstance(usage.get("details"), dict) else {}
        for key in details:
            details[key] += int(usage_details.get(key) or 0)

    if not found:
        return None

    combined = {
        **totals,
        "details": details,
    }
    combined["total"] = max(combined["total"], combined["input"] + combined["output"])
    return combined


def _transcription_prompt(conn: sqlite3.Connection, session_id: str) -> str:
    (
        _summary_text,
        _preset_name,
        preset_instructions,
        preset_context,
        custom_prompt,
        custom_context,
    ) = _session_instruction_parts(conn, session_id)

    parts = []
    if preset_instructions:
        parts.append(preset_instructions)
    if preset_context:
        parts.append(preset_context)
    if custom_prompt:
        parts.append(custom_prompt)
    if custom_context:
        parts.append(custom_context)
    prompt = " ".join(part.strip() for part in parts if part and part.strip())
    return prompt[:1000].strip()


def _audio_mime_type_for_format(format_name: str) -> str:
    if format_name == "wav":
        return "audio/wav"
    if format_name == "opus":
        return "audio/opus"
    if format_name == "flac":
        return "audio/flac"
    if format_name == "pcm16":
        return "audio/L16"
    return "audio/mpeg"


def _tts_supported_voices(model: str) -> list[str]:
    meta = MODEL_METADATA.get(model, {})
    if not meta:
        for key, candidate in MODEL_METADATA.items():
            if model.startswith(key):
                meta = candidate
                break
    voices = meta.get("ttsVoices") if isinstance(meta, dict) else None
    return [str(voice).strip() for voice in (voices or []) if str(voice).strip()]


def _assistant_supported_voices(model: str) -> list[str]:
    meta = MODEL_METADATA.get(model, {})
    if not meta:
        for key, candidate in MODEL_METADATA.items():
            if model.startswith(key):
                meta = candidate
                break
    voices = meta.get("assistantVoices") if isinstance(meta, dict) else None
    return [str(voice).strip() for voice in (voices or []) if str(voice).strip()]


def _transcription_source_label(source_kind: str, source_name: str) -> str:
    if source_kind == "uploaded":
        return f"Uploaded audio: {source_name}" if source_name else "Uploaded audio"
    return "Recorded audio"


def _reasoning_stage_line(stage: str, status: str, detail: str | None = None) -> str:
    labels = {
        "context_build": "Preparing context",
        "attachment_prep": "Preparing attachments",
        "model_generating": "Planning response",
        "streaming_response": "Streaming response",
        "finalizing_usage": "Finalizing response",
        "completed": "Completed",
    }
    label = labels.get(stage, stage.replace("_", " ").title())
    suffix = f" ({detail})" if detail else ""
    if status == "done":
        return f"- {label} done{suffix}"
    if status == "unavailable":
        return f"- {label} unavailable{suffix}"
    if status == "error":
        return f"- {label} failed{suffix}"
    return f"- {label}{suffix}"


def _is_computer_use_preview_model(model: str) -> bool:
    return is_computer_use_preview_model(
        model,
        normalize_text=normalize_session_text,
        preview_model=COMPUTER_USE_PREVIEW_MODEL,
    )


def _normalize_acknowledged_safety_checks(raw_checks) -> list[dict]:
    return normalize_acknowledged_safety_checks(
        raw_checks,
        transcription_value_to_python=_transcription_value_to_python,
    )


def _normalize_start_url(start_url: str | None) -> str | None:
    return normalize_start_url(start_url, normalize_text=normalize_session_text)


def _extract_computer_response(response) -> dict:
    return extract_computer_response(
        response,
        normalize_text=normalize_session_text,
        transcription_to_dict=_transcription_to_dict,
        transcription_value_to_python=_transcription_value_to_python,
        response_text=_response_text,
        usage_payload=_usage_payload,
    )


def _execute_computer_action(page, action: dict):
    return execute_computer_action(page, action, normalize_text=normalize_session_text)


class ComputerRunManager(ComputerRunManagerCore):
    def __init__(self, openai_client_factory, playwright_factory):
        deps = ComputerRunManagerDeps(
            normalize_text=normalize_session_text,
            now_ms=_now_ms,
            request_id=_request_id,
            db_factory=_db,
            append_token_usage_log=_append_token_usage_log,
            usage_cost=usage_cost,
            ensure_session=ensure_session,
            insert_message=insert_message,
            refresh_session_title=refresh_session_title,
            update_message=update_message,
            response_text=_response_text,
            usage_payload=_usage_payload,
            transcription_to_dict=_transcription_to_dict,
            transcription_value_to_python=_transcription_value_to_python,
            security_log=_security_log,
            openai_timeout_sec=OPENAI_TIMEOUT_SEC,
            preview_model=COMPUTER_USE_PREVIEW_MODEL,
            preview_environment=COMPUTER_USE_PREVIEW_ENVIRONMENT,
        )
        super().__init__(openai_client_factory, playwright_factory, deps)


def _db():
    return open_sqlite_db(DB_FILE)


def _append_token_usage_log(entry: dict):
    os.makedirs(os.path.dirname(TOKEN_USAGE_LOG_FILE), exist_ok=True)
    with open(TOKEN_USAGE_LOG_FILE, "a", encoding="utf-8") as file:
        file.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _take_tail_that_fits(messages: list[dict], budget_tokens: int) -> list[dict]:
    if budget_tokens <= 0 or not messages:
        return []
    selected: list[dict] = []
    used = 0
    for message in reversed(messages):
        cost = _estimate_message_tokens(message)
        if selected and used + cost > budget_tokens:
            break
        if not selected and cost > budget_tokens:
            selected.append(message)
            break
        selected.append(message)
        used += cost
    selected.reverse()
    return selected


def _summary_prompt(existing_summary: str, older_messages: list[dict]) -> str:
    transcript = []
    for message in older_messages:
        role = "User" if message.get("role") == "user" else "Assistant"
        transcript.append(f"{role}: {_message_context_text(message)}")
    transcript_text = "\n\n".join(transcript)
    return (
        "Existing rolling summary:\n"
        f"{existing_summary or '(none)'}\n\n"
        "Older transcript to fold into the summary:\n"
        f"{transcript_text}\n\n"
        "Return an updated rolling summary that preserves instructions, facts, constraints, decisions, "
        "open questions, and active tasks. Keep it concise and under about 1500 tokens."
    )


def _refresh_summary(conn: sqlite3.Connection, session_id: str, existing_summary: str, older_messages: list[dict]):
    if not older_messages:
        return existing_summary or ""

    try:
        response = _openai_client().responses.create(
            model=SUMMARY_MODEL,
            instructions=(
                "You compress conversation history into a durable working memory. "
                "Do not add facts. Keep the result concise, structured, and faithful."
            ),
            input=_summary_prompt(existing_summary, older_messages),
            store=False,
        )
        summary_text = _response_text(response)
    except Exception as exc:
        log("⚠️ ", "SUMMARY    ", f"failed: {exc}")
        return existing_summary or ""

    if not summary_text:
        return existing_summary or ""

    conn.execute(
        """
        UPDATE sessions
        SET summary = ?, summary_message_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (summary_text, older_messages[-1]["id"], _now_ms(), session_id),
    )
    return summary_text


def _prepare_context(conn: sqlite3.Connection, session_id: str, current_user_id: int, model: str):
    return prompt_context_helpers.prepare_context(
        conn,
        session_id,
        current_user_id,
        model,
        prompt_presets_file=PROMPT_PRESETS_FILE,
        max_recent_messages=MAX_RECENT_MESSAGES,
        max_history_tokens=MAX_HISTORY_TOKENS,
        history_context_ratio=HISTORY_CONTEXT_RATIO,
        attachment_budget_ratio=ATTACHMENT_BUDGET_RATIO,
        summary_model=SUMMARY_MODEL,
        openai_client_factory=_openai_client,
        response_text_fn=_response_text,
        now_ms_fn=_now_ms,
        log_fn=log,
    )


def _system_prompt(
    summary_text: str,
    preset_instructions: str = "",
    preset_context: str = "",
    custom_prompt: str = "",
    custom_context: str = "",
) -> str:
    return prompt_context_helpers.system_prompt(
        summary_text,
        preset_instructions,
        preset_context,
        custom_prompt,
        custom_context,
        base_system_prompt=BASE_SYSTEM_PROMPT,
    )


def _session_instruction_parts(conn: sqlite3.Connection, session_id: str):
    return prompt_context_helpers.session_instruction_parts(
        conn,
        session_id,
        prompt_presets_file=PROMPT_PRESETS_FILE,
    )


def _voice_session_instructions(conn: sqlite3.Connection, session_id: str) -> str:
    return prompt_context_helpers.voice_session_instructions(
        conn,
        session_id,
        prompt_presets_file=PROMPT_PRESETS_FILE,
        base_system_prompt=BASE_SYSTEM_PROMPT,
    )


def _mint_realtime_client_secret(model: str, instructions: str, voice: str = "ash") -> dict:

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured on the server.")

    request_body = {
        "expires_after": {
            "anchor": "created_at",
            "seconds": 600,
        },
        "session": {
            "type": "realtime",
            "model": model,
            "instructions": instructions,
            "output_modalities": ["audio"],
            "audio": {
                "input": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": 24000,
                    },
                    "noise_reduction": {
                        "type": "near_field",
                    },
                    "transcription": {
                        "model": "gpt-4o-mini-transcribe",
                        "language": "en",
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "create_response": True,
                        "interrupt_response": True,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
                    },
                },
                "output": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": 24000,
                    },
                    "voice": voice,
                },
            },
        },
    }
    encoded_body = json.dumps(request_body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.openai.com/v1/realtime/client_secrets",
        data=encoded_body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


def _read_file_bytes(path: str) -> bytes | None:
    if not path or not os.path.exists(path):
        return None
    with open(path, "rb") as file:
        return file.read()


def _excerpt_text(text: str, token_budget: int) -> str:
    if token_budget <= 0 or not text:
        return ""
    max_chars = max(400, token_budget * 4)
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[Attachment excerpt truncated]"


def _attachment_context_blocks(attachments: list[sqlite3.Row], responses_api: bool, budget_tokens: int):
    if not attachments:
        return []

    text_attachments = [
        row for row in attachments
        if (row["extracted_text"] or "") and row["availability"] == "ready"
    ]
    image_attachments = [
        row for row in attachments
        if row["availability"] == "ready" and (row["mime_type"] or "").startswith("image/")
    ]
    tool_handoff_attachments = [
        row for row in attachments
        if row["availability"] == "ready"
        and _attachment_supports_tool_handoff(row["name"] or "", row["extraction_status"] or "unsupported")
    ]

    blocks = []
    text_budget_each = max(250, budget_tokens // max(1, len(text_attachments))) if text_attachments else 0

    for row in text_attachments:
        excerpt = _excerpt_text(row["extracted_text"] or "", text_budget_each)
        if not excerpt:
            continue
        label = f"[Attached file: {row['name']}]\n{excerpt}"
        if responses_api:
            blocks.append({"type": "input_text", "text": label})
        else:
            blocks.append({"type": "text", "text": label})

    for row in image_attachments:
        raw = _read_file_bytes(row["local_path"] or "")
        if not raw:
            continue
        b64 = base64.b64encode(raw).decode()
        if responses_api:
            blocks.append({
                "type": "input_image",
                "image_url": f"data:{row['mime_type']};base64,{b64}",
            })
        else:
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{row['mime_type']};base64,{b64}"},
            })

    for row in tool_handoff_attachments:
        label = (
            f"[Attached binary tool file: {row['name']}]\n"
            f"Local path on server: {row['local_path']}\n"
            "This format is intended for MCP/tool processing rather than direct text extraction."
        )
        if responses_api:
            blocks.append({"type": "input_text", "text": label})
        else:
            blocks.append({"type": "text", "text": label})

    return blocks


def _current_user_content(user_text: str, attachments: list[sqlite3.Row], responses_api: bool, attachment_budget: int):
    if not attachments:
        return user_text

    if responses_api:
        blocks = [{"type": "input_text", "text": user_text}]
    else:
        blocks = [{"type": "text", "text": user_text}]

    blocks.extend(_attachment_context_blocks(attachments, responses_api, attachment_budget))
    return blocks


def _load_active_attachments(conn: sqlite3.Connection, session_id: str, active_attachment_ids: list[str] | None):
    if active_attachment_ids:
        placeholders = ",".join(["?"] * len(active_attachment_ids))
        rows = conn.execute(
            f"""
            SELECT *
            FROM attachments
            WHERE session_id = ? AND id IN ({placeholders})
            ORDER BY created_at ASC, id ASC
            """,
            (session_id, *active_attachment_ids),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT *
            FROM attachments
            WHERE session_id = ? AND active = 1
            ORDER BY created_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()

    refreshed_rows = [_refresh_attachment_extraction_if_possible(conn, row) for row in rows]
    return [row for row in refreshed_rows if row["availability"] == "ready"]


def _context_message_payload(message: dict):
    return {
        "role": message["role"],
        "content": _message_context_text(message),
    }


def _extract_docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        raw = archive.read("word/document.xml")
    root = ElementTree.fromstring(raw)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", ns):
        runs = [node.text for node in paragraph.findall(".//w:t", ns) if node.text]
        if runs:
            paragraphs.append("".join(runs))
    return "\n".join(paragraphs).strip()


def _extract_text_from_file(data: bytes, mime_type: str, name: str):
    ext = os.path.splitext(name or "")[1].lower()
    if mime_type.startswith("text/") or ext in TEXT_FILE_EXTENSIONS:
        try:
            return data.decode("utf-8"), "extracted"
        except UnicodeDecodeError:
            return data.decode("latin-1", errors="ignore"), "extracted"

    if ext == ".docx":
        try:
            return _extract_docx_text(data), "extracted"
        except Exception:
            return "", "failed"

    if ext == ".pdf":
        if PdfReader is None:
            return "", "unsupported"
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            return text, "extracted" if text else "failed"
        except Exception:
            return "", "failed"

    return "", "unsupported"


def _refresh_attachment_extraction_if_possible(conn: sqlite3.Connection, row: sqlite3.Row) -> sqlite3.Row:
    if not row or row["availability"] != "ready":
        return row
    if row["extraction_status"] == "extracted":
        return row
    if not _attachment_supports_text_extraction(row["mime_type"] or "", row["name"] or ""):
        return row

    raw = _read_file_bytes(row["local_path"] or "")
    if raw is None:
        return row

    extracted_text, extraction_status = _extract_text_from_file(
        raw,
        row["mime_type"] or "",
        row["name"] or "",
    )
    if extraction_status == (row["extraction_status"] or "unsupported") and (extracted_text or "") == (row["extracted_text"] or ""):
        return row

    conn.execute(
        """
        UPDATE attachments
        SET extracted_text = ?, extraction_status = ?, updated_at = ?
        WHERE id = ?
        """,
        (extracted_text, extraction_status, _now_ms(), row["id"]),
    )
    return conn.execute(
        "SELECT * FROM attachments WHERE id = ?",
        (row["id"],),
    ).fetchone()


def _attachment_dir(session_id: str) -> str:
    path = os.path.join(ATTACHMENTS_DIR, session_id)
    os.makedirs(path, exist_ok=True)
    return path


def _store_attachment(conn: sqlite3.Connection, session_id: str, file_storage):
    raw = file_storage.read()
    attachment_id = uuid.uuid4().hex
    safe_name = _sanitize_filename(file_storage.filename or "file")
    local_path = os.path.join(_attachment_dir(session_id), f"{attachment_id}_{safe_name}")
    with open(local_path, "wb") as file:
        file.write(raw)

    mime_type = file_storage.mimetype or "application/octet-stream"
    extracted_text, extraction_status = _extract_text_from_file(raw, mime_type, safe_name)
    default_active = 1 if (
        extraction_status == "extracted"
        or mime_type.startswith("image/")
        or _attachment_supports_tool_handoff(safe_name, extraction_status)
    ) else 0
    timestamp = _now_ms()

    conn.execute(
        """
        INSERT INTO attachments
          (id, session_id, name, mime_type, local_path, extracted_text, size_bytes, active, availability, extraction_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            attachment_id,
            session_id,
            file_storage.filename or safe_name,
            mime_type,
            local_path,
            extracted_text,
            len(raw),
            default_active,
            "ready",
            extraction_status,
            timestamp,
            timestamp,
        ),
    )
    conn.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        (_now_ms(), session_id),
    )


def _insert_missing_attachment_placeholder(conn: sqlite3.Connection, session_id: str, file_name: str, created_at: int):
    attachment_id = uuid.uuid4().hex
    conn.execute(
        """
        INSERT INTO attachments
          (id, session_id, name, mime_type, local_path, extracted_text, size_bytes, active, availability, extraction_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, '', '', 0, 0, 'missing', 'missing', ?, ?)
        """,
        (
            attachment_id,
            session_id,
            file_name or "file",
            "application/octet-stream",
            created_at,
            created_at,
        ),
    )


def _import_legacy_sessions(conn: sqlite3.Connection):
    try:
        with open(LEGACY_SESSIONS_FILE, "r", encoding="utf-8") as file:
            sessions = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    if not isinstance(sessions, list):
        return

    for session in sessions:
        session_id = session.get("id")
        if not session_id:
            continue
        created_at = int(session.get("createdAt") or _now_ms())
        use_case = session.get("useCase") or "general"
        title = session.get("title") or "New chat"
        insert_session(conn, session_id, use_case, title=title, created_at=created_at)
        conn.execute(
            """
            UPDATE sessions
            SET title = ?, use_case = ?, updated_at = ?
            WHERE id = ?
            """,
            (title, use_case, created_at, session_id),
        )

        for index, message in enumerate(session.get("messages") or []):
            created = created_at + index
            insert_message(
                conn,
                session_id,
                message.get("role") or "assistant",
                message.get("content") or "",
                msg_type=message.get("msgType") or "text",
                payload=message.get("payload"),
                usage=message.get("usage"),
                usage_model=message.get("usageModel"),
                usage_cost=message.get("usageCost"),
                elapsed_sec=message.get("elapsedSec"),
                reasoning_summary=message.get("reasoningSummary"),
                reasoning_status=message.get("reasoningStatus"),
                status=message.get("status") or "complete",
                created_at=created,
            )

        for file_name in session.get("fileNames") or []:
            _insert_missing_attachment_placeholder(conn, session_id, file_name, created_at)

    conn.commit()


def _init_storage():
    os.makedirs(ATTACHMENTS_DIR, exist_ok=True)
    if not os.path.exists(PROMPT_PRESETS_FILE):
        write_prompt_presets(PROMPT_PRESETS_FILE, [])
    with _db() as conn:
        ensure_schema(conn)
        row = conn.execute("SELECT COUNT(*) AS count FROM sessions").fetchone()
        if row and row["count"] == 0:
            _import_legacy_sessions(conn)


_init_storage()
COMPUTER_RUN_MANAGER = ComputerRunManager(_openai_client, sync_playwright)


@app.before_request
def _assign_request_id():
    g.request_id = uuid.uuid4().hex


@app.after_request
def _apply_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob: https:; "
        "connect-src 'self' https://api.openai.com wss://api.openai.com; "
        "font-src 'self' data:; "
        "media-src 'self' data: blob:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    response.headers["X-Request-Id"] = _request_id()
    return response


@app.errorhandler(RequestEntityTooLarge)
def _handle_entity_too_large(_exc):
    return _error_response("Request payload is too large.", 413, "payload_too_large")


# ── Page ─────────────────────────────────────────────────────────────────────

# Implementations live in handlers/misc.py (imported at module bottom).


# ── Sessions ─────────────────────────────────────────────────────────────────

# Implementations live in handlers/sessions.py (imported at module bottom).


# ── Image projects + image-meta ──────────────────────────────────────────────
# Implementations live in handlers/image.py and are bound via app.add_url_rule
# at module bottom.


# ── Sessions / attachments / prompt presets / usage history ────────────────
# Implementations live in handlers/sessions.py (imported at module bottom).


# ── Voice / audio / transcription / TTS ──────────────────────────────────────
# Implementations live in handlers/voice.py (imported at module bottom).



# ── Computer use (legacy preview) ─────────────────────────────────────────────
# Implementations live in handlers/computer.py (imported at module bottom).


# ── Settings (model / effort change notification) ────────────────────────────

# Implementations live in handlers/misc.py (imported at module bottom).


# ── Chat (streaming text) ─────────────────────────────────────────────────────

# Implementation lives in handlers/chat.py (imported at module bottom).


def _single_shot_interaction(session_id: str, use_case: str, user_text: str):
    if not session_id or not user_text:
        return None, None
    with _db() as conn:
        ensure_session(conn, session_id, use_case)
        insert_message(conn, session_id, "user", user_text, status="complete")
        refresh_session_title(conn, session_id)
        assistant_message_id = insert_message(conn, session_id, "assistant", "", status="pending")
        conn.commit()
    return assistant_message_id, user_text


# ── Image generation ──────────────────────────────────────────────────────────
# Implementations live in handlers/image.py and are bound via app.add_url_rule
# at module bottom.


# ── Text-to-speech ────────────────────────────────────────────────────────────

# Implementation lives in handlers/voice.py (imported at module bottom).



# ── Embeddings ────────────────────────────────────────────────────────────────
# Implementations live in handlers/embedding.py. They are imported below, after
# all helpers above have been added to this module's namespace.


from handlers.chat import chat
from handlers.computer import computer_run_close, computer_run_start, computer_run_step
from handlers.embedding import embed, embed_index, embed_search
from handlers.sessions import (
    archive_session,
    clear_session,
    create_prompt_preset,
    delete_attachment,
    delete_prompt_preset,
    delete_session,
    export_assistant_message,
    export_session,
    get_prompt_presets,
    get_session_detail,
    get_sessions,
    get_usage_history,
    update_attachment,
    update_prompt_preset,
    update_session,
    upload_attachments,
)
from handlers.image import (
    create_image_project,
    delete_image_project,
    edit_image,
    generate_image,
    get_image_projects,
    rename_image_project,
    update_image_message_meta,
)
from handlers.misc import (
    angular_app_entry,
    deep_research_mcp_profiles,
    get_model_catalog,
    index,
    settings,
    vm_catalog,
    vm_session,
    vm_usage,
)
from handlers.voice import (
    bootstrap_voice_session,
    create_audio_turn,
    create_transcription_turn,
    persist_voice_turn,
    text_to_speech,
)

# Image endpoints were originally registered with @app.route directly. Bind them
# explicitly here so existing URLs and tests remain unchanged.
app.add_url_rule(
    "/sessions/<session_id>/messages/<int:message_id>/image-meta",
    view_func=update_image_message_meta,
    methods=["PATCH"],
)
app.add_url_rule("/image-projects", view_func=get_image_projects, methods=["GET"])
app.add_url_rule(
    "/image-projects",
    view_func=create_image_project,
    methods=["POST"],
    endpoint="create_image_project",
)
app.add_url_rule(
    "/image-projects/<project_id>",
    view_func=rename_image_project,
    methods=["PATCH"],
    endpoint="rename_image_project",
)
app.add_url_rule(
    "/image-projects/<project_id>",
    view_func=delete_image_project,
    methods=["DELETE"],
    endpoint="delete_image_project",
)
app.add_url_rule("/image", view_func=generate_image, methods=["POST"])
app.add_url_rule("/image/edit", view_func=edit_image, methods=["POST"])

from routes.chat import chat_bp
from routes.computer import computer_bp
from routes.embedding import embedding_bp
from routes.misc import misc_bp
from routes.route_context import register_route_handlers
from routes.sessions import sessions_bp
from routes.voice import voice_bp

register_route_handlers(
    index=index,
    angular_app_entry=angular_app_entry,
    get_model_catalog=get_model_catalog,
    get_sessions=get_sessions,
    get_session_detail=get_session_detail,
    export_session=export_session,
    export_assistant_message=export_assistant_message,
    get_usage_history=get_usage_history,
    update_session=update_session,
    get_prompt_presets=get_prompt_presets,
    create_prompt_preset=create_prompt_preset,
    update_prompt_preset=update_prompt_preset,
    delete_prompt_preset=delete_prompt_preset,
    delete_session=delete_session,
    clear_session=clear_session,
    archive_session=archive_session,
    upload_attachments=upload_attachments,
    update_attachment=update_attachment,
    delete_attachment=delete_attachment,
    bootstrap_voice_session=bootstrap_voice_session,
    persist_voice_turn=persist_voice_turn,
    create_audio_turn=create_audio_turn,
    create_transcription_turn=create_transcription_turn,
    computer_run_start=computer_run_start,
    computer_run_step=computer_run_step,
    computer_run_close=computer_run_close,
    settings=settings,
    deep_research_mcp_profiles=deep_research_mcp_profiles,
    vm_usage=vm_usage,
    vm_session=vm_session,
    vm_catalog=vm_catalog,
    chat=chat,
    text_to_speech=text_to_speech,
    embed_index=embed_index,
    embed_search=embed_search,
    embed=embed,
)

app.register_blueprint(misc_bp)
app.register_blueprint(sessions_bp)
app.register_blueprint(chat_bp)
app.register_blueprint(voice_bp)
app.register_blueprint(computer_bp)
app.register_blueprint(embedding_bp)
