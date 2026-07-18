"""Authentication and authorization helpers for the remote MCP endpoint.

The browser API can run in an intentionally open hackathon-demo mode.  Remote
MCP is different: every request is tied to a stored API key, and every tool
derives its organization from that key rather than from caller-supplied input.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from mcp.server.fastmcp import Context
from mcp.server.fastmcp.exceptions import ToolError
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from backend.brain.store import get_db
from backend.config import settings


logger = logging.getLogger(__name__)

MCP_READ_SCOPE = "mcp:read"
MCP_CHECK_SCOPE = "mcp:check"
MCP_WORKFLOW_SCOPE = "mcp:workflow"
MCP_WRITE_SCOPE = "mcp:write"
MCP_SCOPES = frozenset(
    {
        MCP_READ_SCOPE,
        MCP_CHECK_SCOPE,
        MCP_WORKFLOW_SCOPE,
        MCP_WRITE_SCOPE,
    }
)

# Existing dashboard keys may still use the pre-MCP permission names.  They
# remain valid API-key records but deliberately confer no MCP tool access.
_LEGACY_API_KEY_SCOPES = frozenset({"read:skills", "read:events"})
DEFAULT_MCP_API_KEY_PERMISSIONS = "mcp:read mcp:check mcp:workflow"


@dataclass(frozen=True)
class MCPPrincipal:
    """The server-resolved identity available to a single MCP request."""

    org_id: str
    key_id: str
    permissions: frozenset[str]


def parse_api_key_permissions(value: Any) -> frozenset[str]:
    """Parse the persisted space/comma-delimited permissions field safely."""
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = [str(item) for item in value]
    else:
        values = []
    parts: list[str] = []
    for item in values:
        parts.extend(part.strip() for part in re.split(r"[\s,]+", item) if part.strip())
    return frozenset(parts)


def validate_api_key_permissions(value: str) -> str:
    """Validate requested key permissions and return a normalized string.

    API keys are intentionally narrow capability grants.  We permit the two
    historical dashboard permissions for backward compatibility, but callers
    must opt into one of the explicit ``mcp:*`` scopes to use remote MCP.
    """
    permissions = parse_api_key_permissions(value)
    if not permissions:
        raise ValueError("At least one API-key permission is required")
    unsupported = permissions - MCP_SCOPES - _LEGACY_API_KEY_SCOPES
    if unsupported:
        allowed = ", ".join(sorted(MCP_SCOPES | _LEGACY_API_KEY_SCOPES))
        unknown = ", ".join(sorted(unsupported))
        raise ValueError(f"Unsupported API-key permission(s): {unknown}. Allowed: {allowed}")
    # Keep the display order deterministic without changing permission meaning.
    order = [
        MCP_READ_SCOPE,
        MCP_CHECK_SCOPE,
        MCP_WORKFLOW_SCOPE,
        MCP_WRITE_SCOPE,
        "read:skills",
        "read:events",
    ]
    return " ".join(permission for permission in order if permission in permissions)


async def authenticate_mcp_api_key(api_key: str) -> MCPPrincipal | None:
    """Resolve an MCP principal from a non-revoked stored API key."""
    if not api_key or not api_key.strip():
        return None
    db = get_db()
    doc = await db["api_keys"].find_one(
        {
            "api_key": api_key.strip(),
            "revoked_at": None,
        }
    )
    if not doc:
        return None
    return MCPPrincipal(
        org_id=str(doc.get("org_id", settings.DEMO_ORG_ID)),
        key_id=str(doc.get("key_id", "")),
        permissions=parse_api_key_permissions(doc.get("permissions", "")),
    )


def _configured_origins() -> frozenset[str]:
    raw = getattr(settings, "MCP_ALLOWED_ORIGINS", "")
    if isinstance(raw, str):
        candidates = re.split(r"[\s,]+", raw)
    elif isinstance(raw, (list, tuple, set, frozenset)):
        candidates = [str(value) for value in raw]
    else:
        candidates = []
    if not candidates:
        public_base_url = str(getattr(settings, "PUBLIC_BASE_URL", "") or "").strip()
        if public_base_url:
            candidates = [public_base_url]
    return frozenset(value.rstrip("/") for value in candidates if value.strip())


def _origin_is_allowed(origin: str) -> bool:
    # Non-browser MCP clients normally do not send Origin.  A browser-originated
    # request must match an explicit allowlist; an empty allowlist therefore
    # fails closed rather than inheriting the UI's permissive demo CORS policy.
    return origin.rstrip("/") in _configured_origins()


async def _json_error(
    scope: Scope,
    receive: Receive,
    send: Send,
    *,
    status_code: int,
    error: str,
    detail: str,
) -> None:
    response = JSONResponse({"error": error, "detail": detail}, status_code=status_code)
    await response(scope, receive, send)


class MCPApiKeyAuthMiddleware:
    """ASGI middleware that authenticates every Streamable HTTP MCP request.

    It stores a server-resolved principal on the request scope.  FastMCP carries
    this same Starlette request into each tool context, so tool wrappers can
    enforce the individual capability scope without accepting ``org_id`` from
    an agent.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not bool(getattr(settings, "MCP_REMOTE_ENABLED", True)):
            await _json_error(
                scope,
                receive,
                send,
                status_code=503,
                error="MCP_REMOTE_DISABLED",
                detail="Remote MCP is disabled by server configuration.",
            )
            return
        # Do not silently turn a remote connector into an unauthenticated one
        # if an environment variable is misconfigured.
        if not bool(getattr(settings, "MCP_REQUIRE_API_KEY", True)):
            logger.error("MCP_REQUIRE_API_KEY=false; refusing to expose remote MCP")
            await _json_error(
                scope,
                receive,
                send,
                status_code=503,
                error="MCP_AUTH_MISCONFIGURED",
                detail="Remote MCP requires API-key authentication.",
            )
            return

        request = Request(scope, receive)
        origin = request.headers.get("origin")
        if origin and not _origin_is_allowed(origin):
            await _json_error(
                scope,
                receive,
                send,
                status_code=403,
                error="MCP_ORIGIN_FORBIDDEN",
                detail="Browser origin is not allowed for remote MCP.",
            )
            return

        api_key = request.headers.get("X-Brain-Api-Key", "")
        if not api_key:
            await _json_error(
                scope,
                receive,
                send,
                status_code=401,
                error="MCP_API_KEY_REQUIRED",
                detail="Provide X-Brain-Api-Key to use remote MCP.",
            )
            return
        try:
            principal = await authenticate_mcp_api_key(api_key)
        except Exception:  # noqa: BLE001
            logger.exception("MCP API-key verification failed")
            await _json_error(
                scope,
                receive,
                send,
                status_code=503,
                error="MCP_AUTH_UNAVAILABLE",
                detail="Unable to verify the API key right now.",
            )
            return
        if principal is None:
            await _json_error(
                scope,
                receive,
                send,
                status_code=401,
                error="MCP_API_KEY_INVALID",
                detail="The supplied API key is invalid or revoked.",
            )
            return
        if not (principal.permissions & MCP_SCOPES):
            await _json_error(
                scope,
                receive,
                send,
                status_code=403,
                error="MCP_SCOPE_REQUIRED",
                detail="This API key has no remote MCP capability scope.",
            )
            return

        scope.setdefault("state", {})["mcp_principal"] = principal
        await self.app(scope, receive, send)


def require_mcp_scope(ctx: Context, required_scope: str) -> MCPPrincipal:
    """Return the request principal or reject an MCP tool call safely."""
    try:
        request = ctx.request_context.request
    except Exception as exc:  # noqa: BLE001
        raise ToolError("Remote MCP request context is unavailable") from exc
    principal = getattr(getattr(request, "state", None), "mcp_principal", None)
    if not isinstance(principal, MCPPrincipal):
        raise ToolError("Remote MCP request was not authenticated")
    if required_scope not in principal.permissions:
        raise ToolError(f"MCP API key lacks required scope: {required_scope}")
    return principal
