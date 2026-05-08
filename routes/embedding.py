from flask import Blueprint

from routes.route_context import get_route_handler


embedding_bp = Blueprint("embedding_routes", __name__)


@embedding_bp.route("/embed-index", methods=["POST"])
def embed_index_route():
    return get_route_handler("embed_index")()


@embedding_bp.route("/embed-search", methods=["POST"])
def embed_search_route():
    return get_route_handler("embed_search")()


@embedding_bp.route("/embed", methods=["POST"])
def embed_route():
    return get_route_handler("embed")()

