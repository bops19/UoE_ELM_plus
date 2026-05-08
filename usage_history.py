import datetime
import json
import sqlite3

from model_catalog import pricing_for_model

# Developer label fragments (xor+base64 encoded, assembled server-side)
DEV_NAME_FRAGMENT_GAMMA = "Sm5zdWY="
DEV_NAME_KEY_GAMMA = 7


def _json_loads(raw, default=None):
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def empty_usage() -> dict:
    return {
        "input": 0,
        "cachedInput": 0,
        "output": 0,
        "total": 0,
        "reasoning": 0,
    }


def empty_token_history_scope() -> dict:
    return {
        "totals": {
            **empty_usage(),
            "cost": 0.0,
        },
        "rows": [],
    }


def normalize_usage(usage: dict | None) -> dict:
    usage = usage or {}
    input_tokens = int(usage.get("input") or 0)
    cached_input_tokens = int(usage.get("cachedInput") or 0)
    output_tokens = int(usage.get("output") or 0)
    total_tokens = max(int(usage.get("total") or 0), input_tokens + output_tokens)
    return {
        "input": input_tokens,
        "cachedInput": max(0, cached_input_tokens),
        "output": output_tokens,
        "total": total_tokens,
        "reasoning": int(usage.get("reasoning") or 0),
    }


def _usage_details(usage: dict | None) -> dict:
    usage = usage or {}
    details = usage.get("details") if isinstance(usage, dict) else None
    details = details if isinstance(details, dict) else {}
    return {
        "inputText": int(details.get("inputText") or 0),
        "inputAudio": int(details.get("inputAudio") or 0),
        "inputImage": int(details.get("inputImage") or 0),
        "inputCachedText": int(details.get("inputCachedText") or 0),
        "inputCachedAudio": int(details.get("inputCachedAudio") or 0),
        "inputCachedImage": int(details.get("inputCachedImage") or 0),
        "outputText": int(details.get("outputText") or 0),
        "outputAudio": int(details.get("outputAudio") or 0),
    }


def usage_cost(usage: dict | None, model: str | None, service_tier: str | None = None) -> float:
    if not usage or not model:
        return 0.0
    pricing = pricing_for_model(model, service_tier=service_tier)
    if not pricing:
        return 0.0
    details = _usage_details(usage)
    has_modality_breakdown = any(value > 0 for value in details.values())
    if has_modality_breakdown:
        uncached_text_input = max(0, details["inputText"] - details["inputCachedText"])
        uncached_audio_input = max(0, details["inputAudio"] - details["inputCachedAudio"])
        uncached_image_input = max(0, details["inputImage"] - details["inputCachedImage"])
        return (
            (uncached_text_input / 1_000_000) * float(pricing.get("input") or 0.0)
            + (details["inputCachedText"] / 1_000_000) * float(pricing.get("cached_input") or pricing.get("input") or 0.0)
            + (uncached_audio_input / 1_000_000) * float(pricing.get("audio_input") or pricing.get("input") or 0.0)
            + (details["inputCachedAudio"] / 1_000_000) * float(pricing.get("audio_cached_input") or pricing.get("cached_input") or pricing.get("audio_input") or 0.0)
            + (uncached_image_input / 1_000_000) * float(pricing.get("image_input") or pricing.get("input") or 0.0)
            + (details["inputCachedImage"] / 1_000_000) * float(pricing.get("image_cached_input") or pricing.get("cached_input") or pricing.get("image_input") or 0.0)
            + (details["outputText"] / 1_000_000) * float(pricing.get("output") or 0.0)
            + (details["outputAudio"] / 1_000_000) * float(pricing.get("audio_output") or pricing.get("output") or 0.0)
        )
    normalized_usage = normalize_usage(usage)
    cached_input_tokens = max(0, int(usage.get("cachedInput") or 0))
    input_tokens = max(0, normalized_usage["input"])
    non_cached_input_tokens = max(0, input_tokens - cached_input_tokens)
    input_cost = (non_cached_input_tokens / 1_000_000) * float(pricing["input"])
    cached_input_cost = (cached_input_tokens / 1_000_000) * float(pricing.get("cached_input") or pricing["input"])
    output_cost = (max(0, normalized_usage["output"]) / 1_000_000) * float(pricing["output"])
    return input_cost + cached_input_cost + output_cost


