import os
import platform
import shutil

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

BASE_DIR = os.path.dirname(__file__)
if load_dotenv:
    load_dotenv(os.path.join(BASE_DIR, ".env"))

LEGACY_RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")
LEGACY_DIR = os.path.join(BASE_DIR, "Legacy")


def _resolve_angular_static_dir() -> str:
    """
    Resolve Angular build output with a strong preference for static/ng/browser.
    This keeps Flask aligned with the current frontend deploy layout.
    """
    override = (os.getenv("ELMPLUS_ANGULAR_STATIC_DIR") or "").strip()
    if override:
        return os.path.abspath(os.path.expanduser(override))

    preferred = os.path.join(BASE_DIR, "static", "ng", "browser")
    if os.path.isdir(preferred):
        return preferred

    fallback = os.path.join(BASE_DIR, "static", "ng")
    if os.path.isdir(fallback):
        return fallback

    # Keep preferred path as the default target even before first frontend build.
    return preferred


ANGULAR_STATIC_DIR = _resolve_angular_static_dir()


def _runtime_path(name: str) -> str:
    return os.path.join(RUNTIME_DIR, name)


def _user_profile_runtime_dir(app_slug: str = "elmplus") -> str:
    """
    Resolve runtime storage under user profile, cross-platform:
    - macOS:   ~/Library/Application Support/<app_slug>/runtime
    - Windows: %APPDATA%\\<app_slug>\\runtime (fallback LOCALAPPDATA, then home)
    - Linux:   $XDG_DATA_HOME/<app_slug>/runtime (fallback ~/.local/share/<app_slug>/runtime)
    """
    env_override = (os.getenv("ELMPLUS_RUNTIME_DIR") or "").strip()
    if env_override:
        return os.path.abspath(os.path.expanduser(env_override))

    home_dir = os.path.expanduser("~")
    system_name = platform.system().lower()

    if system_name == "darwin":
        return os.path.join(home_dir, "Library", "Application Support", app_slug, "runtime")

    if system_name.startswith("win"):
        base = (os.getenv("APPDATA") or os.getenv("LOCALAPPDATA") or home_dir).strip() or home_dir
        return os.path.join(base, app_slug, "runtime")

    xdg_data_home = (os.getenv("XDG_DATA_HOME") or "").strip()
    if xdg_data_home:
        return os.path.join(xdg_data_home, app_slug, "runtime")
    return os.path.join(home_dir, ".local", "share", app_slug, "runtime")


RUNTIME_DIR = _user_profile_runtime_dir()


def _migrate_legacy_runtime_once(src_dir: str, dst_dir: str):
    """
    Best-effort migration from repo-local runtime directory to profile runtime directory.
    Only copies files that are not already present at destination.
    """
    if not src_dir or not os.path.isdir(src_dir):
        return

    src_real = os.path.realpath(src_dir)
    dst_real = os.path.realpath(dst_dir)
    if src_real == dst_real:
        return

    os.makedirs(dst_dir, exist_ok=True)

    files_to_copy = (
        "chat_store.db",
        "prompt_presets.json",
        "token_usage_log.jsonl",
        "sessions.json",
    )
    for filename in files_to_copy:
        src_path = os.path.join(src_dir, filename)
        dst_path = os.path.join(dst_dir, filename)
        if os.path.isfile(src_path) and not os.path.exists(dst_path):
            try:
                shutil.copy2(src_path, dst_path)
            except Exception:
                pass

    src_attachments = os.path.join(src_dir, "chat_files")
    dst_attachments = os.path.join(dst_dir, "chat_files")
    if os.path.isdir(src_attachments) and not os.path.exists(dst_attachments):
        try:
            shutil.copytree(src_attachments, dst_attachments)
        except Exception:
            pass


_migrate_legacy_runtime_once(LEGACY_RUNTIME_DIR, RUNTIME_DIR)


DB_FILE = _runtime_path("chat_store.db")
ATTACHMENTS_DIR = _runtime_path("chat_files")
PROMPT_PRESETS_FILE = _runtime_path("prompt_presets.json")
TOKEN_USAGE_LOG_FILE = _runtime_path("token_usage_log.jsonl")
LEGACY_SESSIONS_FILE = _runtime_path("sessions.json")

