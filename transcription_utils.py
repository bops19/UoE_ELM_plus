import json
import os

from prompt_session_service import normalize_session_text


def _safe_get(obj, *path, default=None):
    current = obj
    for key in path:
        if current is None:
            return default
        if isinstance(current, dict):
            current = current.get(key, default)
            continue
        try:
            current = getattr(current, key)
        except Exception:
            return default
    return current if current is not None else default


def _preview_for_log(value: str, max_length: int = 180) -> str:
    text = normalize_session_text(value)
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def transcription_segment_payload(transcription) -> list[dict]:
    segments = _safe_get(transcription, "segments", default=[]) or []
    payload_segments: list[dict] = []
    for segment in segments:
        text = str(_safe_get(segment, "text", default="") or "").strip()
        if not text:
            continue
        try:
            start_sec = float(_safe_get(segment, "start", default=0) or 0)
        except (TypeError, ValueError):
            start_sec = 0.0
        try:
            end_sec = float(_safe_get(segment, "end", default=start_sec) or start_sec)
        except (TypeError, ValueError):
            end_sec = start_sec
        payload_segments.append({
            "startSec": max(0.0, start_sec),
            "endSec": max(0.0, end_sec),
            "text": text,
        })
    return payload_segments


def _extract_known_object_fields(value) -> dict:
    known_fields = (
        "id",
        "text",
        "transcript",
        "output_text",
        "utterance",
        "content",
        "sentence",
        "speaker",
        "label",
        "name",
        "start",
        "end",
        "segments",
        "utterances",
        "results",
        "duration",
        "task",
        "usage",
    )
    payload = {}
    for field_name in known_fields:
        try:
            field_value = getattr(value, field_name)
        except Exception:
            continue
        if callable(field_value) or field_value in (None, "", [], {}):
            continue
        payload[field_name] = field_value
    return payload


def _repr_preview(value, max_length: int = 400) -> str:
    try:
        raw = repr(value)
    except Exception:
        raw = str(value)
    text = normalize_session_text(raw)
    if len(text) <= max_length:
        return text
    return text[:max_length].rstrip() + "..."


def _transcription_value_to_python(value, depth: int = 0):
    if depth > 6:
        return value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _transcription_value_to_python(item, depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_transcription_value_to_python(item, depth + 1) for item in value]

    for method_name in ("model_dump", "to_dict"):
        method = getattr(value, method_name, None)
        if not callable(method):
            continue
        try:
            data = method(mode="python") if method_name == "model_dump" else method()
        except TypeError:
            try:
                data = method()
            except Exception:
                continue
        except Exception:
            continue
        if isinstance(data, dict):
            return _transcription_value_to_python(data, depth + 1)

    try:
        cast_dict = dict(value)
        if isinstance(cast_dict, dict) and cast_dict:
            return _transcription_value_to_python(cast_dict, depth + 1)
    except Exception:
        pass

    raw_dict = getattr(value, "__dict__", None)
    if isinstance(raw_dict, dict) and raw_dict:
        return _transcription_value_to_python(raw_dict, depth + 1)

    known_field_dict = _extract_known_object_fields(value)
    if known_field_dict:
        return _transcription_value_to_python(known_field_dict, depth + 1)

    return value


def _transcription_mapping_score(data: dict) -> int:
    if not isinstance(data, dict) or not data:
        return -1

    score = 0
    for key in ("text", "transcript", "output_text"):
        if normalize_session_text(data.get(key)):
            score += 50

    segments = data.get("segments") or data.get("utterances") or data.get("results") or []
    if isinstance(segments, list) and segments:
        score += 10 + min(len(segments), 5)
        first_segment = _transcription_to_dict(segments[0]) or (segments[0] if isinstance(segments[0], dict) else {})
        if isinstance(first_segment, dict):
            for key in ("text", "transcript", "utterance", "content", "sentence"):
                if normalize_session_text(first_segment.get(key)):
                    score += 20
                    break
            if normalize_session_text(first_segment.get("speaker")):
                score += 5

    score += sum(
        1
        for value in data.values()
        if value not in (None, "", [], {})
    )
    return score


def _transcription_to_dict(transcription) -> dict:
    if isinstance(transcription, dict):
        normalized = _transcription_value_to_python(transcription)
        return normalized if isinstance(normalized, dict) else transcription

    candidates: list[dict] = []

    try:
        cast_dict = dict(transcription)
        if isinstance(cast_dict, dict) and cast_dict:
            normalized = _transcription_value_to_python(cast_dict)
            if isinstance(normalized, dict) and normalized:
                candidates.append(normalized)
    except Exception:
        pass

    for method_name in ("model_dump", "to_dict"):
        method = getattr(transcription, method_name, None)
        if not callable(method):
            continue
        try:
            data = method()
        except TypeError:
            try:
                data = method(mode="python")
            except Exception:
                continue
        except Exception:
            continue
        if isinstance(data, dict):
            normalized = _transcription_value_to_python(data)
            if isinstance(normalized, dict) and normalized:
                candidates.append(normalized)

    raw_dict = getattr(transcription, "__dict__", None)
    if isinstance(raw_dict, dict) and raw_dict:
        normalized = _transcription_value_to_python(raw_dict)
        if isinstance(normalized, dict) and normalized:
            candidates.append(normalized)

    known_field_dict = _extract_known_object_fields(transcription)
    if known_field_dict:
        normalized = _transcription_value_to_python(known_field_dict)
        if isinstance(normalized, dict) and normalized:
            candidates.append(normalized)

    if not candidates:
        return {}
    return max(candidates, key=_transcription_mapping_score)


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen = set()
    ordered: list[str] = []
    for line in lines:
        cleaned = normalize_session_text(line)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return ordered


