import datetime
import json
import sqlite3

from attachment_service import serialize_attachment_record
from model_catalog import use_case_keys
from prompt_session_service import normalize_use_case, resolve_prompt_preset_id, use_case_supports_prompt_setup


def _now_ms() -> int:
    return int(datetime.datetime.now().timestamp() * 1000)


def _json_loads(raw, default=None):
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def _json_dumps(value):
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _safe_message_content(content: str, status: str, role: str) -> str:
    if content:
        return content
    if role == "assistant" and status == "pending":
        return "[Response incomplete]"
    if role == "assistant" and status == "interrupted":
        return "[Response interrupted]"
    if role == "assistant" and status == "error":
        return "[Request failed]"
    return ""


def _derive_title(text: str) -> str:
    if not text:
        return "New chat"
    stripped = " ".join(text.split())
    return stripped[:42] + "…" if len(stripped) > 42 else stripped


def serialize_message_row(row: sqlite3.Row) -> dict:
    status = row["status"] or "complete"
    return {
        "id": row["id"],
        "role": row["role"],
        "content": _safe_message_content(row["content"] or "", status, row["role"]),
        "msgType": row["msg_type"] or "text",
        "payload": _json_loads(row["payload_json"]),
        "usage": _json_loads(row["usage_json"]),
        "usageModel": row["usage_model"],
        "usageCost": row["usage_cost"],
        "elapsedSec": row["elapsed_sec"],
        "reasoningSummary": row["reasoning_summary"],
        "reasoningStatus": row["reasoning_status"],
        "status": status,
        "createdAt": row["created_at"],
    }


