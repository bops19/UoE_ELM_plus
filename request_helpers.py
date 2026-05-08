"""HTTP request/rate-limit helper logic extracted from app.py."""

import base64
import hashlib
import ipaddress
import os
import sqlite3
import threading
import time

from flask import request


_RATE_LIMIT_TRUSTED_PROXIES_RAW = (os.getenv("RATE_LIMIT_TRUSTED_PROXIES") or "").strip()
_RATE_LIMIT_CLEANUP_INTERVAL_SEC = max(1, int(os.getenv("RATE_LIMIT_CLEANUP_INTERVAL_SEC", "120")))
_RATE_LIMIT_CLEANUP_MAX_ROWS = max(1, int(os.getenv("RATE_LIMIT_CLEANUP_MAX_ROWS", "5000")))
_RATE_LIMIT_LAST_CLEANUP_SEC = 0
_RATE_LIMIT_CLEANUP_LOCK = threading.Lock()


def decode_xor_base64_parts(parts: list[tuple[str, int]]) -> str:
    decoded_parts: list[str] = []
    for encoded, key in parts:
        token = str(encoded or "").strip()
        if not token:
            continue
        try:
            raw = base64.urlsafe_b64decode(token.encode("ascii"))
        except Exception:
            continue
        decoded = "".join(chr(byte ^ int(key)) for byte in raw)
        decoded_parts.append(decoded)
    return "".join(decoded_parts)


def _parse_trusted_proxy_nets(raw_value: str, *, security_log) -> list[ipaddress._BaseNetwork]:
    nets: list[ipaddress._BaseNetwork] = []
    if not raw_value:
        return nets
    for candidate in raw_value.split(","):
        token = candidate.strip()
        if not token:
            continue
        try:
            nets.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            security_log("RATE LIMIT ", f"invalid trusted proxy entry ignored: {token[:80]}")
    return nets


def _parse_ip_address(value: str):
    token = (value or "").strip()
    if not token:
        return None
    try:
        return ipaddress.ip_address(token)
    except ValueError:
        return None


def _client_ip(*, trusted_proxy_nets: list[ipaddress._BaseNetwork]) -> str:
    remote_ip = _parse_ip_address(request.remote_addr or "")
    if remote_ip is None:
        return "unknown"

    if any(remote_ip in net for net in trusted_proxy_nets):
        forwarded = (request.headers.get("X-Forwarded-For") or "").strip()
        if forwarded:
            for candidate in forwarded.split(","):
                forwarded_ip = _parse_ip_address(candidate)
                if forwarded_ip is not None:
                    return str(forwarded_ip)
    return str(remote_ip)


def _rate_limit_cleanup_if_due(conn: sqlite3.Connection, now_sec: int, *, security_log):
    global _RATE_LIMIT_LAST_CLEANUP_SEC
    if now_sec - _RATE_LIMIT_LAST_CLEANUP_SEC < _RATE_LIMIT_CLEANUP_INTERVAL_SEC:
        return
    with _RATE_LIMIT_CLEANUP_LOCK:
        if now_sec - _RATE_LIMIT_LAST_CLEANUP_SEC < _RATE_LIMIT_CLEANUP_INTERVAL_SEC:
            return
        deleted = conn.execute(
            """
            DELETE FROM rate_limit_windows
            WHERE rowid IN (
              SELECT rowid
              FROM rate_limit_windows
              WHERE expires_at_sec <= ?
              ORDER BY expires_at_sec ASC
              LIMIT ?
            )
            """,
            (now_sec, _RATE_LIMIT_CLEANUP_MAX_ROWS),
        ).rowcount
        if deleted:
            security_log("RATE LIMIT ", f"cleanup deleted={deleted}")
        _RATE_LIMIT_LAST_CLEANUP_SEC = now_sec


def _rate_limit_retry_after(conn: sqlite3.Connection, bucket: str, limiter_key: str, now_sec: int, window_sec: int) -> int:
    oldest = conn.execute(
        """
        SELECT MIN(window_start_sec) AS oldest_window
        FROM rate_limit_windows
        WHERE bucket = ? AND limiter_key = ? AND window_start_sec > ?
        """,
        (bucket, limiter_key, now_sec - window_sec),
    ).fetchone()
    oldest_window = int((oldest["oldest_window"] if oldest else 0) or 0)
    if oldest_window <= 0:
        return 1
    return max(1, (oldest_window + window_sec) - now_sec)


