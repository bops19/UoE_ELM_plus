from flask import Blueprint

from routes.route_context import get_route_handler


sessions_bp = Blueprint("sessions_routes", __name__)


@sessions_bp.route("/sessions", methods=["GET"])
def get_sessions_route():
    return get_route_handler("get_sessions")()


@sessions_bp.route("/sessions/<session_id>", methods=["GET"])
def get_session_detail_route(session_id: str):
    return get_route_handler("get_session_detail")(session_id)


@sessions_bp.route("/sessions/<session_id>/export", methods=["GET"])
def export_session_route(session_id: str):
    return get_route_handler("export_session")(session_id)


@sessions_bp.route("/sessions/<session_id>/messages/<int:message_id>/export", methods=["GET"])
def export_assistant_message_route(session_id: str, message_id: int):
    return get_route_handler("export_assistant_message")(session_id, message_id)


@sessions_bp.route("/sessions/<session_id>", methods=["PATCH"])
def update_session_route(session_id: str):
    return get_route_handler("update_session")(session_id)


@sessions_bp.route("/sessions/<session_id>", methods=["DELETE"])
def delete_session_route(session_id: str):
    return get_route_handler("delete_session")(session_id)


@sessions_bp.route("/sessions/<session_id>/clear", methods=["POST"])
def clear_session_route(session_id: str):
    return get_route_handler("clear_session")(session_id)


@sessions_bp.route("/sessions/<session_id>/archive", methods=["PATCH"])
def archive_session_route(session_id: str):
    return get_route_handler("archive_session")(session_id)


@sessions_bp.route("/sessions/<session_id>/attachments", methods=["POST"])
def upload_attachments_route(session_id: str):
    return get_route_handler("upload_attachments")(session_id)


@sessions_bp.route("/sessions/<session_id>/attachments/<attachment_id>", methods=["PATCH"])
def update_attachment_route(session_id: str, attachment_id: str):
    return get_route_handler("update_attachment")(session_id, attachment_id)


@sessions_bp.route("/sessions/<session_id>/attachments/<attachment_id>", methods=["DELETE"])
def delete_attachment_route(session_id: str, attachment_id: str):
    return get_route_handler("delete_attachment")(session_id, attachment_id)

