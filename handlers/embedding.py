"""Handlers for the /embed-index, /embed-search, /embed endpoints."""

import json

from prompt_session_service import normalize_session_text
from session_store import update_message

from handler_dependencies import (
    EMBEDDING_MODELS,
    EMBED_SEARCH_TOP_K_MAX,
    OPENAI_TIMEOUT_SEC,
    _check_rate_limit,
    _cosine_similarity,
    _db,
    _embedding_model_or_default,
    _error_response,
    _now_ms,
    _openai_client,
    _parse_embedding_vector,
    _preview_for_log,
    _safe_openai_call,
    _security_log,
    _single_shot_interaction,
    _split_for_embedding,
    _validated_json_body,
    divider,
    log,
)


def embed_index():
    limited = _check_rate_limit("embed_index")
    if limited:
        return limited
    data, err = _validated_json_body(
        allowed_keys={"sessionId", "model", "includeInactive", "rebuild"},
        required_keys={"sessionId"},
    )
    if err:
        return err
    session_id = normalize_session_text(data.get("sessionId"))
    if not session_id:
        return _error_response("sessionId is required", 400, "embed_index_session_required")
    model = _embedding_model_or_default(data.get("model"))
    if model not in EMBEDDING_MODELS:
        return _error_response(
            "model must be one of: text-embedding-3-large, text-embedding-3-small, text-embedding-ada-002",
            400,
            "embed_index_invalid_model",
        )
    include_inactive = bool(data.get("includeInactive"))
    rebuild = True if data.get("rebuild") is None else bool(data.get("rebuild"))

    with _db() as conn:
        session_exists = conn.execute("SELECT id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not session_exists:
            return _error_response("session not found", 404, "session_not_found")
        if include_inactive:
            rows = conn.execute(
                """
                SELECT id, name, extracted_text, active, extraction_status
                FROM attachments
                WHERE session_id = ? AND extraction_status = 'extracted'
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, name, extracted_text, active, extraction_status
                FROM attachments
                WHERE session_id = ? AND extraction_status = 'extracted' AND active = 1
                ORDER BY created_at ASC, id ASC
                """,
                (session_id,),
            ).fetchall()
        attachments = [row for row in rows if normalize_session_text(row["extracted_text"] or "")]
        if not attachments:
            return _error_response(
                "No extractable text attachments available for embedding.",
                400,
                "embed_index_no_extractable_attachments",
            )
        if rebuild:
            conn.execute(
                "DELETE FROM file_embeddings WHERE session_id = ? AND model = ?",
                (session_id, model),
            )
            conn.commit()

        indexed_chunks = 0
        indexed_files = 0
        for row in attachments:
            chunks = _split_for_embedding(row["extracted_text"] or "")
            if not chunks:
                continue
            response, openai_err = _safe_openai_call(
                lambda chunks=chunks: _openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).embeddings.create(
                    model=model,
                    input=chunks,
                ),
                error_code="embed_index_failed",
                unavailable_error_code="embed_index_unavailable",
                label="embeddings.create(index)",
            )
            if openai_err:
                conn.rollback()
                return openai_err
            embeddings_data = getattr(response, "data", None) or []
            if len(embeddings_data) != len(chunks):
                conn.rollback()
                return _error_response("Embedding provider returned an unexpected response.", 502, "embed_index_invalid_response")
            now = _now_ms()
            for chunk_index, chunk in enumerate(chunks):
                vector = _parse_embedding_vector(getattr(embeddings_data[chunk_index], "embedding", None))
                if not vector:
                    continue
                conn.execute(
                    """
                    INSERT INTO file_embeddings
                      (session_id, attachment_id, attachment_name, model, chunk_index, chunk_text, embedding_json, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        row["id"],
                        row["name"],
                        model,
                        chunk_index,
                        chunk,
                        json.dumps(vector, ensure_ascii=False),
                        now,
                    ),
                )
                indexed_chunks += 1
            indexed_files += 1
        conn.commit()

    if indexed_chunks <= 0:
        return _error_response("No valid chunks were indexed from selected files.", 400, "embed_index_no_chunks")
    return {
        "ok": True,
        "sessionId": session_id,
        "model": model,
        "indexedFiles": indexed_files,
        "indexedChunks": indexed_chunks,
    }


def embed_search():
    limited = _check_rate_limit("embed_search")
    if limited:
        return limited
    data, err = _validated_json_body(
        allowed_keys={"sessionId", "model", "query", "topK"},
        required_keys={"sessionId", "query"},
    )
    if err:
        return err
    session_id = normalize_session_text(data.get("sessionId"))
    query = normalize_session_text(data.get("query"))
    if not session_id:
        return _error_response("sessionId is required", 400, "embed_search_session_required")
    if not query:
        return _error_response("query is required", 400, "embed_search_query_required")
    model = _embedding_model_or_default(data.get("model"))
    if model not in EMBEDDING_MODELS:
        return _error_response(
            "model must be one of: text-embedding-3-large, text-embedding-3-small, text-embedding-ada-002",
            400,
            "embed_search_invalid_model",
        )
    try:
        top_k = int(data.get("topK", 8))
    except (TypeError, ValueError):
        top_k = 8
    top_k = max(1, min(EMBED_SEARCH_TOP_K_MAX, top_k))

    with _db() as conn:
        rows = conn.execute(
            """
            SELECT attachment_id, attachment_name, chunk_index, chunk_text, embedding_json
            FROM file_embeddings
            WHERE session_id = ? AND model = ?
            """,
            (session_id, model),
        ).fetchall()
    if not rows:
        return _error_response(
            "No embedding index found for this session/model. Run /embed-index first.",
            400,
            "embed_index_required",
        )

    query_response, openai_err = _safe_openai_call(
        lambda: _openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).embeddings.create(
            model=model,
            input=query,
        ),
        error_code="embed_search_failed",
        unavailable_error_code="embed_search_unavailable",
        label="embeddings.create(search)",
    )
    if openai_err:
        return openai_err
    query_data = getattr(query_response, "data", None) or []
    query_vector = _parse_embedding_vector(getattr(query_data[0], "embedding", None) if query_data else [])
    if not query_vector:
        return _error_response("Embedding provider returned an invalid query vector.", 502, "embed_search_invalid_response")

    scored = []
    for row in rows:
        candidate = _parse_embedding_vector(row["embedding_json"])
        if not candidate:
            continue
        score = _cosine_similarity(query_vector, candidate)
        if score <= -1.0:
            continue
        scored.append({
            "attachmentId": row["attachment_id"],
            "fileName": row["attachment_name"],
            "chunkIndex": int(row["chunk_index"] or 0),
            "score": score,
            "snippet": _preview_for_log(row["chunk_text"] or "", 260),
        })
    scored.sort(key=lambda item: item["score"], reverse=True)
    matches = scored[:top_k]

    file_best: dict[str, dict] = {}
    for match in matches:
        file_name = match["fileName"]
        current = file_best.get(file_name)
        if current is None or match["score"] > current["score"]:
            file_best[file_name] = {"fileName": file_name, "score": match["score"]}
    files = sorted(file_best.values(), key=lambda item: item["score"], reverse=True)

    return {
        "sessionId": session_id,
        "model": model,
        "query": query,
        "topK": top_k,
        "matches": matches,
        "files": files,
    }


def embed():
    limited = _check_rate_limit("chat")
    if limited:
        return limited
    data, err = _validated_json_body(
        allowed_keys={"sessionId", "useCase", "model", "text"},
        required_keys={"sessionId", "text"},
    )
    if err:
        return err
    session_id = data.get("sessionId")
    use_case = data.get("useCase", "embeddings")
    model = data.get("model", "text-embedding-3-large")
    text = data.get("text", "")
    assistant_message_id, text = _single_shot_interaction(session_id, use_case, text)
    divider()
    log("📐", "EMBED      ", f"model={model}")
    log("📝", "INPUT      ", f'"{text[:80]}{"..." if len(text) > 80 else ""}"')
    print("─" * 60, flush=True)
    try:
        response, openai_err = _safe_openai_call(
            lambda: _openai_client().with_options(timeout=OPENAI_TIMEOUT_SEC).embeddings.create(model=model, input=text),
            error_code="embedding_failed",
            unavailable_error_code="embedding_unavailable",
            label="embeddings.create",
        )
        if openai_err:
            return openai_err
        vector = response.data[0].embedding
        dimensions = len(vector)
        payload = {"dimensions": dimensions, "preview": vector[:8], "model": model}
        if assistant_message_id:
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content=f"[Embedding: {dimensions} dimensions]",
                    msg_type="embed",
                    payload=payload,
                    status="complete",
                )
                conn.commit()
        log("✅", "EMBED DONE ", f"{dimensions} dimensions")
        print(flush=True)
        return payload
    except Exception as exc:
        if assistant_message_id:
            with _db() as conn:
                update_message(
                    conn,
                    assistant_message_id,
                    content="[Request failed. Please retry.]",
                    status="error",
                )
                conn.commit()
        _security_log("EMBED ERR  ", f"{type(exc).__name__}: {str(exc)[:300]}")
        print(flush=True)
        return _error_response("Embedding generation failed. Please retry.", 502, "embedding_failed")
