from flask import Blueprint

from routes.route_context import get_route_handler


computer_bp = Blueprint("computer_routes", __name__)


@computer_bp.route("/computer-runs/start", methods=["POST"])
def computer_run_start_route():
    return get_route_handler("computer_run_start")()


@computer_bp.route("/computer-runs/<run_id>/step", methods=["POST"])
def computer_run_step_route(run_id: str):
    return get_route_handler("computer_run_step")(run_id)


@computer_bp.route("/computer-runs/<run_id>/close", methods=["POST"])
def computer_run_close_route(run_id: str):
    return get_route_handler("computer_run_close")(run_id)

