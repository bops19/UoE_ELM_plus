from __future__ import annotations

import hashlib
import os

from openai import OpenAI


def require_openai_api_key() -> str:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required to start this server.")
    return api_key


def openai_api_key_fingerprint() -> str:
    api_key = require_openai_api_key()
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:12]
    return f"sha256:{digest} len:{len(api_key)}"


def openai_client() -> OpenAI:
    return OpenAI(api_key=require_openai_api_key())
