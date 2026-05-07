import json
import os
import uuid

from prompt_session_service import normalize_prompt_presets


def write_prompt_presets(file_path: str, presets: list[dict]) -> list[dict]:
    normalized = normalize_prompt_presets(presets)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    tmp_path = f"{file_path}.{uuid.uuid4().hex}.tmp"
    with open(tmp_path, "w", encoding="utf-8") as file:
        json.dump(normalized, file, ensure_ascii=False, indent=2)
        file.write("\n")
    os.replace(tmp_path, file_path)
    return normalized


def load_prompt_presets(file_path: str) -> list[dict]:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            raw = json.load(file)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    return normalize_prompt_presets(raw)


def find_prompt_preset(file_path: str, preset_id: str) -> dict | None:
    candidate = str(preset_id or "").strip()
    if not candidate:
        return None
    for preset in load_prompt_presets(file_path):
        if preset.get("id") == candidate:
            return preset
    return None