def session_detail(conn: sqlite3.Connection, session_id: str, load_prompt_presets) -> dict | None:
    session_row = conn.execute(
        """
        SELECT id, title, use_case, summary, summary_message_id, custom_prompt, custom_context, prompt_preset_id, created_at, updated_at
        FROM sessions
        WHERE id = ?
        """,
        (session_id,),
    ).fetchone()
    if not session_row:
        return None

    message_rows = conn.execute(
        """
        SELECT id, role, content, msg_type, payload_json, usage_json, usage_model, usage_cost, elapsed_sec, reasoning_summary, reasoning_status, status, created_at
        FROM messages
        WHERE session_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (session_id,),
    ).fetchall()

    attachment_rows = conn.execute(
        """
        SELECT id, name, mime_type, size_bytes, active, availability, extraction_status, created_at, updated_at
        FROM attachments
        WHERE session_id = ?
        ORDER BY created_at ASC, id ASC
        """,
        (session_id,),
    ).fetchall()

    presets = load_prompt_presets()
    normalized_prompt_preset_id = resolve_prompt_preset_id(session_row["prompt_preset_id"] or "", presets)

    normalized_use_case = normalize_use_case(session_row["use_case"], use_case_keys())
    prompt_enabled = use_case_supports_prompt_setup(normalized_use_case)

    return {
        "id": session_row["id"],
        "title": session_row["title"],
        "useCase": normalized_use_case,
        "summary": session_row["summary"] or "",
        "summaryMessageId": session_row["summary_message_id"],
        "prompt": (session_row["custom_prompt"] or "") if prompt_enabled else "",
        "context": (session_row["custom_context"] or "") if prompt_enabled else "",
        "promptPresetId": normalized_prompt_preset_id if prompt_enabled else "",
        "createdAt": session_row["created_at"],
        "updatedAt": session_row["updated_at"],
        "messages": [serialize_message_row(row) for row in message_rows],
        "attachments": [serialize_attachment_record(row) for row in attachment_rows],
    }


def session_selected_model(session_payload: dict, fallback_model: str) -> str:
    for message in reversed(session_payload.get("messages") or []):
        if message.get("role") != "assistant":
            continue
        model = str(message.get("usageModel") or "").strip()
        if model:
            return model
    return fallback_model


def assistant_response_ordinal(conn: sqlite3.Connection, session_id: str, message_id: int) -> int:
    row = conn.execute(
        """
        SELECT COUNT(*) AS count_value
        FROM messages
        WHERE session_id = ? AND role = 'assistant' AND msg_type = 'text' AND id <= ?
        """,
        (session_id, message_id),
    ).fetchone()
    count_value = int((row["count_value"] if row else 0) or 0)
    return max(1, count_value)


def ensure_schema(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY,
          title TEXT NOT NULL,
          use_case TEXT NOT NULL,
          archived_at INTEGER,
          summary TEXT NOT NULL DEFAULT '',
          summary_message_id INTEGER,
          custom_prompt TEXT NOT NULL DEFAULT '',
          custom_context TEXT NOT NULL DEFAULT '',
          prompt_preset_id TEXT NOT NULL DEFAULT '',
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT NOT NULL,
          role TEXT NOT NULL,
          content TEXT NOT NULL,
          msg_type TEXT NOT NULL DEFAULT 'text',
          payload_json TEXT,
          usage_json TEXT,
          usage_model TEXT,
          usage_cost REAL,
          elapsed_sec REAL,
          reasoning_summary TEXT,
          reasoning_status TEXT,
          status TEXT NOT NULL DEFAULT 'complete',
          created_at INTEGER NOT NULL,
          FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_session_created
          ON messages(session_id, created_at, id);

        CREATE INDEX IF NOT EXISTS idx_messages_role_created
          ON messages(role, created_at, id);

        CREATE INDEX IF NOT EXISTS idx_messages_role_session_created
          ON messages(role, session_id, created_at, id);

        CREATE TABLE IF NOT EXISTS attachments (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          name TEXT NOT NULL,
          mime_type TEXT NOT NULL,
          local_path TEXT,
          extracted_text TEXT,
          size_bytes INTEGER NOT NULL DEFAULT 0,
          active INTEGER NOT NULL DEFAULT 1,
          availability TEXT NOT NULL DEFAULT 'ready',
          extraction_status TEXT NOT NULL DEFAULT 'unsupported',
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL,
          FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_attachments_session_created
          ON attachments(session_id, created_at, id);

        CREATE TABLE IF NOT EXISTS image_projects (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          updated_at INTEGER NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_image_projects_updated
          ON image_projects(updated_at DESC, created_at DESC);

        CREATE TABLE IF NOT EXISTS file_embeddings (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          session_id TEXT NOT NULL,
          attachment_id TEXT NOT NULL,
          attachment_name TEXT NOT NULL,
          model TEXT NOT NULL,
          chunk_index INTEGER NOT NULL,
          chunk_text TEXT NOT NULL,
          embedding_json TEXT NOT NULL,
          created_at INTEGER NOT NULL,
          FOREIGN KEY(session_id) REFERENCES sessions(id) ON DELETE CASCADE,
          FOREIGN KEY(attachment_id) REFERENCES attachments(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_file_embeddings_session_model
          ON file_embeddings(session_id, model, id);

        CREATE INDEX IF NOT EXISTS idx_file_embeddings_attachment
          ON file_embeddings(attachment_id, model, id);

        CREATE TABLE IF NOT EXISTS rate_limit_windows (
          bucket TEXT NOT NULL,
          limiter_key TEXT NOT NULL,
          window_start_sec INTEGER NOT NULL,
          count INTEGER NOT NULL DEFAULT 0,
          expires_at_sec INTEGER NOT NULL,
          updated_at_sec INTEGER NOT NULL,
          PRIMARY KEY(bucket, limiter_key, window_start_sec)
        );

        CREATE INDEX IF NOT EXISTS idx_rate_limit_windows_expires
          ON rate_limit_windows(expires_at_sec);

        CREATE INDEX IF NOT EXISTS idx_rate_limit_windows_lookup
          ON rate_limit_windows(bucket, limiter_key, window_start_sec);
        """
    )
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
    if "elapsed_sec" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN elapsed_sec REAL")
    if "reasoning_summary" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN reasoning_summary TEXT")
    if "reasoning_status" not in columns:
        conn.execute("ALTER TABLE messages ADD COLUMN reasoning_status TEXT")
    session_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()}
    if "custom_prompt" not in session_columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN custom_prompt TEXT NOT NULL DEFAULT ''")
    if "custom_context" not in session_columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN custom_context TEXT NOT NULL DEFAULT ''")
    if "prompt_preset_id" not in session_columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN prompt_preset_id TEXT NOT NULL DEFAULT ''")
    if "archived_at" not in session_columns:
        conn.execute("ALTER TABLE sessions ADD COLUMN archived_at INTEGER")


def insert_session(
    conn: sqlite3.Connection,
    session_id: str,
    use_case: str,
    title: str = "New chat",
    created_at: int | None = None,
):
    timestamp = created_at or _now_ms()
    conn.execute(
        """
        INSERT OR IGNORE INTO sessions (id, title, use_case, summary, summary_message_id, created_at, updated_at)
        VALUES (?, ?, ?, '', NULL, ?, ?)
        """,
        (session_id, title or "New chat", use_case or "general", timestamp, timestamp),
    )


