import os
import sqlite3


TOOL_HANDOFF_EXTENSIONS = {".fig"}


def _supports_tool_handoff(name: str, extraction_status: str) -> bool:
    ext = os.path.splitext(name or "")[1].lower()
    return extraction_status == "unsupported" and ext in TOOL_HANDOFF_EXTENSIONS


def _format_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _attachment_usable(availability: str, extraction_status: str, mime_type: str, name: str) -> bool:
    if availability != "ready":
        return False
    if (mime_type or "").startswith("image/"):
        return True
    if _supports_tool_handoff(name, extraction_status):
        return True
    return extraction_status == "extracted"


def _unusable_reason_code(availability: str, extraction_status: str, mime_type: str, name: str) -> str | None:
    if availability != "ready":
        return "missing_local"
    if (mime_type or "").startswith("image/"):
        return None
    if _supports_tool_handoff(name, extraction_status):
        return None
    if extraction_status == "extracted":
        return None
    if extraction_status == "failed":
        return "extract_failed"
    if extraction_status == "missing":
        return "extract_missing"
    if extraction_status == "unsupported" and mime_type == "application/pdf":
        return "pdf_text_extraction_unavailable"
    if extraction_status == "unsupported":
        return "unsupported_format"
    return "not_readable_by_model"


def _display_meta(
    size_bytes: int,
    active: bool,
    availability: str,
    extraction_status: str,
    mime_type: str,
    name: str,
    usable: bool,
    unusable_reason_code: str | None,
) -> str:
    parts: list[str] = []
    if size_bytes > 0:
        parts.append(_format_size(size_bytes))

    if availability == "missing":
        parts.append("missing locally")
    elif not usable:
        if unusable_reason_code == "pdf_text_extraction_unavailable":
            parts.append("pdf text extraction unavailable")
        else:
            parts.append("not readable by model")
    else:
        parts.append("active" if active else "inactive")

    if extraction_status == "extracted":
        parts.append("text ready")
    if extraction_status == "failed":
        parts.append("extract failed")
    if extraction_status == "missing":
        parts.append("placeholder")
    if extraction_status == "unsupported" and (mime_type or "").startswith("image/"):
        parts.append("image")
    if _supports_tool_handoff(name, extraction_status):
        parts.append("mcp tool file")
    return " · ".join(parts)


def _toggle_title(active: bool, usable: bool, name: str, extraction_status: str) -> str:
    if not usable:
        return "This file is stored, but not readable by the model yet"
    if _supports_tool_handoff(name, extraction_status):
        return "Include this file for MCP tool workflows" if not active else "Exclude from next request"
    return "Exclude from next request" if active else "Include in next request"


def serialize_attachment_record(row: sqlite3.Row) -> dict:
    availability = row["availability"] or "ready"
    extraction_status = row["extraction_status"] or "unsupported"
    mime_type = row["mime_type"] or "application/octet-stream"
    name = row["name"] or "file"
    size_bytes = int(row["size_bytes"] or 0)
    active = bool(row["active"])
    usable = _attachment_usable(availability, extraction_status, mime_type, name)
    unusable_reason_code = _unusable_reason_code(availability, extraction_status, mime_type, name)

    if availability == "missing":
        status_label = "Missing"
    elif usable:
        status_label = "Active" if active else "Inactive"
    else:
        status_label = "Stored only"

    return {
        "id": row["id"],
        "name": row["name"],
        "mimeType": mime_type,
        "sizeBytes": size_bytes,
        "active": active,
        "availability": availability,
        "extractionStatus": extraction_status,
        "usable": usable,
        "unusableReasonCode": unusable_reason_code,
        "statusLabel": status_label,
        "displayMeta": _display_meta(
            size_bytes,
            active,
            availability,
            extraction_status,
            mime_type,
            name,
            usable,
            unusable_reason_code,
        ),
        "toggleTitle": _toggle_title(active, usable, name, extraction_status),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }
