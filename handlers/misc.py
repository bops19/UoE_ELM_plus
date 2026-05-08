"""Misc page + settings + VM/catalog + deep-research handlers."""

import os

from flask import Response, redirect, request, send_from_directory
from model_catalog import get_model_catalog_payload, normalize_service_tier
from model_catalog import DEV_NAME_FRAGMENT_BETA, DEV_NAME_KEY_BETA
from prompt_presets_store import load_prompt_presets
from prompt_session_service import normalize_session_text
from session_store import session_detail
from usage_history import DEV_NAME_FRAGMENT_GAMMA, DEV_NAME_KEY_GAMMA
from vm_service import build_catalog_view, build_session_view, build_usage_view

from handler_dependencies import (
    ANGULAR_STATIC_DIR,
    DEV_NAME_FRAGMENT_ALPHA,
    DEV_NAME_KEY_ALPHA,
    DEEP_RESEARCH_DEFAULT_MCP_PROFILE_ID,
    DEEP_RESEARCH_MCP_PROFILES,
    PROMPT_PRESETS_FILE,
    _db,
    _error_response,
    _refresh_attachment_extraction_if_possible,
    _validated_json_body,
    divider,
    log,
)

import request_helpers


def _developer_label() -> str:
    name = request_helpers.decode_xor_base64_parts([
        (DEV_NAME_FRAGMENT_ALPHA, DEV_NAME_KEY_ALPHA),
        (DEV_NAME_FRAGMENT_BETA, DEV_NAME_KEY_BETA),
        (DEV_NAME_FRAGMENT_GAMMA, DEV_NAME_KEY_GAMMA),
    ]).strip()
    return f"Created by {name or 'Developer'}"


def index():
    log("🌐", "PAGE LOAD  ", "→ redirect / to /app")
    return redirect("/app", code=302)


def angular_app_entry(subpath: str = ""):
    normalized_subpath = (subpath or "").strip().lstrip("/")
    if not os.path.isdir(ANGULAR_STATIC_DIR):
        return _error_response(
            "Angular frontend build not found. Run npm install && npm run build in /frontend.",
            503,
            "frontend_unavailable",
        )

    if normalized_subpath:
        candidate = os.path.join(ANGULAR_STATIC_DIR, normalized_subpath)
        if os.path.isfile(candidate):
            return send_from_directory(ANGULAR_STATIC_DIR, normalized_subpath)
        if "." in os.path.basename(normalized_subpath):
            return _error_response("Frontend asset not found.", 404, "frontend_asset_not_found")

    index_path = os.path.join(ANGULAR_STATIC_DIR, "index.html")
    with open(index_path, encoding="utf-8") as file:
        return Response(file.read(), mimetype="text/html")


def get_model_catalog():
    processing_mode = normalize_session_text(request.args.get("processingMode") or "")
    requested_tier = "default"
    if processing_mode == "flex":
        requested_tier = "flex"
    elif processing_mode == "priority":
        requested_tier = "priority"
    service_tier = normalize_service_tier(requested_tier)
    return get_model_catalog_payload(service_tier=service_tier)


def settings():
    data, err = _validated_json_body(allowed_keys={"model", "effort"})
    if err:
        return err
    model = data.get("model")
    effort = data.get("effort")
    divider()
    if model:
        log("🔄", "MODEL SET  ", model)
    if effort:
        log("🧠", "EFFORT SET ", effort)
    print("─" * 60, flush=True)
    print(flush=True)
    return {"ok": True}


def deep_research_mcp_profiles():
    profiles = []
    for profile in DEEP_RESEARCH_MCP_PROFILES:
        profile_id = str(profile.get("id") or "").strip()
        label = str(profile.get("label") or profile_id).strip() or profile_id
        if not profile_id:
            continue
        profiles.append({
            "id": profile_id,
            "label": label,
            "description": str(profile.get("description") or "").strip(),
            "isDefault": profile_id == DEEP_RESEARCH_DEFAULT_MCP_PROFILE_ID,
        })
    return {
        "profiles": profiles,
        "defaultProfileId": DEEP_RESEARCH_DEFAULT_MCP_PROFILE_ID,
    }


def vm_usage():
    session_id = normalize_session_text(request.args.get("sessionId") or "")
    selected_model = normalize_session_text(request.args.get("selectedModel") or "")
    voice_mode = normalize_session_text(request.args.get("voiceMode") or "")
    with _db() as conn:
        usage_view = build_usage_view(conn, session_id=session_id or None, voice_mode=voice_mode or None)
    return {
        "usageView": usage_view,
        "selectedModel": selected_model,
        "voiceMode": voice_mode,
    }


def vm_session(session_id: str):
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
    return {"sessionView": build_session_view(detail)}


def vm_catalog():
    selected_model = normalize_session_text(request.args.get("selectedModel") or "")
    voice_mode = normalize_session_text(request.args.get("voiceMode") or "")
    processing_mode = normalize_session_text(request.args.get("processingMode") or "")
    requested_tier = "default"
    if processing_mode == "flex":
        requested_tier = "flex"
    elif processing_mode == "priority":
        requested_tier = "priority"
    service_tier = normalize_service_tier(requested_tier)
    catalog_payload = get_model_catalog_payload(service_tier=service_tier)
    if not selected_model:
        defaults = catalog_payload.get("defaults") or {}
        default_use_case = str(defaults.get("useCase") or "general")
        default_tier = str(defaults.get("tier") or "standard")
        default_models = (
            (catalog_payload.get("modelMap") or {})
            .get(default_use_case, {})
            .get(default_tier, [])
        )
        if isinstance(default_models, list) and default_models:
            selected_model = str(default_models[0] or "")
    return {
        "catalog": catalog_payload,
        "catalogView": build_catalog_view(
            selected_model=selected_model,
            voice_mode=voice_mode,
            service_tier=service_tier,
        ),
        "developerLabel": _developer_label(),
    }
