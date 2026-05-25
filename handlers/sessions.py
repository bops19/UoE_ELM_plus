"""Handlers for /sessions/* and /prompt-presets/* and /usage/history endpoints."""

import json
import os
import shutil
import uuid
from pathlib import Path

from flask import Response, request, send_file

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
from model_catalog import use_case_keys
from prompt_presets_store import find_prompt_preset, load_prompt_presets, write_prompt_presets
from prompt_session_service import (
    normalize_preset_name,
    normalize_session_text,
    normalize_session_update,
    normalize_use_case,
)
from session_store import (
    assistant_response_ordinal,
    ensure_session,
    session_detail,
    session_selected_model,
)
from usage_history import build_usage_history_payload, model_usage_breakdown
from vm_service import build_session_view
from pdf_to_markdown_service import convert_pdf_to_markdown_bundle

from handler_dependencies import (
    ATTACHMENTS_DIR,
    PROMPT_PRESETS_FILE,
    SUMMARY_MODEL,
    _apply_session_retention,
    _db,
    _error_response,
    _now_ms,
    _refresh_attachment_extraction_if_possible,
    _remove_session_files,
    _store_attachment,
    _validated_json_body,
)


def get_sessions():
    with _db() as conn:
        _apply_session_retention(conn)
        rows = conn.execute(
            """
            SELECT
              s.id,
              s.title,
              s.use_case,
              s.archived_at,
              s.created_at,
              s.updated_at,
              COALESCE((SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id AND m.role = 'user'), 0) AS message_count,
              COALESCE((SELECT COUNT(*) FROM attachments a WHERE a.session_id = s.id), 0) AS attachment_count
            FROM sessions s
            ORDER BY s.updated_at DESC, s.created_at DESC
            """
        ).fetchall()

    sessions = [
        {
            "id": row["id"],
            "title": row["title"],
            "useCase": normalize_use_case(row["use_case"], use_case_keys()),
            "archivedAt": row["archived_at"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "messageCount": row["message_count"],
            "attachmentCount": row["attachment_count"],
        }
        for row in rows
    ]
    return {"sessions": sessions}


def get_session_detail(session_id):
    with _db() as conn:
        attachment_rows = conn.execute(
            "SELECT * FROM attachments WHERE session_id = ? ORDER BY created_at ASC, id ASC",
            (session_id,),
        ).fetchall()
        for row in attachment_rows:
            _refresh_attachment_extraction_if_possible(conn, row)
        conn.commit()
        detail = session_detail(conn, session_id, load_prompt_presets=lambda: load_prompt_presets(PROMPT_PRESETS_FILE))
    if not detail:
        return _error_response("session not found", 404, "session_not_found")
    return {"session": detail, "sessionView": build_session_view(detail)}


def export_session(session_id):
    export_format = normalize_export_format(request.args.get("format"), default_value="md")
    with _db() as conn:
        detail = session_detail(conn, session_id, load_prompt_presets=lambda: load_prompt_presets(PROMPT_PRESETS_FILE))
    if not detail:
        return _error_response("session not found", 404, "session_not_found")

    preset = find_prompt_preset(PROMPT_PRESETS_FILE, detail.get("promptPresetId") or "")
    selected_model = session_selected_model(detail, fallback_model=SUMMARY_MODEL)
    if export_format == "txt":
        content = render_session_text(detail, preset=preset, selected_model=selected_model)
    else:
        content = render_session_markdown(detail, preset=preset, selected_model=selected_model)
    filename = session_export_filename(detail.get("title") or "new-chat", export_format)

    return Response(
        content,
        mimetype=export_mime_type(export_format),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def export_assistant_message(session_id, message_id: int):
    export_format = normalize_export_format(request.args.get("format"), default_value="md")
    with _db() as conn:
        message = conn.execute(
            """
            SELECT id, role, msg_type, content, payload_json
            FROM messages
            WHERE session_id = ? AND id = ?
            """,
            (session_id, message_id),
        ).fetchone()
        if not message:
            return _error_response("message not found", 404, "message_not_found")
        if message["role"] != "assistant" or (message["msg_type"] or "text") != "text":
            return _error_response(
                "message is not an exportable assistant text response",
                400,
                "message_not_exportable",
            )
        session_row = conn.execute(
            "SELECT title FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        response_number = assistant_response_ordinal(conn, session_id, message_id)

    content_value = message["content"] or ""
    payload_value = json.loads(message["payload_json"]) if message["payload_json"] else None
    content = (
        render_response_text(content_value, payload_value)
        if export_format == "txt"
        else render_response_markdown(content_value, payload_value)
    )
    filename = response_export_filename(
        session_title=(session_row["title"] if session_row else "new-chat"),
        response_number=response_number,
        export_format=export_format,
    )
    return Response(
        content,
        mimetype=export_mime_type(export_format),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def get_usage_history():
    session_id = (request.args.get("sessionId") or "").strip()
    date_value = (request.args.get("date") or "").strip() or None

    try:
        with _db() as conn:
            return build_usage_history_payload(conn, session_id=session_id or None, date_value=date_value)
    except ValueError:
        return _error_response("invalid date", 400, "invalid_date")


def get_usage_model_breakdown():
    session_id = (request.args.get("sessionId") or "").strip() or None
    date_value = (request.args.get("date") or "").strip() or None
    scope = (request.args.get("scope") or "today").strip() or "today"
    model = (request.args.get("model") or "").strip()

    try:
        with _db() as conn:
            return model_usage_breakdown(
                conn,
                scope=scope,
                model=model,
                session_id=session_id,
                date_value=date_value,
            )
    except ValueError as exc:
        code = str(exc)
        if code == "missing_model":
            return _error_response("model is required", 400, "missing_model")
        if code == "session_required":
            return _error_response("sessionId is required for scope=session", 400, "session_required")
        if code == "invalid_scope":
            return _error_response("invalid scope", 400, "invalid_scope")
        return _error_response("invalid request", 400, "invalid_request")


def update_session(session_id):
    data = request.json or {}

    with _db() as conn:
        existing = conn.execute(
            "SELECT title, use_case, custom_prompt, custom_context, prompt_preset_id FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        presets = load_prompt_presets(PROMPT_PRESETS_FILE)
        normalized = normalize_session_update(
            request_data=data,
            existing=existing,
            allowed_use_cases=use_case_keys(),
            presets=presets,
        )
        ensure_session(conn, session_id, normalized["useCase"])
        conn.execute(
            """
            UPDATE sessions
            SET title = ?, use_case = ?, custom_prompt = ?, custom_context = ?, prompt_preset_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                normalized["title"],
                normalized["useCase"],
                normalized["prompt"],
                normalized["context"],
                normalized["promptPresetId"],
                _now_ms(),
                session_id,
            ),
        )
        conn.commit()
        detail = session_detail(conn, session_id, load_prompt_presets=lambda: load_prompt_presets(PROMPT_PRESETS_FILE))

    return {"session": detail, "sessionView": build_session_view(detail)}


def get_prompt_presets():
    return {"presets": load_prompt_presets(PROMPT_PRESETS_FILE)}


def create_prompt_preset():
    data = request.json or {}
    name = normalize_preset_name(data.get("name"))
    instructions = normalize_session_text(data.get("instructions"))
    context = normalize_session_text(data.get("context"))
    if not name or not (instructions or context):
        return _error_response(
            "name and either instructions or context are required",
            400,
            "prompt_preset_invalid_payload",
        )

    now = _now_ms()
    preset = {
        "id": uuid.uuid4().hex,
        "name": name,
        "instructions": instructions,
        "context": context,
        "createdAt": now,
        "updatedAt": now,
    }
    presets = load_prompt_presets(PROMPT_PRESETS_FILE)
    presets.append(preset)
    write_prompt_presets(PROMPT_PRESETS_FILE, presets)
    return {"preset": preset}


def update_prompt_preset(preset_id):
    data = request.json or {}
    presets = load_prompt_presets(PROMPT_PRESETS_FILE)
    updated_preset = None

    for preset in presets:
        if preset["id"] != preset_id:
            continue
        next_name = normalize_preset_name(data.get("name", preset["name"]))
        next_instructions = normalize_session_text(data.get("instructions", preset["instructions"]))
        next_context = normalize_session_text(data.get("context", preset.get("context", "")))
        if not next_name or not (next_instructions or next_context):
            return _error_response(
                "name and either instructions or context are required",
                400,
                "prompt_preset_invalid_payload",
            )
        preset["name"] = next_name
        preset["instructions"] = next_instructions
        preset["context"] = next_context
        preset["updatedAt"] = _now_ms()
        updated_preset = dict(preset)
        break

    if not updated_preset:
        return _error_response("prompt preset not found", 404, "prompt_preset_not_found")

    write_prompt_presets(PROMPT_PRESETS_FILE, presets)
    return {"preset": updated_preset}


def delete_prompt_preset(preset_id):
    presets = load_prompt_presets(PROMPT_PRESETS_FILE)
    remaining = [preset for preset in presets if preset["id"] != preset_id]
    if len(remaining) == len(presets):
        return _error_response("prompt preset not found", 404, "prompt_preset_not_found")
    write_prompt_presets(PROMPT_PRESETS_FILE, remaining)
    return {"ok": True}


def delete_session(session_id):
    with _db() as conn:
        conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        conn.execute("DELETE FROM file_embeddings WHERE session_id = ?", (session_id,))
        conn.commit()
    session_dir = os.path.join(ATTACHMENTS_DIR, session_id)
    if os.path.isdir(session_dir):
        shutil.rmtree(session_dir, ignore_errors=True)
    return {"ok": True}


def clear_session(session_id):
    now = _now_ms()
    with _db() as conn:
        existing = conn.execute(
            "SELECT id, use_case, archived_at, created_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not existing:
            return _error_response("session not found", 404, "session_not_found")
        conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM attachments WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM file_embeddings WHERE session_id = ?", (session_id,))
        conn.execute(
            """
            UPDATE sessions
            SET title = ?, summary = '', summary_message_id = NULL,
                custom_prompt = '', custom_context = '', prompt_preset_id = '',
                updated_at = ?
            WHERE id = ?
            """,
            ("New chat", now, session_id),
        )
        conn.commit()
        detail = session_detail(conn, session_id, load_prompt_presets=lambda: load_prompt_presets(PROMPT_PRESETS_FILE))
    _remove_session_files([session_id])
    return {"ok": True, "session": detail, "sessionView": build_session_view(detail)}


def archive_session(session_id):
    data, err = _validated_json_body(
        allowed_keys={"archived"},
        required_keys={"archived"},
    )
    if err:
        return err
    archived_value = data.get("archived")
    if not isinstance(archived_value, bool):
        return _error_response("archived must be a boolean", 400, "session_archive_invalid_flag")
    now = _now_ms()
    with _db() as conn:
        existing = conn.execute(
            "SELECT id, archived_at FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if not existing:
            return _error_response("session not found", 404, "session_not_found")
        next_archived_at = now if archived_value else None
        if archived_value and existing["archived_at"]:
            return {"ok": True, "archivedAt": existing["archived_at"]}
        if (not archived_value) and existing["archived_at"] is None:
            return {"ok": True, "archivedAt": None}
        conn.execute(
            "UPDATE sessions SET archived_at = ?, updated_at = ? WHERE id = ?",
            (next_archived_at, now, session_id),
        )
        conn.commit()
    return {"ok": True, "archivedAt": next_archived_at}


def upload_attachments(session_id):
    files = request.files.getlist("files")
    use_case = request.form.get("useCase", "general")
    if not files:
        return _error_response("no files uploaded", 400, "attachments_required")

    with _db() as conn:
        ensure_session(conn, session_id, use_case)
        for file_storage in files:
            _store_attachment(conn, session_id, file_storage)
        conn.commit()
        detail = session_detail(conn, session_id, load_prompt_presets=lambda: load_prompt_presets(PROMPT_PRESETS_FILE))

    return {"session": detail, "sessionView": build_session_view(detail)}


def _create_markdown_attachment_from_row(conn, session_id: str, row) -> str:
    name = str(row["name"] or "")
    local_path = str(row["local_path"] or "")
    markdown_id = uuid.uuid4().hex
    markdown_name = f"{os.path.splitext(name)[0]}.md"
    safe_name = os.path.basename(markdown_name) or "document.md"
    session_dir = os.path.join(ATTACHMENTS_DIR, session_id)
    os.makedirs(session_dir, exist_ok=True)
    bundle_dir = os.path.join(session_dir, f"{markdown_id}_bundle")
    os.makedirs(bundle_dir, exist_ok=True)
    bundle = convert_pdf_to_markdown_bundle(
        Path(local_path),
        output_dir=Path(bundle_dir),
        force_mode="auto",
        ocr_lang="eng",
    )
    markdown_text = bundle.markdown_text
    target_dir = str(bundle.output_dir or Path(bundle_dir))
    os.makedirs(target_dir, exist_ok=True)
    markdown_path = os.path.join(target_dir, safe_name)
    with open(markdown_path, "w", encoding="utf-8") as md_file:
        md_file.write(markdown_text)

    timestamp = _now_ms()
    conn.execute(
        """
        INSERT INTO attachments
          (id, session_id, name, mime_type, local_path, extracted_text, size_bytes, active, availability, extraction_status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            markdown_id,
            session_id,
            safe_name,
            "text/markdown",
            markdown_path,
            markdown_text,
            len(markdown_text.encode("utf-8")),
            1,
            "ready",
            "extracted",
            timestamp,
            timestamp,
        ),
    )
    return markdown_id


def create_markdown_attachment(session_id):
    data, err = _validated_json_body(
        allowed_keys={"attachmentId", "attachmentIds", "useCase"},
    )
    if err:
        return err
    attachment_id = str(data.get("attachmentId") or "").strip()
    attachment_ids = data.get("attachmentIds")
    ids: list[str] = []
    if isinstance(attachment_ids, list):
        ids = [str(item or "").strip() for item in attachment_ids if str(item or "").strip()]
    if not ids and attachment_id:
        ids = [attachment_id]
    use_case = str(data.get("useCase") or "general").strip() or "general"
    if not ids:
        return _error_response("attachmentId or attachmentIds is required", 400, "attachment_id_required")

    with _db() as conn:
        ensure_session(conn, session_id, use_case)
        placeholders = ",".join("?" for _ in ids)
        rows = conn.execute(
            f"""
            SELECT id, name, mime_type, local_path
            FROM attachments
            WHERE session_id = ? AND id IN ({placeholders})
            """,
            (session_id, *ids),
        ).fetchall()
        if not rows:
            return _error_response("attachment not found", 404, "attachment_not_found")
        by_id = {str(row["id"]): row for row in rows}
        ordered_rows = [by_id[attachment_id] for attachment_id in ids if attachment_id in by_id]
        if not ordered_rows:
            return _error_response("attachment not found", 404, "attachment_not_found")

        created_count = 0
        failures: list[dict] = []
        for row in ordered_rows:
            row_id = str(row["id"] or "")
            name = str(row["name"] or "")
            mime_type = str(row["mime_type"] or "").lower()
            local_path = str(row["local_path"] or "")
            if (not name.lower().endswith(".pdf") and mime_type != "application/pdf"):
                failures.append({"attachmentId": row_id, "name": name, "error": "not_pdf"})
                continue
            if not local_path or not os.path.exists(local_path):
                failures.append({"attachmentId": row_id, "name": name, "error": "missing_file"})
                continue
            try:
                _create_markdown_attachment_from_row(conn, session_id, row)
                created_count += 1
            except Exception as exc:
                failures.append({"attachmentId": row_id, "name": name, "error": str(exc)})
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_now_ms(), session_id),
        )
        conn.commit()
        detail = session_detail(conn, session_id, load_prompt_presets=lambda: load_prompt_presets(PROMPT_PRESETS_FILE))
    return {
        "session": detail,
        "sessionView": build_session_view(detail),
        "createdCount": created_count,
        "requestedCount": len(ids),
        "failures": failures,
    }


def download_attachment(session_id, attachment_id):
    with _db() as conn:
        row = conn.execute(
            """
            SELECT name, mime_type, local_path
            FROM attachments
            WHERE session_id = ? AND id = ?
            """,
            (session_id, attachment_id),
        ).fetchone()
    if not row:
        return _error_response("attachment not found", 404, "attachment_not_found")
    local_path = str(row["local_path"] or "")
    if not local_path or not os.path.exists(local_path):
        return _error_response("attachment file missing", 404, "attachment_missing_file")
    return send_file(
        local_path,
        as_attachment=True,
        download_name=str(row["name"] or "attachment.bin"),
        mimetype=str(row["mime_type"] or "application/octet-stream"),
    )


def update_attachment(session_id, attachment_id):
    data = request.json or {}
    active = 1 if data.get("active") else 0
    with _db() as conn:
        conn.execute(
            """
            UPDATE attachments
            SET active = ?, updated_at = ?
            WHERE session_id = ? AND id = ?
            """,
            (active, _now_ms(), session_id, attachment_id),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_now_ms(), session_id),
        )
        conn.commit()
    return {"ok": True}


def delete_attachment(session_id, attachment_id):
    with _db() as conn:
        row = conn.execute(
            "SELECT local_path FROM attachments WHERE session_id = ? AND id = ?",
            (session_id, attachment_id),
        ).fetchone()
        conn.execute(
            "DELETE FROM attachments WHERE session_id = ? AND id = ?",
            (session_id, attachment_id),
        )
        conn.execute(
            "DELETE FROM file_embeddings WHERE session_id = ? AND attachment_id = ?",
            (session_id, attachment_id),
        )
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_now_ms(), session_id),
        )
        conn.commit()

    if row and row["local_path"] and os.path.exists(row["local_path"]):
        try:
            os.remove(row["local_path"])
        except OSError:
            pass

    return {"ok": True}
