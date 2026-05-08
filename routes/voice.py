from flask import Blueprint

from routes.route_context import get_route_handler


voice_bp = Blueprint("voice_routes", __name__)


@voice_bp.route("/sessions/<session_id>/voice/bootstrap", methods=["POST"])
def bootstrap_voice_session_route(session_id: str):
    return get_route_handler("bootstrap_voice_session")(session_id)


@voice_bp.route("/sessions/<session_id>/voice/turns", methods=["POST"])
def persist_voice_turn_route(session_id: str):
    return get_route_handler("persist_voice_turn")(session_id)


@voice_bp.route("/sessions/<session_id>/audio/turn", methods=["POST"])
def create_audio_turn_route(session_id: str):
    return get_route_handler("create_audio_turn")(session_id)


@voice_bp.route("/sessions/<session_id>/transcription/turn", methods=["POST"])
def create_transcription_turn_route(session_id: str):
    return get_route_handler("create_transcription_turn")(session_id)


@voice_bp.route("/tts", methods=["POST"])
def text_to_speech_route():
    return get_route_handler("text_to_speech")()

