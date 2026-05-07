from typing import Any

PROMPT_SETUP_USE_CASES = {"general", "reasoning", "deep", "voice", "audio"}


def normalize_session_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("\r\n", "\n").replace("\r", "\n").strip()


def normalize_preset_name(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def normalize_prompt_preset_record(raw: Any) -> dict | None:
    if not isinstance(raw, dict):
        return None
    preset_id = str(raw.get("id") or "").strip()
    name = normalize_preset_name(raw.get("name"))
    instructions = normalize_session_text(raw.get("instructions"))
    context = normalize_session_text(raw.get("context"))
    created_at = int(raw.get("createdAt") or 0)
    updated_at = int(raw.get("updatedAt") or created_at or 0)
    if not preset_id or not name or not (instructions or context):
        return None
    if created_at <= 0:
        created_at = updated_at if updated_at > 0 else 0
    if updated_at <= 0:
        updated_at = created_at
    return {
        "id": preset_id,
        "name": name,
        "instructions": instructions,
        "context": context,
        "createdAt": created_at,
        "updatedAt": updated_at,
    }


def sort_prompt_presets(presets: list[dict]) -> list[dict]:
    return sorted(
        presets,
        key=lambda preset: (
            (preset.get("name") or "").lower(),
            int(preset.get("updatedAt") or 0),
            preset.get("id") or "",
        ),
    )


def normalize_prompt_presets(raw_presets: list[Any]) -> list[dict]:
    return sort_prompt_presets(
        [
            preset
            for preset in (normalize_prompt_preset_record(item) for item in (raw_presets or []))
            if preset
        ]
    )


def resolve_prompt_preset_id(preset_id: Any, presets: list[dict]) -> str:
    candidate = str(preset_id or "").strip()
    if not candidate:
        return ""
    return candidate if any((preset.get("id") == candidate) for preset in presets) else ""


def normalize_use_case(use_case: Any, allowed_use_cases: set[str], fallback: str = "general") -> str:
    candidate = str(use_case or "").strip()
    if candidate in allowed_use_cases:
        return candidate
    if fallback in allowed_use_cases:
        return fallback
    return sorted(allowed_use_cases)[0] if allowed_use_cases else fallback


def use_case_supports_prompt_setup(use_case: Any) -> bool:
    return str(use_case or "").strip() in PROMPT_SETUP_USE_CASES


def normalize_session_update(
    *,
    request_data: dict,
    existing: Any,
    allowed_use_cases: set[str],
    presets: list[dict],
) -> dict:
    requested_title = " ".join(str(request_data.get("title") or "").split()).strip()
    requested_use_case = str(request_data.get("useCase") or "").strip()
    requested_prompt = request_data["prompt"] if "prompt" in request_data else None
    requested_context = request_data["context"] if "context" in request_data else None
    requested_prompt_preset_id = request_data.get("promptPresetId") if "promptPresetId" in request_data else None

    existing_use_case = str(existing["use_case"] or "").strip() if existing else ""
    existing_prompt = str(existing["custom_prompt"] or "") if existing else ""
    existing_context = str(existing["custom_context"] or "") if existing else ""
    existing_preset_id = str(existing["prompt_preset_id"] or "") if existing else ""

    use_case = normalize_use_case(requested_use_case, allowed_use_cases, fallback=existing_use_case or "general")

    if use_case_supports_prompt_setup(use_case):
        prompt_text = normalize_session_text(requested_prompt) if requested_prompt is not None else normalize_session_text(existing_prompt)
        context_text = normalize_session_text(requested_context) if requested_context is not None else normalize_session_text(existing_context)
        raw_preset_id = requested_prompt_preset_id if requested_prompt_preset_id is not None else existing_preset_id
        prompt_preset_id = resolve_prompt_preset_id(raw_preset_id, presets)
    else:
        prompt_text = ""
        context_text = ""
        prompt_preset_id = ""

    return {
        "title": requested_title or "New chat",
        "useCase": use_case,
        "prompt": prompt_text,
        "context": context_text,
        "promptPresetId": prompt_preset_id,
    }
