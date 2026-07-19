"""Operator-only, encrypted source-connector setup surface."""

from __future__ import annotations

from typing import Any, Literal

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from backend.config import settings
from backend.sources.adapters import GoogleDriveAdapter
from backend.sources.runtime_config import (
    list_runtime_config,
    load_runtime_config,
    operator_setup_enabled,
    save_runtime_config,
    setup_instructions,
    verify_operator_token,
)


router = APIRouter(prefix="/operator/integrations", tags=["operator-integrations"])
Provider = Literal["slack", "github", "google_drive", "web"]


class IntegrationConfigRequest(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


def _require_operator(token: str | None) -> None:
    if not operator_setup_enabled():
        raise HTTPException(
            status_code=503,
            detail="Operator setup is disabled. Set INTEGRATION_ADMIN_TOKEN and INTEGRATION_CONFIG_ENCRYPTION_KEY on the server.",
        )
    if not verify_operator_token(token):
        raise HTTPException(status_code=401, detail="Operator unlock token is invalid")


def _validate_provider(provider: str) -> Provider:
    if provider not in {"slack", "github", "google_drive", "web"}:
        raise HTTPException(status_code=404, detail="Unsupported integration provider")
    return provider  # type: ignore[return-value]


@router.get("/setup")
async def operator_setup_metadata() -> dict[str, Any]:
    """Public, credential-free details for the Integration Studio cards."""
    return setup_instructions()


@router.get("/config")
async def operator_config(
    x_integration_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_operator(x_integration_admin_token)
    return {"providers": await list_runtime_config()}


@router.put("/{provider}")
async def configure_provider(
    provider: str,
    body: IntegrationConfigRequest,
    x_integration_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _require_operator(x_integration_admin_token)
    selected = _validate_provider(provider)
    try:
        configured = await save_runtime_config(selected, body.values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"provider": configured, "message": "Saved encrypted server-side. Secret values are never returned."}


@router.post("/{provider}/test")
async def test_provider(
    provider: str,
    x_integration_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Run a non-mutating provider reachability check.

    These checks never post messages, change repository state, write Drive
    content, or ingest evidence.  A successful event/sync remains the final
    proof for source ingestion.
    """
    _require_operator(x_integration_admin_token)
    selected = _validate_provider(provider)
    await load_runtime_config()
    if selected == "slack":
        if not settings.SLACK_SIGNING_SECRET or not settings.SLACK_ALLOWED_TEAM_ID or not settings.SLACK_ALLOWED_CHANNEL_IDS:
            raise HTTPException(status_code=422, detail="Slack signing secret, team ID, and channel IDs are required")
        if not settings.SLACK_BOT_TOKEN:
            return {
                "ok": True,
                "status": "ready_for_signed_event",
                "detail": "Slack is configured to receive signed Events API callbacks. Add an optional bot token to run auth.test, or send a test incident message.",
            }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"},
            )
            payload = response.json()
        if not response.is_success or not payload.get("ok"):
            raise HTTPException(status_code=502, detail=f"Slack auth.test failed: {payload.get('error', 'unknown error')}")
        return {"ok": True, "status": "verified", "detail": f"Slack app authenticated as {payload.get('user') or payload.get('bot_id') or 'configured app'}."}
    if selected == "github":
        repositories = [item.strip() for item in settings.GITHUB_REPOS.split(",") if item.strip()]
        if not settings.GITHUB_TOKEN or not repositories:
            raise HTTPException(status_code=422, detail="GitHub token and repository allowlist are required")
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(
                f"https://api.github.com/repos/{repositories[0]}",
                headers={"Authorization": f"Bearer {settings.GITHUB_TOKEN}", "Accept": "application/vnd.github+json"},
            )
        if not response.is_success:
            raise HTTPException(status_code=502, detail=f"GitHub repository read failed with HTTP {response.status_code}")
        payload = response.json()
        return {"ok": True, "status": "verified", "detail": f"Read-only access verified for {payload.get('full_name', repositories[0])}."}
    if selected == "google_drive":
        try:
            documents = await GoogleDriveAdapter().list_documents()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Drive read test failed: {str(exc)[:300]}") from exc
        return {"ok": True, "status": "verified", "detail": f"Read-only Drive access verified; {len(documents)} allowed document(s) are currently visible."}
    if not settings.WEB_EVIDENCE_ALLOWED_HOSTS.strip():
        raise HTTPException(status_code=422, detail="At least one HTTPS host must be allowlisted")
    return {"ok": True, "status": "configured", "detail": "Host allowlist is active. A workflow or MCP write-scoped key can now fetch an explicit HTTPS URL."}