def check_rate_limit(
    bucket: str,
    *,
    db_factory,
    error_response,
    security_log,
    rate_limit_defaults: dict[str, tuple[int, int]],
):
    trusted_proxy_nets = _parse_trusted_proxy_nets(_RATE_LIMIT_TRUSTED_PROXIES_RAW, security_log=security_log)
    limit, window_sec = rate_limit_defaults.get(bucket, (60, 60))
    now_sec = int(time.time())
    limiter_key = _client_ip(trusted_proxy_nets=trusted_proxy_nets)
    try:
        with db_factory() as conn:
            conn.execute("BEGIN IMMEDIATE")
            _rate_limit_cleanup_if_due(conn, now_sec, security_log=security_log)
            row = conn.execute(
                """
                SELECT COALESCE(SUM(count), 0) AS request_count
                FROM rate_limit_windows
                WHERE bucket = ? AND limiter_key = ? AND window_start_sec > ?
                """,
                (bucket, limiter_key, now_sec - window_sec),
            ).fetchone()
            request_count = int((row["request_count"] if row else 0) or 0)
            if request_count >= limit:
                retry_after = _rate_limit_retry_after(conn, bucket, limiter_key, now_sec, window_sec)
                key_hash = hashlib.sha256(limiter_key.encode("utf-8")).hexdigest()[:12]
                security_log(
                    "RATE LIMIT ",
                    f"bucket={bucket} keyHash={key_hash} status=blocked retryAfter={retry_after}s",
                )
                conn.commit()
                return error_response(
                    "Too many requests. Please retry shortly.",
                    429,
                    "rate_limit_exceeded",
                    {"retryAfterSec": retry_after},
                )
            conn.execute(
                """
                INSERT INTO rate_limit_windows (
                  bucket, limiter_key, window_start_sec, count, expires_at_sec, updated_at_sec
                )
                VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(bucket, limiter_key, window_start_sec)
                DO UPDATE SET count = count + 1, updated_at_sec = excluded.updated_at_sec, expires_at_sec = excluded.expires_at_sec
                """,
                (bucket, limiter_key, now_sec, now_sec + window_sec, now_sec),
            )
            conn.commit()
    except sqlite3.OperationalError as exc:
        if "readonly" in str(exc).lower():
            return None
        raise
    key_hash = hashlib.sha256(limiter_key.encode("utf-8")).hexdigest()[:12]
    security_log("RATE LIMIT ", f"bucket={bucket} keyHash={key_hash} status=allowed")
    return None


def validated_json_body(
    *,
    json_body_max_bytes: int,
    error_response,
    allowed_keys: set[str] | None = None,
    required_keys: set[str] | None = None,
):
    if (request.content_length or 0) > json_body_max_bytes:
        return None, error_response(
            "JSON payload is too large.",
            413,
            "json_payload_too_large",
        )
    data = request.get_json(silent=True)
    if data is None:
        return None, error_response("Request body must be valid JSON.", 400, "invalid_json")
    if not isinstance(data, dict):
        return None, error_response("Request body must be a JSON object.", 400, "invalid_json_shape")
    if required_keys:
        missing = sorted([key for key in required_keys if key not in data])
        if missing:
            return None, error_response(
                f"Missing required field(s): {', '.join(missing)}",
                400,
                "missing_required_fields",
            )
    if allowed_keys is not None:
        unexpected = sorted([str(key) for key in data.keys() if key not in allowed_keys])
        if unexpected:
            return None, error_response(
                f"Unexpected field(s): {', '.join(unexpected)}",
                400,
                "unexpected_fields",
            )
    return data, None


def reject_oversized_multipart(*, max_bytes: int, error_response):
    if (request.content_length or 0) > max_bytes:
        return error_response("Request payload is too large.", 413, "payload_too_large")
    return None