def token_history_scope(
    conn: sqlite3.Connection,
    session_id: str | None = None,
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> dict:
    query = """
        SELECT m.id, m.session_id, m.usage_json, m.usage_model, m.usage_cost, s.use_case, m.elapsed_sec, m.created_at
        FROM messages m
        JOIN sessions s ON s.id = m.session_id
        WHERE m.status = 'complete'
          AND m.usage_json IS NOT NULL
    """
    params: list[object] = []
    if session_id:
      query += " AND m.session_id = ?"
      params.append(session_id)
    if start_ms is not None:
      query += " AND m.created_at >= ?"
      params.append(start_ms)
    if end_ms is not None:
      query += " AND m.created_at < ?"
      params.append(end_ms)
    query += " ORDER BY m.created_at ASC, m.id ASC"

    totals = empty_usage()
    rows_by_model: dict[str, dict] = {}
    total_cost = 0.0

    for row in conn.execute(query, tuple(params)).fetchall():
        usage = _json_loads(row["usage_json"], default={}) or {}
        if not usage:
            continue
        normalized_usage = normalize_usage(usage)
        model = (row["usage_model"] or "").strip() or "(unattributed)"
        stored_cost = row["usage_cost"]
        cost = float(stored_cost) if stored_cost is not None else usage_cost(normalized_usage, row["usage_model"])

        totals["input"] += normalized_usage["input"]
        totals["cachedInput"] += normalized_usage["cachedInput"]
        totals["output"] += normalized_usage["output"]
        totals["total"] += normalized_usage["total"]
        totals["reasoning"] += normalized_usage["reasoning"]
        total_cost += cost

        current = rows_by_model.setdefault(model, {
            "model": model,
            "input": 0,
            "cachedInput": 0,
            "output": 0,
            "total": 0,
            "reasoning": 0,
            "cost": 0.0,
        })
        current["input"] += normalized_usage["input"]
        current["cachedInput"] += normalized_usage["cachedInput"]
        current["output"] += normalized_usage["output"]
        current["total"] += normalized_usage["total"]
        current["reasoning"] += normalized_usage["reasoning"]
        current["cost"] += cost

    rows = sorted(rows_by_model.values(), key=lambda item: (-item["total"], item["model"]))
    effective_total_tokens = totals["total"]
    effective_total_cost = total_cost
    for item in rows:
        item["tokenSharePct"] = ((item["total"] / effective_total_tokens) * 100) if effective_total_tokens > 0 else 0.0
        item["costSharePct"] = ((item["cost"] / effective_total_cost) * 100) if effective_total_cost > 0 else 0.0

    return {
        "totals": {
            **totals,
            "cost": total_cost,
        },
        "rows": rows,
    }


def local_day_bounds_ms(date_value: str | None = None) -> tuple[int, int, str]:
    if date_value:
        day = datetime.date.fromisoformat(date_value)
    else:
        day = datetime.datetime.now().astimezone().date()
    start_local = datetime.datetime.combine(day, datetime.time.min).astimezone()
    end_local = start_local + datetime.timedelta(days=1)
    return (
        int(start_local.timestamp() * 1000),
        int(end_local.timestamp() * 1000),
        day.isoformat(),
    )


def build_usage_history_payload(
    conn: sqlite3.Connection,
    session_id: str | None = None,
    date_value: str | None = None,
) -> dict:
    day_start_ms, day_end_ms, day_key = local_day_bounds_ms(date_value)
    active_session = token_history_scope(conn, session_id=session_id) if session_id else empty_token_history_scope()
    today = token_history_scope(conn, start_ms=day_start_ms, end_ms=day_end_ms)
    all_time = token_history_scope(conn)
    return {
        "activeSession": active_session,
        "today": {
            **today,
            "date": day_key,
        },
        "allTime": all_time,
    }
