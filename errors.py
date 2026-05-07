from dataclasses import dataclass

from flask import Flask, g, has_request_context, jsonify
from werkzeug.exceptions import HTTPException


@dataclass
class ApiError(Exception):
    code: str
    message: str
    status: int = 400


def _request_id() -> str:
    if not has_request_context():
        return "unknown"
    return str(getattr(g, "request_id", "unknown"))


def error_payload(code: str, message: str, *, request_id: str | None = None, extra: dict | None = None) -> dict:
    rid = request_id or _request_id()
    payload = {
        "error": {
            "code": code,
            "message": message,
            "requestId": rid,
        },
        "message": message,
        "errorCode": code,
        "requestId": rid,
    }
    if extra and isinstance(extra, dict):
        payload.update(extra)
    return payload


def register_error_handlers(app: Flask):
    @app.errorhandler(ApiError)
    def _handle_api_error(err: ApiError):
        return jsonify(error_payload(err.code, err.message)), err.status

    @app.errorhandler(Exception)
    def _handle_unexpected(err: Exception):
        if isinstance(err, HTTPException):
            status = int(getattr(err, "code", 500) or 500)
            code = str(getattr(err, "name", "HTTP_ERROR") or "HTTP_ERROR").upper().replace(" ", "_")
            message = str(getattr(err, "description", "Unexpected HTTP error") or "Unexpected HTTP error")
            return jsonify(error_payload(code, message)), status
        app.logger.exception("Unhandled backend error", exc_info=err)
        return jsonify(error_payload("INTERNAL_ERROR", "Unexpected server error")), 500
