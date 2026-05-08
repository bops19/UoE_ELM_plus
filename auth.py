import hmac
import uuid
from functools import wraps

from flask import current_app, g, has_request_context, jsonify, request

from errors import error_payload


def require_api_key(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        expected = str(current_app.config.get("API_KEY") or "").strip()
        if not expected:
            return view(*args, **kwargs)

        provided = str(request.headers.get("X-API-Key") or "").strip()
        if provided and hmac.compare_digest(provided, expected):
            return view(*args, **kwargs)
        return jsonify(error_payload("UNAUTHORIZED", "Invalid API key")), 401

    return wrapped


def register_api_key_guard(app):
    @app.before_request
    def _api_key_guard():
        if has_request_context() and not getattr(g, "request_id", None):
            g.request_id = uuid.uuid4().hex

        if request.method == "OPTIONS":
            return None

        path = (request.path or "").strip()
        if path == "/" or path.startswith("/app"):
            return None

        expected = str(app.config.get("API_KEY") or "").strip()
        if not expected:
            return None

        provided = str(request.headers.get("X-API-Key") or "").strip()
        if provided and hmac.compare_digest(provided, expected):
            return None

        return jsonify(error_payload("UNAUTHORIZED", "Invalid API key")), 401