def ensure_session(conn: sqlite3.Connection, session_id: str, use_case: str):
    row = conn.execute(
        "SELECT id, use_case, created_at FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE sessions SET use_case = ?, updated_at = ? WHERE id = ?",
            (use_case or row["use_case"], _now_ms(), session_id),
        )
        return
    insert_session(conn, session_id, use_case or "general")


def refresh_session_title(conn: sqlite3.Connection, session_id: str):
    session_row = conn.execute(
        "SELECT title FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    current_title = (session_row["title"] or "").strip() if session_row else ""
    if current_title and current_title != "New chat":
        return

    row = conn.execute(
        """
        SELECT content
        FROM messages
        WHERE session_id = ? AND role = 'user'
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (session_id,),
    ).fetchone()
    title = _derive_title(row["content"] if row else "")
    conn.execute(
        "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
        (title, _now_ms(), session_id),
    )


def insert_message(
    conn: sqlite3.Connection,
    session_id: str,
    role: str,
    content: str,
    msg_type: str = "text",
    payload=None,
    usage=None,
    usage_model=None,
    usage_cost=None,
    elapsed_sec=None,
    reasoning_summary=None,
    reasoning_status=None,
    status: str = "complete",
    created_at: int | None = None,
):
    timestamp = created_at or _now_ms()
    cursor = conn.execute(
        """
        INSERT INTO messages
          (session_id, role, content, msg_type, payload_json, usage_json, usage_model, usage_cost, elapsed_sec, reasoning_summary, reasoning_status, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id,
            role,
            content or "",
            msg_type or "text",
            _json_dumps(payload),
            _json_dumps(usage),
            usage_model,
            usage_cost,
            elapsed_sec,
            reasoning_summary,
            reasoning_status,
            status or "complete",
            timestamp,
        ),
    )
    conn.execute(
        "UPDATE sessions SET updated_at = ? WHERE id = ?",
        (_now_ms(), session_id),
    )
    return cursor.lastrowid


def update_message(
    conn: sqlite3.Connection,
    message_id: int,
    *,
    content=None,
    msg_type=None,
    payload=None,
    usage=None,
    usage_model=None,
    usage_cost=None,
    elapsed_sec=None,
    reasoning_summary=None,
    reasoning_status=None,
    status=None,
):
    updates = []
    values = []
    if content is not None:
        updates.append("content = ?")
        values.append(content)
    if msg_type is not None:
        updates.append("msg_type = ?")
        values.append(msg_type or "text")
    if payload is not None:
        updates.append("payload_json = ?")
        values.append(_json_dumps(payload))
    if usage is not None:
        updates.append("usage_json = ?")
        values.append(_json_dumps(usage))
    if usage_model is not None:
        updates.append("usage_model = ?")
        values.append(usage_model)
    if usage_cost is not None:
        updates.append("usage_cost = ?")
        values.append(usage_cost)
    if elapsed_sec is not None:
        updates.append("elapsed_sec = ?")
        values.append(elapsed_sec)
    if reasoning_summary is not None:
        updates.append("reasoning_summary = ?")
        values.append(reasoning_summary)
    if reasoning_status is not None:
        updates.append("reasoning_status = ?")
        values.append(reasoning_status)
    if status is not None:
        updates.append("status = ?")
        values.append(status)
    if not updates:
        return
    values.append(message_id)
    conn.execute(
        f"UPDATE messages SET {', '.join(updates)} WHERE id = ?",
        tuple(values),
    )


def session_messages_before(conn: sqlite3.Connection, session_id: str, before_id: int | None = None) -> list[dict]:
    params = [session_id]
    clause = ""
    if before_id is not None:
        clause = "AND id < ?"
        params.append(before_id)
    rows = conn.execute(
        f"""
        SELECT id, role, content, msg_type, payload_json, usage_json, usage_model, usage_cost, elapsed_sec, reasoning_summary, reasoning_status, status, created_at
        FROM messages
        WHERE session_id = ? {clause}
        ORDER BY created_at ASC, id ASC
        """,
        tuple(params),
    ).fetchall()

    serialized = []
    for row in rows:
        message = serialize_message_row(row)
        if message["role"] == "assistant" and message["status"] in {"pending", "error"}:
            continue
        serialized.append(message)
    return serialized
