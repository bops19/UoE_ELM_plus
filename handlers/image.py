"""Handlers for image generation, editing, and project metadata endpoints.

These handlers were registered directly via ``@app.route`` in the original
monolith. They are now plain functions; ``app.py`` binds them with
``app.add_url_rule`` near the bottom of the module.
"""

import io
import json
import re
import uuid

from flask import request

from prompt_session_service import normalize_session_text
from session_store import insert_message, update_message

from handler_dependencies import (
    IMAGE_EDIT_ALLOWED_MIME,
    IMAGE_EDIT_MAX_BYTES,
    IMAGE_MODERATION_LEVELS,
    IMAGE_OUTPUT_COUNTS,
    IMAGE_PROMPT_MAX_CHARS,
    IMAGE_SIZE_MAP,
    IMAGE_STYLE_GUIDANCE,
    OPENAI_TIMEOUT_SEC,
    REQUEST_BODY_MAX_BYTES,
    _check_rate_limit,
    _compose_image_prompt,
    _db,
    _decode_generated_images,
    _error_response,
    _mapped_size_dimensions,
    _now_ms,
    _openai_client,
    _reject_oversized_multipart,
    _safe_openai_call,
    _security_log,
    _single_shot_interaction,
    _validated_json_body,
    divider,
    log,
)


def update_image_message_meta(session_id, message_id: int):
    limited = _check_rate_limit("image_meta_mutation")
    if limited:
        return limited
    data, err = _validated_json_body(
        allowed_keys={"favorite", "hiddenInWorkspace", "projectId"},
    )
    if err:
        return err
    has_favorite = "favorite" in data
    has_hidden = "hiddenInWorkspace" in data
    has_project = "projectId" in data
    if not has_favorite and not has_hidden and not has_project:
        return _error_response(
            "at least one of favorite, hiddenInWorkspace, or projectId is required",
            400,
            "image_meta_patch_required",
        )
    if has_favorite and not isinstance(data.get("favorite"), bool):
        return _error_response("favorite must be a boolean", 400, "image_meta_invalid_favorite")
    if has_hidden and not isinstance(data.get("hiddenInWorkspace"), bool):
        return _error_response("hiddenInWorkspace must be a boolean", 400, "image_meta_invalid_hidden")
    if has_project and data.get("projectId") is not None and not isinstance(data.get("projectId"), str):
        return _error_response("projectId must be a string or null", 400, "image_meta_invalid_project_id")

    with _db() as conn:
        project_id = None
        if has_project and isinstance(data.get("projectId"), str):
            project_id = normalize_session_text(data.get("projectId"))
            if not project_id:
                project_id = None
            else:
                project_row = conn.execute(
                    "SELECT id FROM image_projects WHERE id = ?",
                    (project_id,),
                ).fetchone()
                if not project_row:
                    return _error_response("project not found", 404, "project_not_found")

        row = conn.execute(
            """
            SELECT id, role, msg_type, payload_json
            FROM messages
            WHERE session_id = ? AND id = ?
            """,
            (session_id, message_id),
        ).fetchone()
        if not row:
            return _error_response("message not found", 404, "message_not_found")
        if row["role"] != "assistant" or (row["msg_type"] or "text") != "image":
            return _error_response("message is not an assistant image", 400, "image_meta_target_invalid")

        payload = {}
        if row["payload_json"]:
            try:
                payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                payload = {}
        if not isinstance(payload, dict):
            payload = {}

        if has_favorite:
            payload["favorite"] = bool(data.get("favorite"))
        if has_hidden:
            payload["hiddenInWorkspace"] = bool(data.get("hiddenInWorkspace"))
        if has_project:
            payload["projectId"] = project_id

        if row["payload_json"]:
            try:
                existing_payload = json.loads(row["payload_json"])
            except (TypeError, json.JSONDecodeError):
                existing_payload = {}
            if isinstance(existing_payload, dict):
                unchanged = True
                if has_favorite and bool(existing_payload.get("favorite")) != bool(payload.get("favorite")):
                    unchanged = False
                if has_hidden and bool(existing_payload.get("hiddenInWorkspace")) != bool(payload.get("hiddenInWorkspace")):
                    unchanged = False
                if has_project and existing_payload.get("projectId") != payload.get("projectId"):
                    unchanged = False
                if unchanged:
                    return {"ok": True, "payload": existing_payload}

        update_message(conn, message_id, payload=payload)
        conn.execute(
            "UPDATE sessions SET updated_at = ? WHERE id = ?",
            (_now_ms(), session_id),
        )
        conn.commit()

    return {"ok": True, "payload": payload}


