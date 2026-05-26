"""HTTP client compartido por las tools del Reel Director.

Habla con los endpoints internal del API MediConnect via mediconnect-internal
(red Docker compartida). Auth con X-Internal-Secret header.
"""
from __future__ import annotations
import os
from typing import Any

import httpx


MARKESTUDIO_API = os.getenv("MARKESTUDIO_API_URL", "http://mediconnect-api:8100")
INTERNAL_SECRET = os.getenv("MARKESTUDIO_INTERNAL_SECRET", "")
TIMEOUT = float(os.getenv("MARKESTUDIO_INTERNAL_TIMEOUT", "300"))


def post_internal(endpoint: str, payload: dict) -> dict[str, Any]:
    """POST a un endpoint /api/v1/markestudio/internal/* y devuelve dict.

    Raises:
        httpx.HTTPError en fallos de red / status no-2xx.
    """
    url = f"{MARKESTUDIO_API}/api/v1/markestudio/internal/{endpoint.lstrip('/')}"
    headers = {"Content-Type": "application/json"}
    if INTERNAL_SECRET:
        headers["X-Internal-Secret"] = INTERNAL_SECRET
    with httpx.Client(timeout=TIMEOUT) as client:
        r = client.post(url, json=payload, headers=headers)
        r.raise_for_status()
        return r.json()
