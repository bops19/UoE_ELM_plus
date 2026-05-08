"""Handlers for the /computer-runs/* endpoints."""

from flask import request

from computer_use_service import ComputerRunError
from prompt_session_service import normalize_session_text

from handler_dependencies import (
    COMPUTER_RUN_MANAGER,
    COMPUTER_USE_PREVIEW_DISPLAY_HEIGHT,
    COMPUTER_USE_PREVIEW_DISPLAY_WIDTH,
    COMPUTER_USE_PREVIEW_MODEL,
    JSON_BODY_MAX_BYTES,
    _check_rate_limit,
    _error_response,
    _normalize_acknowledged_safety_checks,
    _normalize_start_url,
    _validated_json_body,
)


def computer_run_start():
    limited = _check_rate_limit("computer_runs")
    if limited:
        return limited
    data, err = _validated_json_body(
        allowed_keys={"sessionId", "userText", "model", "displayWidth", "displayHeight", "startUrl", "reasoningSummary"},
        required_keys={"sessionId", "userText"},
    )
    if err:
        return err
    try:
        model = normalize_session_text(data.get("model") or COMPUTER_USE_PREVIEW_MODEL) or COMPUTER_USE_PREVIEW_MODEL
        display_width = int(data.get("displayWidth", COMPUTER_USE_PREVIEW_DISPLAY_WIDTH) or COMPUTER_USE_PREVIEW_DISPLAY_WIDTH)
        display_height = int(data.get("displayHeight", COMPUTER_USE_PREVIEW_DISPLAY_HEIGHT) or COMPUTER_USE_PREVIEW_DISPLAY_HEIGHT)
    except (TypeError, ValueError):
        return _error_response(
            "displayWidth and displayHeight must be integers.",
            400,
            "computer_run_invalid_display",
        )
    if display_width < 320 or display_width > 4096 or display_height < 240 or display_height > 4096:
        return _error_response(
            "displayWidth/displayHeight are outside supported bounds.",
            400,
            "computer_run_invalid_display",
        )

    try:
        payload = COMPUTER_RUN_MANAGER.start_run(
            session_id=data.get("sessionId"),
            user_text=data.get("userText"),
            model=model,
            display_width=display_width,
            display_height=display_height,
            start_url=_normalize_start_url(data.get("startUrl")),
            reasoning_summary=data.get("reasoningSummary"),
        )
        return payload
    except ComputerRunError as exc:
        return _error_response(exc.message, exc.status, exc.error_code, exc.extra)


def computer_run_step(run_id):
    limited = _check_rate_limit("computer_runs")
    if limited:
        return limited
    if (request.content_length or 0) > JSON_BODY_MAX_BYTES:
        return _error_response(
            "JSON payload is too large.",
            413,
            "json_payload_too_large",
        )
    data = request.get_json(silent=True)
    if data is None:
        raw_body = request.get_data(cache=True, as_text=True) or ""
        if raw_body.strip():
            return _error_response("Request body must be valid JSON.", 400, "invalid_json")
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return _error_response("Request body must be a JSON object.", 400, "invalid_json_shape")
    unexpected = sorted([str(key) for key in data.keys() if key not in {"acknowledgedSafetyChecks"}])
    if unexpected:
        return _error_response(
            f"Unexpected field(s): {', '.join(unexpected)}",
            400,
            "unexpected_fields",
        )
    try:
        acknowledged = _normalize_acknowledged_safety_checks(data.get("acknowledgedSafetyChecks") or [])
        payload = COMPUTER_RUN_MANAGER.step_run(run_id, acknowledged_safety_checks=acknowledged)
        return payload
    except ComputerRunError as exc:
        return _error_response(exc.message, exc.status, exc.error_code, exc.extra)


def computer_run_close(run_id):
    limited = _check_rate_limit("computer_runs")
    if limited:
        return limited
    try:
        return COMPUTER_RUN_MANAGER.close_run(run_id)
    except ComputerRunError as exc:
        return _error_response(exc.message, exc.status, exc.error_code, exc.extra)
