from flask import Blueprint

from routes.route_context import get_route_handler


chat_bp = Blueprint("chat_routes", __name__)


@chat_bp.route("/chat", methods=["POST"])
def chat_route():
    return get_route_handler("chat")()

