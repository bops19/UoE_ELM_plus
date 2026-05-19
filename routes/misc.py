from flask import Blueprint

from routes.route_context import get_route_handler


misc_bp = Blueprint("misc_routes", __name__)


@misc_bp.route("/", methods=["GET"])
def index_route():
    return get_route_handler("index")()


@misc_bp.route("/app", methods=["GET"])
@misc_bp.route("/app/", methods=["GET"])
@misc_bp.route("/app/<path:subpath>", methods=["GET"])
def angular_app_route(subpath: str = ""):
    return get_route_handler("angular_app_entry")(subpath)


@misc_bp.route("/assets/<path:asset_path>", methods=["GET"])
def angular_assets_compat_route(asset_path: str):
    # Compatibility route: some templates still reference root /assets/*
    return get_route_handler("angular_app_entry")(f"assets/{asset_path}")


@misc_bp.route("/model-catalog", methods=["GET"])
def get_model_catalog_route():
    return get_route_handler("get_model_catalog")()


@misc_bp.route("/usage/history", methods=["GET"])
def get_usage_history_route():
    return get_route_handler("get_usage_history")()


@misc_bp.route("/usage/model-breakdown", methods=["GET"])
def get_usage_model_breakdown_route():
    return get_route_handler("get_usage_model_breakdown")()


@misc_bp.route("/prompt-presets", methods=["GET"])
def get_prompt_presets_route():
    return get_route_handler("get_prompt_presets")()


@misc_bp.route("/prompt-presets", methods=["POST"])
def create_prompt_preset_route():
    return get_route_handler("create_prompt_preset")()


@misc_bp.route("/prompt-presets/<preset_id>", methods=["PATCH"])
def update_prompt_preset_route(preset_id: str):
    return get_route_handler("update_prompt_preset")(preset_id)


@misc_bp.route("/prompt-presets/<preset_id>", methods=["DELETE"])
def delete_prompt_preset_route(preset_id: str):
    return get_route_handler("delete_prompt_preset")(preset_id)


@misc_bp.route("/settings", methods=["POST"])
def settings_route():
    return get_route_handler("settings")()


@misc_bp.route("/deep-research/mcp-profiles", methods=["GET"])
def deep_research_mcp_profiles_route():
    return get_route_handler("deep_research_mcp_profiles")()


@misc_bp.route("/vm/usage", methods=["GET"])
def vm_usage_route():
    return get_route_handler("vm_usage")()


@misc_bp.route("/vm/session/<session_id>", methods=["GET"])
def vm_session_route(session_id: str):
    return get_route_handler("vm_session")(session_id)


@misc_bp.route("/vm/catalog", methods=["GET"])
def vm_catalog_route():
    return get_route_handler("vm_catalog")()