def get_image_projects():
    with _db() as conn:
        rows = conn.execute(
            """
            SELECT id, name, created_at, updated_at
            FROM image_projects
            ORDER BY updated_at DESC, created_at DESC, id DESC
            """
        ).fetchall()
    projects = [
        {
            "id": row["id"],
            "name": row["name"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }
        for row in rows
    ]
    return {"projects": projects}


def create_image_project():
    limited = _check_rate_limit("project_mutation")
    if limited:
        return limited
    data, err = _validated_json_body(allowed_keys={"name"}, required_keys={"name"})
    if err:
        return err
    name = normalize_session_text(data.get("name"))
    if not name:
        return _error_response("name is required", 400, "image_project_name_required")
    now = _now_ms()
    project_id = uuid.uuid4().hex
    with _db() as conn:
        conn.execute(
            """
            INSERT INTO image_projects (id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, name, now, now),
        )
        conn.commit()
    return {"project": {"id": project_id, "name": name, "createdAt": now, "updatedAt": now}}, 201


def rename_image_project(project_id: str):
    limited = _check_rate_limit("project_mutation")
    if limited:
        return limited
    data, err = _validated_json_body(allowed_keys={"name"}, required_keys={"name"})
    if err:
        return err
    name = normalize_session_text(data.get("name"))
    if not name:
        return _error_response("name is required", 400, "image_project_name_required")
    now = _now_ms()
    with _db() as conn:
        existing = conn.execute(
            "SELECT id, name, created_at, updated_at FROM image_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if not existing:
            return _error_response("project not found", 404, "project_not_found")
        current_name = normalize_session_text(existing["name"])
        if current_name == name:
            return {"project": {"id": project_id, "name": name, "createdAt": existing["created_at"], "updatedAt": existing["updated_at"]}}
        conn.execute(
            "UPDATE image_projects SET name = ?, updated_at = ? WHERE id = ?",
            (name, now, project_id),
        )
        conn.commit()
    return {"project": {"id": project_id, "name": name, "createdAt": existing["created_at"], "updatedAt": now}}


def delete_image_project(project_id: str):
    limited = _check_rate_limit("project_mutation")
    if limited:
        return limited
    with _db() as conn:
        existing = conn.execute(
            "SELECT id FROM image_projects WHERE id = ?",
            (project_id,),
        ).fetchone()
        if not existing:
            return _error_response("project not found", 404, "project_not_found")

        rows = conn.execute(
            """
            SELECT id, payload_json
            FROM messages
            WHERE role = 'assistant' AND msg_type = 'image'
            """
        ).fetchall()
        for row in rows:
            payload = {}
            if row["payload_json"]:
                try:
                    payload = json.loads(row["payload_json"])
                except (TypeError, json.JSONDecodeError):
                    payload = {}
            if not isinstance(payload, dict):
                continue
            if payload.get("projectId") != project_id:
                continue
            payload["projectId"] = None
            update_message(conn, row["id"], payload=payload)

        conn.execute("DELETE FROM image_projects WHERE id = ?", (project_id,))
        conn.commit()
    return {"ok": True}


def generate_image():
    limited = _check_rate_limit("image")
    if limited:
        return limited
    data, err = _validated_json_body(
        allowed_keys={"sessionId", "useCase", "model", "prompt", "moderation", "style", "size", "count", "actionOrigin"},
        required_keys={"sessionId", "prompt"},
    )
    if err:
        return err
    session_id = normalize_session_text(data.get("sessionId"))
    if not session_id:
        return _error_response("sessionId is required", 400, "image_session_required")
    use_case = data.get("useCase", "image")
    model = data.get("model", "gpt-image-1")
    prompt = normalize_session_text(data.get("prompt", ""))
    moderation = normalize_session_text(data.get("moderation", "auto")) or "auto"
    style = normalize_session_text(data.get("style", "photorealistic")) or "photorealistic"
    size_key = normalize_session_text(data.get("size", "square")) or "square"
    try:
        count = int(data.get("count", 1))
    except (TypeError, ValueError):
        count = -1
    if not prompt:
        return _error_response("prompt is required", 400, "image_prompt_required")
    if len(prompt) > IMAGE_PROMPT_MAX_CHARS:
        return _error_response(
            f"prompt must be {IMAGE_PROMPT_MAX_CHARS} characters or fewer",
            400,
            "image_prompt_too_long",
        )
    if moderation not in IMAGE_MODERATION_LEVELS:
        return _error_response("moderation must be one of: auto, low", 400, "image_invalid_moderation")
    if style not in IMAGE_STYLE_GUIDANCE:
        return _error_response(
            "style must be one of: photorealistic, illustration, 3d_render, poster, minimal",
            400,
            "image_invalid_style",
        )
    if size_key not in IMAGE_SIZE_MAP:
        return _error_response("size must be one of: square, portrait, landscape", 400, "image_invalid_size")
    if count not in IMAGE_OUTPUT_COUNTS:
        return _error_response("count must be one of: 1, 2, 4", 400, "image_invalid_count")

    assistant_message_id, prompt = _single_shot_interaction(session_id, use_case, prompt)
    generation_prompt = _compose_image_prompt(prompt, style)
    openai_size = IMAGE_SIZE_MAP[size_key]
    width = None
    height = None
    size_match = re.match(r"^(\d+)x(\d+)$", openai_size)
    if size_match:
        width = int(size_match.group(1))
        height = int(size_match.group(2))
    retry_payload = {
        "imageRequest": {
            "retryable": True,
            "prompt": prompt,
            "model": model,
            "moderation": moderation,
            "style": style,
            "size": size_key,
            "count": count,
        },
        "errorCode": "image_generation_failed",
    }
    divider()
    log("🖼️ ", "IMAGE GEN  ", f"model={model}")
    log("📝", "PROMPT     ", f'"{prompt[:80]}{"..." if len(prompt) > 80 else ""}"')
    log("🎨", "IMG STYLE  ", style)
    log("📐", "IMG SIZE   ", f"{size_key} -> {openai_size}")
    log("🧮", "IMG COUNT  ", str(count))
    print("─" * 60, flush=True)
    provider_error_response = None
    try:
        image_payload = {"model": model, "prompt": generation_prompt, "n": count, "size": openai_size}
        if isinstance(model, str) and (model.startswith("gpt-image-") or model == "chatgpt-image-latest"):
            image_payload["moderation"] = moderation
            log("🛡️ ", "IMG MOD    ", moderation)
        else:
            log("🛡️ ", "IMG MOD    ", f"{moderation} (ignored for {model})")
        response, openai_err = _safe_openai_call(
            lambda: _openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).images.generate(**image_payload),
            error_code="image_generation_failed",
            unavailable_error_code="image_generation_unavailable",
            label="images.generate",
        )
        if openai_err:
            provider_error_response = openai_err
            raise RuntimeError("provider failure")
        raw_images = _decode_generated_images(response)

        if not raw_images:
            raise RuntimeError("Image generation returned no images")

        generated_at = _now_ms()
        output_total = len(raw_images)
        images_payload = []
        for index, image_item in enumerate(raw_images, start=1):
            image_payload = {
                "b64": image_item["b64"],
                "mime": image_item["mime"],
                "prompt": prompt,
                "model": model,
                "moderation": moderation,
                "style": style,
                "size": size_key,
                "outputIndex": index,
                "outputTotal": output_total,
                "generatedAt": generated_at,
            }
            if width is not None and height is not None:
                image_payload["width"] = width
                image_payload["height"] = height
            images_payload.append(image_payload)

        first_image = images_payload[0]
        if assistant_message_id:
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content="[Image generated]",
                    msg_type="image",
                    payload=first_image,
                    status="complete",
                )
                for image_item in images_payload[1:]:
                    insert_message(
                        conn,
                        session_id,
                        "assistant",
                        "[Image generated]",
                        msg_type="image",
                        payload=image_item,
                        status="complete",
                    )
                conn.commit()
        mime_summary = ", ".join(sorted({item["mime"] for item in images_payload}))
        log("🔍", "FORMAT     ", mime_summary)
        log("✅", "IMAGE DONE ", f"{len(images_payload)} image(s)")
        print(flush=True)
        return {"image": first_image["b64"], "mime": first_image["mime"], "images": images_payload}
    except Exception as exc:
        if assistant_message_id:
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content="Image generation failed. Review the prompt and settings, then retry.",
                    payload=retry_payload,
                    status="error",
                )
                conn.commit()
        _security_log("IMAGE ERR  ", f"{type(exc).__name__}: {str(exc)[:300]}")
        print(flush=True)
        if provider_error_response:
            return provider_error_response
        return _error_response("Image generation failed. Please try again.", 502, "image_generation_failed")


def edit_image():
    limited = _check_rate_limit("image_edit")
    if limited:
        return limited
    oversized = _reject_oversized_multipart(REQUEST_BODY_MAX_BYTES)
    if oversized:
        return oversized
    allowed_form_fields = {"sessionId", "instruction", "model", "useCase", "moderation", "style", "size", "count", "actionOrigin"}
    unexpected_fields = sorted([key for key in request.form.keys() if key not in allowed_form_fields])
    if unexpected_fields:
        return _error_response(
            f"Unexpected field(s): {', '.join(unexpected_fields)}",
            400,
            "unexpected_fields",
        )
    session_id = normalize_session_text(request.form.get("sessionId"))
    if not session_id:
        return _error_response("sessionId is required", 400, "image_edit_session_required")

    use_case = normalize_session_text(request.form.get("useCase", "image")) or "image"
    model = normalize_session_text(request.form.get("model", ""))
    instruction = normalize_session_text(request.form.get("instruction", ""))
    moderation = normalize_session_text(request.form.get("moderation", "auto")) or "auto"
    style = normalize_session_text(request.form.get("style", "photorealistic")) or "photorealistic"
    size_key = normalize_session_text(request.form.get("size", "square")) or "square"
    action_origin = normalize_session_text(request.form.get("actionOrigin", "manual")) or "manual"
    try:
        count = int(request.form.get("count", "1"))
    except (TypeError, ValueError):
        count = -1
    image_file = request.files.get("image")

    if not instruction:
        return _error_response("instruction is required", 400, "image_edit_instruction_required")
    if len(instruction) > IMAGE_PROMPT_MAX_CHARS:
        return _error_response(
            f"instruction must be {IMAGE_PROMPT_MAX_CHARS} characters or fewer",
            400,
            "image_edit_instruction_too_long",
        )
    if not model:
        return _error_response("model is required", 400, "image_edit_model_required")
    if moderation not in IMAGE_MODERATION_LEVELS:
        return _error_response("moderation must be one of: auto, low", 400, "image_edit_invalid_moderation")
    if style not in IMAGE_STYLE_GUIDANCE:
        return _error_response(
            "style must be one of: photorealistic, illustration, 3d_render, poster, minimal",
            400,
            "image_edit_invalid_style",
        )
    if size_key not in IMAGE_SIZE_MAP:
        return _error_response("size must be one of: square, portrait, landscape", 400, "image_edit_invalid_size")
    if count not in IMAGE_OUTPUT_COUNTS:
        return _error_response("count must be one of: 1, 2, 4", 400, "image_edit_invalid_count")
    if not image_file:
        return _error_response("image is required", 400, "image_edit_image_required")

    file_name = (image_file.filename or "edit-base").strip() or "edit-base"
    raw = image_file.read() or b""
    if not raw:
        return _error_response("image file is empty", 400, "image_edit_image_required")
    if len(raw) > IMAGE_EDIT_MAX_BYTES:
        return _error_response("image must be 10MB or smaller", 400, "image_edit_image_too_large")

    uploaded_mime = (image_file.mimetype or "").strip().lower()
    detected_mime = None
    if raw[:4] == b"\x89PNG":
        detected_mime = "image/png"
    elif raw[:2] == b"\xff\xd8":
        detected_mime = "image/jpeg"
    elif raw[:4] == b"RIFF":
        detected_mime = "image/webp"
    effective_mime = detected_mime or uploaded_mime
    if effective_mime not in IMAGE_EDIT_ALLOWED_MIME:
        return _error_response("image must be PNG, JPEG, or WEBP", 400, "image_edit_unsupported_mime")

    assistant_message_id, instruction = _single_shot_interaction(session_id, use_case, instruction)
    generation_instruction = _compose_image_prompt(instruction, style)
    openai_size = IMAGE_SIZE_MAP[size_key]
    width, height = _mapped_size_dimensions(size_key)
    retry_payload = {
        "imageEditRequest": {
            "retryable": False,
            "instruction": instruction,
            "model": model,
            "moderation": moderation,
            "style": style,
            "size": size_key,
            "count": count,
            "baseMime": effective_mime,
            "baseFileName": file_name,
            "actionOrigin": action_origin,
        },
        "errorCode": "image_edit_failed",
    }

    divider()
    log("🖌️ ", "IMAGE EDIT ", f"model={model}")
    log("📝", "INSTR      ", f'"{instruction[:80]}{"..." if len(instruction) > 80 else ""}"')
    log("🎨", "IMG STYLE  ", style)
    log("📐", "IMG SIZE   ", f"{size_key} -> {openai_size}")
    log("🧮", "IMG COUNT  ", str(count))
    log("🗂️ ", "BASE       ", f"{file_name} ({effective_mime}, {len(raw):,} bytes)")
    print("─" * 60, flush=True)
    provider_error_response = None
    try:
        image_stream = io.BytesIO(raw)
        image_stream.name = file_name
        edit_payload = {
            "model": model,
            "image": image_stream,
            "prompt": generation_instruction,
            "n": count,
            "size": openai_size,
        }
        log("🛡️ ", "IMG MOD    ", f"{moderation} (not supported by images.edit in current SDK/API path)")

        response, openai_err = _safe_openai_call(
            lambda: _openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).images.edit(**edit_payload),
            error_code="image_edit_failed",
            unavailable_error_code="image_edit_unavailable",
            label="images.edit",
        )
        if openai_err:
            provider_error_response = openai_err
            raise RuntimeError("provider failure")
        raw_images = _decode_generated_images(response)
        if not raw_images:
            raise RuntimeError("Image edit returned no images")

        generated_at = _now_ms()
        output_total = len(raw_images)
        images_payload = []
        for index, image_item in enumerate(raw_images, start=1):
            payload_item = {
                "b64": image_item["b64"],
                "mime": image_item["mime"],
                "prompt": instruction,
                "instruction": instruction,
                "model": model,
                "moderation": moderation,
                "style": style,
                "size": size_key,
                "outputIndex": index,
                "outputTotal": output_total,
                "generatedAt": generated_at,
                "editMode": "full_image",
                "baseMime": effective_mime,
                "baseFileName": file_name,
                "actionOrigin": action_origin,
            }
            if width is not None and height is not None:
                payload_item["width"] = width
                payload_item["height"] = height
            images_payload.append(payload_item)

        first_image = images_payload[0]
        if assistant_message_id:
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content="[Image edited]",
                    msg_type="image",
                    payload=first_image,
                    status="complete",
                )
                for image_item in images_payload[1:]:
                    insert_message(
                        conn,
                        session_id,
                        "assistant",
                        "[Image edited]",
                        msg_type="image",
                        payload=image_item,
                        status="complete",
                    )
                conn.commit()
        mime_summary = ", ".join(sorted({item["mime"] for item in images_payload}))
        log("🔍", "FORMAT     ", mime_summary)
        log("✅", "EDIT DONE  ", f"{len(images_payload)} image(s)")
        print(flush=True)
        return {"image": first_image["b64"], "mime": first_image["mime"], "images": images_payload}
    except Exception as exc:
        if assistant_message_id:
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content="Image edit failed. Review the base image and instruction, then retry.",
                    payload=retry_payload,
                    status="error",
                )
                conn.commit()
        _security_log("EDIT ERR   ", f"{type(exc).__name__}: {str(exc)[:300]}")
        print(flush=True)
        if provider_error_response:
            return provider_error_response
        return _error_response("Image edit failed. Please try again.", 502, "image_edit_failed")
