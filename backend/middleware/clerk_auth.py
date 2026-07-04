"""Clerk + API key dual-auth middleware.

Priority (fastest → most authoritative):
1. Public paths → skip auth entirely.
2. X-Brain-Api-Key header → agent API key verified against MongoDB.
3. Authorization: Bearer <jwt> → Clerk JWT verified via JWKS.
4. Nothing matched → 401.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import jwt
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from jwt import PyJWKClient

from backend.brain.store import get_db
from backend.config import settings

logger = logging.getLogger(__name__)

# FastAPI route identifiers that are public (no auth required)
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

_jwk_client: PyJWKClient | None = None
_jwk_lock = asyncio.Lock()


async def _get_jwk_client() -> PyJWKClient:
    """Return a cached Clerk JWKS client, warming the key cache on first use."""
    global _jwk_client
    async with _jwk_lock:
        if _jwk_client is None:
            # Clerk Backend API JWKS endpoint requires the secret key.
            # A non-default User-Agent is required; Clerk blocks "Python-urllib".
            _jwk_client = PyJWKClient(
                settings.CLERK_JWKS_URL,
                headers={
                    "Authorization": f"Bearer {settings.CLERK_SECRET_KEY}",
                    "User-Agent": "CompanyBrain/1.0",
                },
            )
            # Warm the cache so the first authenticated request doesn't race on a
            # cold JWKS fetch and return 401 to the browser.
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, _jwk_client.fetch_data)
            except Exception as exc:  # noqa: BLE001
                logger.warning("JWKS warmup failed: %s", exc)
        return _jwk_client


async def _verify_clerk_jwt(token: str) -> dict[str, Any]:
    """Verify a Clerk JWT and return the decoded claims."""
    client = await _get_jwk_client()
    signing_key = client.get_signing_key_from_jwt(token)
    if signing_key is None:
        raise jwt.InvalidTokenError("No signing key found for token")
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        options={"verify_exp": True, "verify_aud": False},
        leeway=60,
    )


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
    return str(doc.get("org_id", "default")), str(doc.get("key_id", ""))


async def auth_middleware(request: Request, call_next: Any) -> Any:
    """FastAPI middleware extracting org_id + auth_type + user_id into request.state."""
    path = request.url.path

    # 1. Public paths – skip auth
    if path in _PUBLIC_PATHS:
        return await call_next(request)

    request.state.org_id = None
    request.state.auth_type = None
    request.state.user_id = None

    # 2. Agent API key
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

    # 3. Clerk JWT
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            claims = await _verify_clerk_jwt(token)
            user_id = claims.get("sub", "")
            # Use explicit Clerk org when present; otherwise isolate by user_id
            # so personal-account users never share the generic "default" org.
            org_id = claims.get("org_id") or claims.get("org_slug") or user_id or "default"
            request.state.org_id = org_id
            request.state.auth_type = "user"
            request.state.user_id = user_id
            return await call_next(request)
        except jwt.ExpiredSignatureError:
            return JSONResponse({"error": "Token expired"}, status_code=401)
        except jwt.InvalidTokenError:
            return JSONResponse({"error": "Invalid token"}, status_code=401)
        except Exception:  # noqa: BLE001
            logger.exception("Clerk JWT verification error")
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

    # 4. Nothing matched
    return JSONResponse({"error": "Unauthorized"}, status_code=401)


async def resolve_org_from_token(token: str) -> str | None:
    """Try to resolve an org_id from an API key token. Returns None if invalid."""
    try:
        org_id, _ = await _verify_agent_api_key(token)
        return org_id
    except Exception:  # noqa: BLE001
        return None