def _collect_nested_text_values(node, lines: list[str], depth: int = 0):
    if depth > 5:
        return
    converted = _transcription_to_dict(node)
    if converted and converted is not node:
        _collect_nested_text_values(converted, lines, depth + 1)
        return
    if isinstance(node, dict):
        text_value = normalize_session_text(node.get("text"))
        if text_value:
            lines.append(text_value)
        transcript_value = normalize_session_text(node.get("transcript"))
        if transcript_value:
            lines.append(transcript_value)
        content_value = normalize_session_text(node.get("content"))
        if content_value:
            lines.append(content_value)
        utterance_value = normalize_session_text(node.get("utterance"))
        if utterance_value:
            lines.append(utterance_value)
        sentence_value = normalize_session_text(node.get("sentence"))
        if sentence_value:
            lines.append(sentence_value)
        for value in node.values():
            _collect_nested_text_values(value, lines, depth + 1)
        return
    if isinstance(node, list):
        for value in node:
            _collect_nested_text_values(value, lines, depth + 1)


def _collect_keyed_text_values(node, lines: list[str], depth: int = 0):
    if depth > 6:
        return
    converted = _transcription_to_dict(node)
    if converted and converted is not node:
        _collect_keyed_text_values(converted, lines, depth + 1)
        return
    if isinstance(node, dict):
        for key, value in node.items():
            key_lower = str(key).lower()
            if isinstance(value, str) and (
                "text" in key_lower
                or "transcript" in key_lower
                or "utterance" in key_lower
                or "sentence" in key_lower
                or key_lower == "content"
            ):
                cleaned = normalize_session_text(value)
                if cleaned:
                    lines.append(cleaned)
            _collect_keyed_text_values(value, lines, depth + 1)
        return
    if isinstance(node, list):
        for value in node:
            _collect_keyed_text_values(value, lines, depth + 1)


def _transcription_text(transcription) -> str:
    data = _transcription_to_dict(transcription)

    direct_text = normalize_session_text(
        _safe_get(data, "text", default=None)
        or _safe_get(data, "transcript", default=None)
        or _safe_get(data, "output_text", default=None)
    )
    if direct_text:
        return direct_text

    speaker_lines: list[str] = []
    speakers = _safe_get(data, "speakers", default=[]) or []
    for speaker_block in speakers if isinstance(speakers, list) else []:
        speaker_data = _transcription_to_dict(speaker_block) or speaker_block
        if not isinstance(speaker_data, dict):
            continue
        speaker_name = normalize_session_text(
            speaker_data.get("speaker")
            or speaker_data.get("label")
            or speaker_data.get("name")
        )
        direct_speaker_text = normalize_session_text(
            speaker_data.get("text")
            or speaker_data.get("transcript")
            or speaker_data.get("utterance")
            or speaker_data.get("content")
        )
        if direct_speaker_text:
            speaker_lines.append(f"[{speaker_name}] {direct_speaker_text}" if speaker_name else direct_speaker_text)

        segments = speaker_data.get("segments")
        if not isinstance(segments, list):
            segments = speaker_data.get("utterances")
        if not isinstance(segments, list):
            continue
        for segment in segments:
            segment_data = _transcription_to_dict(segment) or segment
            text = normalize_session_text(
                _safe_get(segment_data, "text", default=None)
                or _safe_get(segment_data, "transcript", default=None)
                or _safe_get(segment_data, "utterance", default=None)
                or _safe_get(segment_data, "content", default=None)
                or _safe_get(segment_data, "sentence", default=None)
            )
            if not text:
                continue
            speaker_lines.append(f"[{speaker_name}] {text}" if speaker_name else text)

    if speaker_lines:
        return normalize_session_text("\n".join(_dedupe_lines(speaker_lines)))

    segment_lines: list[str] = []
    segments = (
        _safe_get(data, "segments", default=[])
        or _safe_get(data, "utterances", default=[])
        or _safe_get(data, "results", default=[])
        or _safe_get(transcription, "segments", default=[])
        or []
    )
    for segment in segments if isinstance(segments, list) else []:
        segment_data = _transcription_to_dict(segment) or segment
        text = normalize_session_text(
            _safe_get(segment_data, "text", default=None)
            or _safe_get(segment_data, "transcript", default=None)
            or _safe_get(segment_data, "utterance", default=None)
            or _safe_get(segment_data, "content", default=None)
            or _safe_get(segment_data, "sentence", default=None)
        )
        if not text:
            continue
        speaker_name = normalize_session_text(_safe_get(segment_data, "speaker", default=None))
        segment_lines.append(f"[{speaker_name}] {text}" if speaker_name else text)

    if segment_lines:
        return normalize_session_text("\n".join(_dedupe_lines(segment_lines)))

    nested_lines: list[str] = []
    _collect_nested_text_values(data, nested_lines)
    if nested_lines:
        return normalize_session_text("\n".join(_dedupe_lines(nested_lines)))

    keyed_lines: list[str] = []
    _collect_keyed_text_values(data, keyed_lines)
    if keyed_lines:
        return normalize_session_text("\n".join(_dedupe_lines(keyed_lines)))

    text_value = normalize_session_text(
        getattr(transcription, "text", None)
        or _safe_get(transcription, "text", default=None)
        or _safe_get(transcription, "transcript", default=None)
        or _safe_get(transcription, "output_text", default=None)
    )
    if text_value:
        return text_value

    segments = _safe_get(transcription, "segments", default=[]) or _safe_get(transcription, "results", default=[]) or []
    lines = []
    for segment in segments:
        segment_data = _transcription_to_dict(segment) or segment
        text = normalize_session_text(
            _safe_get(segment_data, "text", default=None)
            or _safe_get(segment_data, "transcript", default=None)
            or _safe_get(segment_data, "utterance", default=None)
            or _safe_get(segment_data, "content", default=None)
            or _safe_get(segment_data, "sentence", default=None)
            or ""
        )
        if text:
            speaker_name = normalize_session_text(_safe_get(segment_data, "speaker", default=None))
            lines.append(f"[{speaker_name}] {text}" if speaker_name else text)
    return normalize_session_text("\n".join(_dedupe_lines(lines)))


