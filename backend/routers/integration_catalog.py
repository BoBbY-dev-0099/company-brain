"""Truthful, server-defined connection catalog for the judge-facing UI.

The catalog deliberately describes only connection paths that exist in this
submission. It is configuration-derived, does not expose secret values, and
keeps adapter fixtures distinct from real configured sources.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter

from backend.config import settings
from backend.workflows.models import workflow_now


router = APIRouter(tags=["integrations"])

_STATUS_DEFINITIONS = {
    "connected": "A real, configured connection is available on this deployment.",
    "setup_required": "The connector exists, but required server configuration is missing.",
    "contract_ready": "A stable HTTP contract is available for a company to call.",
    "fixture": "A deterministic demo adapter or example; it is not a live connector.",
    "preview": "An implemented capability that is not yet configured as a production connection.",
}


def _normalise_base_url(value: str) -> str:
    return value.strip().rstrip("/")


def _public_endpoint(path: str) -> str:
    """Return a public endpoint when configured, otherwise a stable API path."""
    base_url = _normalise_base_url(settings.PUBLIC_BASE_URL)
    return f"{base_url}{path}" if base_url else path


def _github_configuration() -> dict[str, bool]:
    """Return capability flags only; never reveal a secret or token."""
    return {
        "webhook_secret": bool(settings.GITHUB_WEBHOOK_SECRET.strip()),
        "repository_allowlist": bool(settings.GITHUB_REPOS.strip()),
        "github_token": bool(settings.GITHUB_TOKEN.strip()),
    }


def _github_is_connected(configuration: dict[str, bool]) -> bool:
    # The current intake fetches a merged PR diff with a token and verifies an
    # HMAC signature. A non-empty allowlist prevents treating an unscoped
    # webhook endpoint as a completed company connection.
    return all(configuration.values())


def _mcp_is_connected() -> bool:
    base_url = _normalise_base_url(settings.PUBLIC_BASE_URL)
    return bool(
        base_url.startswith("https://")
        and settings.MCP_REMOTE_ENABLED
        and settings.MCP_REQUIRE_API_KEY
        and settings.MCP_TRANSPORT == "streamable-http"
    )


def build_integration_catalog() -> dict[str, Any]:
    """Build a serialisable catalog from runtime configuration.

    Keep the endpoint paths in one place so API clients and the frontend cannot
    drift into claiming connectors that have not been configured.
    """
    github_configuration = _github_configuration()
    github_connected = _github_is_connected(github_configuration)
    mcp_connected = _mcp_is_connected()
    base_url = _normalise_base_url(settings.PUBLIC_BASE_URL)
    fresh_timestamp = workflow_now().isoformat()
    workflow_example_body = {
        "template_id": "release-safety",
        "evidence": [
            {
                "source_type": "github_pull_request",
                "source_name": "GitHub",
                "external_id": "acme/service#42",
                "occurred_at": fresh_timestamp,
                "excerpt": "Merged PR #42 updates the export worker deployment configuration.",
            },
            {
                "source_type": "runtime_metric",
                "source_name": "Runtime telemetry",
                "external_id": "export-worker-memory",
                "occurred_at": fresh_timestamp,
                "excerpt": "export-worker effective memory limit is 25 MiB.",
            },
        ],
        "live_context": {
            "worker_memory_mb": 25,
            "runbook_validated": True,
            "deployment_window_open": True,
        },
    }
    workflow_example_json = json.dumps(workflow_example_body, separators=(",", ":"))

    boundaries: list[dict[str, Any]] = [
        {
            "id": "evidence",
            "title": "Connect evidence",
            "status": "connected" if github_connected else "setup_required",
            "description": (
                "Signed GitHub merged-PR intake persists raw evidence, compiled memory, "
                "audit record, and a workflow decision before acknowledging delivery."
            ),
            "connector": "github_merged_pull_request",
            "endpoint": _public_endpoint("/integrations/github/pr"),
            "requirements": [
                "GitHub webhook secret",
                "GitHub token for merged PR diff retrieval",
                "Explicit repository allowlist",
            ],
            "configuration": github_configuration,
            "scope": "The submission implements one signed GitHub intake, not self-service GitHub App onboarding.",
        },
        {
            "id": "workflow",
            "title": "Connect a workflow",
            "status": "contract_ready",
            "description": (
                "Any company workflow can submit normalized evidence and live context, "
                "then receive the same auditable DecisionBrief used by the inbox."
            ),
            "contracts": [
                {
                    "method": "POST",
                    "path": "/workflow-runs",
                    "endpoint": _public_endpoint("/workflow-runs"),
                    "purpose": "Evidence -> memory -> SAG -> DecisionBrief",
                },
                {
                    "method": "POST",
                    "path": "/decisions/check",
                    "endpoint": _public_endpoint("/decisions/check"),
                    "purpose": "Pre-flight memory and deterministic safety check",
                },
            ],
            "requirements": ["X-Brain-Api-Key for an organization-scoped call"],
            "example": {
                "language": "bash",
                "description": "Submit source-backed evidence and current live context.",
                "method": "POST",
                "path": "/workflow-runs",
                "headers": {
                    "Content-Type": "application/json",
                    "X-Brain-Api-Key": "cb_live_...",
                },
                "body": workflow_example_body,
                "code": (
                    "curl -X POST {base_url}/workflow-runs \\\n"
                    "  -H 'Content-Type: application/json' \\\n"
                    "  -H 'X-Brain-Api-Key: cb_live_...' \\\n"
                    "  -d '{body}'"
                ).format(
                    base_url=base_url or "http://localhost:8000",
                    body=workflow_example_json,
                ),
            },
        },
        {
            "id": "agent",
            "title": "Connect an agent",
            "status": "connected" if mcp_connected else "preview",
            "description": (
                "An MCP client can call Company Brain before a consequential action; "
                "the server, not the caller, resolves organization identity from its API key."
            ),
            "transport": "streamable-http",
            "endpoint": _public_endpoint("/mcp/"),
            "tools": [
                {"name": "recall_skills", "permission": "mcp:read"},
                {"name": "check_intercept", "permission": "mcp:check"},
                {"name": "evaluate_workflow", "permission": "mcp:workflow"},
                {"name": "compile_experience", "permission": "mcp:write"},
            ],
            "requirements": [
                "X-Brain-Api-Key on every request",
                "Scoped permission for each tool",
                "Human confirmation remains outside MCP",
            ],
            "configuration": {
                "public_https_base_url": base_url.startswith("https://"),
                "remote_enabled": settings.MCP_REMOTE_ENABLED,
                "api_key_required": settings.MCP_REQUIRE_API_KEY,
                "transport": settings.MCP_TRANSPORT,
                "legacy_sse_retired": True,
            },
            "scope": "OAuth 2.1 is a production roadmap, not a hackathon claim.",
        },
    ]

    return {
        "version": 1,
        "positioning": (
            "Company Brain does not replace a company's agents or systems. It is the "
            "governed memory checkpoint they call before consequential actions."
        ),
        "public_base_url": base_url or None,
        "connection_boundaries": boundaries,
        # Alias intentionally kept for simple UI consumers; both values are
        # server-defined and identical.
        "connections": boundaries,
        "status_definitions": _STATUS_DEFINITIONS,
    }


@router.get("/integration-catalog")
async def get_integration_catalog() -> dict[str, Any]:
    """List real configured connections, stable contracts, and fixtures honestly."""
    return build_integration_catalog()