BASE_SYSTEM_PROMPT = "You are a helpful assistant."
SUMMARY_MODEL = "gpt-5.4-mini"
MAX_RECENT_MESSAGES = 12  # last 6 user/assistant pairs
MAX_HISTORY_TOKENS = 12_000
HISTORY_CONTEXT_RATIO = 0.20
ATTACHMENT_BUDGET_RATIO = 0.35
SUMMARY_TARGET_TOKENS = 1_500
AUDIO_CHAT_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"
REALTIME_DEFAULT_VOICE = "ash"
AUDIO_CHAT_VOICE = "ash"
AUDIO_CHAT_FORMAT = "mp3"
TTS_OUTPUT_FORMAT = "mp3"
IMAGE_PROMPT_MAX_CHARS = 1500
IMAGE_MODERATION_LEVELS = {"auto", "low"}
IMAGE_STYLE_GUIDANCE = {
    "photorealistic": "Create a photorealistic image with natural lighting, true-to-life textures, and realistic detail.",
    "illustration": "Render as a polished illustration with clean linework, stylized shading, and artistic composition.",
    "3d_render": "Render as a high-quality 3D scene with depth, realistic materials, and cinematic lighting.",
    "poster": "Render as a bold poster-style composition with strong contrast, graphic impact, and clear focal hierarchy.",
    "minimal": "Render in a minimal style with simple forms, clean negative space, and restrained detail.",
}
IMAGE_SIZE_MAP = {
    "square": "1024x1024",
    "portrait": "1024x1536",
    "landscape": "1536x1024",
}
IMAGE_OUTPUT_COUNTS = {1, 2, 4}
IMAGE_EDIT_MAX_BYTES = 10 * 1024 * 1024
IMAGE_EDIT_ALLOWED_MIME = {"image/png", "image/jpeg", "image/webp"}
APP_ENV = (os.getenv("APP_ENV") or os.getenv("FLASK_ENV") or "development").strip().lower()
IS_PRODUCTION = APP_ENV in {"production", "prod"}
REQUEST_BODY_MAX_BYTES = int(os.getenv("REQUEST_BODY_MAX_BYTES", str(60 * 1024 * 1024)))
JSON_BODY_MAX_BYTES = int(os.getenv("JSON_BODY_MAX_BYTES", str(1 * 1024 * 1024)))
OPENAI_TIMEOUT_SEC = float(os.getenv("OPENAI_TIMEOUT_SEC", "90"))
API_KEY = (os.getenv("API_KEY") or os.getenv("ELMPLUS_API_KEY") or "").strip()
EMBEDDING_MODELS = {"text-embedding-3-large", "text-embedding-3-small", "text-embedding-ada-002"}
EMBED_CHUNK_CHARS = 1800
EMBED_CHUNK_OVERLAP_CHARS = 250
EMBED_SEARCH_TOP_K_MAX = 25
SESSION_ARCHIVE_AFTER_DAYS = int(os.getenv("SESSION_ARCHIVE_AFTER_DAYS", "7"))
SESSION_DELETE_ARCHIVED_AFTER_DAYS = int(os.getenv("SESSION_DELETE_ARCHIVED_AFTER_DAYS", "60"))
COMPUTER_USE_PREVIEW_MODEL = "computer-use-preview"
COMPUTER_USE_PREVIEW_DISPLAY_WIDTH = 1024
COMPUTER_USE_PREVIEW_DISPLAY_HEIGHT = 768
COMPUTER_USE_PREVIEW_ENVIRONMENT = "browser"
DEEP_RESEARCH_VECTOR_STORE_IDS = [
    item.strip()
    for item in (os.getenv("DEEP_RESEARCH_VECTOR_STORE_IDS") or "").split(",")
    if item.strip()
][:2]
DEEP_RESEARCH_MCP_SERVER_URL = (os.getenv("DEEP_RESEARCH_MCP_SERVER_URL") or "").strip()
DEEP_RESEARCH_MCP_SERVER_LABEL = (os.getenv("DEEP_RESEARCH_MCP_SERVER_LABEL") or "deep_research_mcp").strip() or "deep_research_mcp"
DEEP_RESEARCH_TOOL_SELECTION_BOOL_KEYS = ("webSearch", "codeInterpreter", "fileSearch", "mcp")
DEEP_RESEARCH_TOOL_SELECTION_KEYS = (*DEEP_RESEARCH_TOOL_SELECTION_BOOL_KEYS, "mcpProfileId")
DEEP_RESEARCH_DATA_SOURCE_TOOL_TYPES = {"web_search", "file_search", "mcp"}
DEEP_RESEARCH_MCP_PROFILES_JSON = (os.getenv("DEEP_RESEARCH_MCP_PROFILES_JSON") or "").strip()

TEXT_FILE_EXTENSIONS = {
    ".txt", ".md", ".markdown", ".py", ".ts", ".tsx", ".js", ".jsx",
    ".json", ".jsonl", ".yaml", ".yml", ".csv", ".tsv", ".html", ".htm",
    ".xml", ".css", ".scss", ".sql", ".tex", ".log", ".ini", ".cfg",
    ".toml", ".sh", ".zsh",
}
TOOL_HANDOFF_EXTENSIONS = {".fig"}

# Developer label fragments (xor+base64 encoded, assembled server-side)
DEV_NAME_FRAGMENT_ALPHA = "VXZn"
DEV_NAME_KEY_ALPHA = 23