def _raw_api_response_text(response) -> str:
    if response is None:
        return ""
    try:
        read_method = getattr(response, "read", None)
        if callable(read_method):
            read_method()
    except Exception:
        pass

    text_attr = getattr(response, "text", "")
    if callable(text_attr):
        try:
            text_value = text_attr()
        except Exception:
            text_value = ""
    else:
        text_value = text_attr
    if isinstance(text_value, str) and text_value:
        return text_value

    http_response = getattr(response, "http_response", None)
    if http_response is not None:
        http_text = getattr(http_response, "text", "")
        if isinstance(http_text, str):
            return http_text

    return ""


def _write_diarize_debug_snapshot(transcription, transcription_data, raw_body: str = "") -> str:
    debug_dir = os.path.join(os.path.dirname(__file__), "_debug")
    os.makedirs(debug_dir, exist_ok=True)
    debug_path = os.path.join(debug_dir, "latest_diarize_debug.json")

    raw_segments = []
    if isinstance(transcription_data, dict):
        raw_segments = transcription_data.get("segments") or []
    if not isinstance(raw_segments, list):
        raw_segments = []
    first_segment = raw_segments[0] if raw_segments else None
    normalized_segment = _transcription_to_dict(first_segment) if first_segment is not None else {}
    known_segment_fields = _extract_known_object_fields(first_segment) if first_segment is not None else {}
    top_level_known_fields = _extract_known_object_fields(transcription)

    payload = {
        "topLevelType": type(transcription).__name__,
        "topLevelRepr": _repr_preview(transcription),
        "rawBodyPreview": _preview_for_log(raw_body, 1000) if raw_body else "",
        "topLevelKnownFieldKeys": sorted([str(key) for key in top_level_known_fields.keys()]),
        "topLevelDataKeys": sorted([str(key) for key in transcription_data.keys()]) if isinstance(transcription_data, dict) else [],
        "topLevelTextType": type(_safe_get(transcription_data, "text", default=None)).__name__ if isinstance(transcription_data, dict) else "none",
        "topLevelTextPreview": _repr_preview(_safe_get(transcription_data, "text", default=None)),
        "segmentsType": type(raw_segments).__name__,
        "segmentsCount": len(raw_segments),
        "firstSegmentType": type(first_segment).__name__ if first_segment is not None else "none",
        "firstSegmentRepr": _repr_preview(first_segment),
        "firstSegmentKnownFieldKeys": sorted([str(key) for key in known_segment_fields.keys()]),
        "firstSegmentKnownFields": _transcription_value_to_python(known_segment_fields),
        "firstSegmentNormalizedKeys": sorted([str(key) for key in normalized_segment.keys()]) if isinstance(normalized_segment, dict) else [],
        "firstSegmentNormalized": normalized_segment if isinstance(normalized_segment, dict) else {},
        "firstSegmentDir": [name for name in dir(first_segment) if not name.startswith("_")][:80] if first_segment is not None else [],
        "firstSegmentSlots": list(getattr(type(first_segment), "__slots__", [])) if first_segment is not None and getattr(type(first_segment), "__slots__", None) else [],
    }

    with open(debug_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True, default=str)

    return debug_path
