"""API-key + open demo auth middleware (hackathon mode).

Priority:
1. Public paths → skip auth entirely.
2. X-Brain-Api-Key header → agent API key verified against MongoDB.
3. Otherwise → open mode: org_id=DEMO_ORG_ID, auth_type=\"open\" (no 401).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from backend.brain.store import get_db
from backend.config import settings
from backend.demo.state import is_canonical_demo_org
from backend.demo.judge_session import COOKIE_NAME, parse_judge_session

logger = logging.getLogger(__name__)

_PUBLIC_PATHS = {
    "/health",
    "/api/health",
    "/demo/readiness",
    "/api/demo/readiness",
    "/readme",
    "/api/readme",
    "/mcp/sse",
    "/stream",
    "/docs",
    "/openapi.json",
}

_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_JUDGE_SANDBOX_PATHS = {
    "/demo/mcp-session",
    "/workflow-runs",
    "/workflow-sources",
    "/source-connections",
    "/source-events",
    "/reality-memory",
    "/reality-overview",
    "/reality/replay/incident",
    "/demo-company/run",
}


def _judge_session_path(path: str) -> bool:
    return (
        path in _JUDGE_SANDBOX_PATHS
        or path.startswith("/workflow-runs/")
        or path.startswith("/demo-company/nexaflow/")
    )


def _canonical_fixture_write_blocked(request: Request) -> bool:
    """Keep API-key holders from accidentally changing the judge fixture."""
    return (
        request.method in _MUTATING_METHODS
        and is_canonical_demo_org(str(getattr(request.state, "org_id", "")))
    )


async def _verify_agent_api_key(api_key: str) -> tuple[str, str]:
    """Verify an agent API key against MongoDB.

    Returns (org_id, api_key_id) if valid, raises HTTPException(401) otherwise.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = await db["api_keys"].find_one({
        "api_key": api_key,
        "revoked_at": None,
        "$or": [
            {"expires_at": None},
            {"expires_at": {"$gt": now}},
            {"expires_at": {"$exists": False}},
        ],
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
            if _canonical_fixture_write_blocked(request):
                return JSONResponse(
                    {
                        "error": "Canonical judge fixture is immutable",
                        "detail": "Use the sandbox org for exploratory writes.",
                    },
                    status_code=409,
                )
            return await call_next(request)
        except HTTPException:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        except Exception:  # noqa: BLE001
            logger.exception("Agent API key verification error")
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # Hackathon open mode — UI shares the clean demo org.
    judge_session = parse_judge_session(request.cookies.get(COOKIE_NAME)) if _judge_session_path(path) else None
    request.state.org_id = judge_session.org_id if judge_session else settings.DEMO_ORG_ID
    request.state.auth_type = "judge_sandbox" if judge_session else "open"
    request.state.user_id = "demo"
    if _canonical_fixture_write_blocked(request):
        return JSONResponse(
            {
                "error": "Canonical judge fixture is immutable",
                "detail": "Set DEMO_ORG_ID to the sandbox for interactive use.",
            },
            status_code=409,
        )
    return await call_next(request)


async def resolve_org_from_token(token: str) -> str | None:
    """Try to resolve an org_id from an API key token. Returns None if invalid."""
    try:
        org_id, _ = await _verify_agent_api_key(token)
        return org_id
    except Exception:  # noqa: BLE001
        return None
