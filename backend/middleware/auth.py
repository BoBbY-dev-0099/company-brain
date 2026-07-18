"""API-key + open demo auth middleware (hackathon mode).

Priority:
1. Public paths → skip auth entirely.
2. X-Brain-Api-Key header → agent API key verified against MongoDB.
3. Otherwise → open mode: org_id=DEMO_ORG_ID, auth_type=\"open\" (no 401).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from backend.brain.store import get_db
from backend.config import settings

logger = logging.getLogger(__name__)

_PUBLIC_PATHS = {
    "/health",
    "/api/health",
    "/readme",
    "/api/readme",
    "/mcp/sse",
    "/stream",
    "/docs",
    "/openapi.json",
}


async def _verify_agent_api_key(api_key: str) -> tuple[str, str]:
    """Verify an agent API key against MongoDB.

    Returns (org_id, api_key_id) if valid, raises HTTPException(401) otherwise.
    """
    db = get_db()
    doc = await db["api_keys"].find_one({
        "api_key": api_key,
        "revoked_at": None,
    })
    if not doc:
        raise HTTPException(status_code=401, detail="Invalid or revoked API key")
    return str(doc.get("org_id", settings.DEMO_ORG_ID)), str(doc.get("key_id", ""))


async def auth_middleware(request: Request, call_next: Any) -> Any:
    """FastAPI middleware extracting org_id + auth_type + user_id into request.state."""
    path = request.url.path

    if path in _PUBLIC_PATHS:
        return await call_next(request)

    request.state.org_id = None
    request.state.auth_type = None
    request.state.user_id = None

    api_key = request.headers.get("X-Brain-Api-Key", "")
    if api_key:
        try:
            org_id, _key_id = await _verify_agent_api_key(api_key)
            request.state.org_id = org_id
            request.state.auth_type = "agent"
            return await call_next(request)
        except HTTPException:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        except Exception:  # noqa: BLE001
            logger.exception("Agent API key verification error")
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Hackathon open mode — UI shares the clean demo org.
    request.state.org_id = settings.DEMO_ORG_ID
    request.state.auth_type = "open"
    request.state.user_id = "demo"
    return await call_next(request)


async def resolve_org_from_token(token: str) -> str | None:
    """Try to resolve an org_id from an API key token. Returns None if invalid."""
    try:
        org_id, _ = await _verify_agent_api_key(token)
        return org_id
    except Exception:  # noqa: BLE001
        return None
