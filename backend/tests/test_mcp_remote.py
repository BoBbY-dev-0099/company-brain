"""Regression tests for the authenticated Streamable HTTP MCP connector."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from backend.config import settings
from backend.mcp import auth as mcp_auth
from backend.mcp import server as mcp_server_module
from backend.workflows.models import workflow_now
from backend.workflows.service import WorkflowService
from backend.workflows.store import InMemoryWorkflowRepository


class _FakeRequestState:
    def __init__(self, principal: mcp_auth.MCPPrincipal) -> None:
        self.mcp_principal = principal


class _FakeRequest:
    def __init__(self, principal: mcp_auth.MCPPrincipal) -> None:
        self.state = _FakeRequestState(principal)


class _FakeContext:
    def __init__(self, principal: mcp_auth.MCPPrincipal) -> None:
        self.request_context = type("RequestContext", (), {"request": _FakeRequest(principal)})()


def _principal(org_id: str, *scopes: str) -> mcp_auth.MCPPrincipal:
    return mcp_auth.MCPPrincipal(org_id=org_id, key_id=f"key-{org_id}", permissions=frozenset(scopes))


def _streamable_app(server) -> FastAPI:
    """Host a fresh FastMCP instance with the lifespan it requires."""
    child = mcp_auth.MCPApiKeyAuthMiddleware(server.streamable_http_app())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        async with server.session_manager.run():
            yield

    app = FastAPI(lifespan=lifespan)
    app.mount("/mcp", child)
    return app


def _headers(api_key: str) -> dict[str, str]:
    return {
        "X-Brain-Api-Key": api_key,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }


def _jsonrpc(method: str, request_id: int, params: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}


def _tool_result(response) -> dict:
    payload = response.json()
    content = payload["result"]["content"][0]
    return json.loads(content["text"])


def _valid_release_evidence(*, age_hours: float = 0) -> list[dict]:
    occurred_at = workflow_now() - timedelta(hours=age_hours)
    return [
        {
            "source_type": "github_pull_request",
            "source_name": "GitHub",
            "external_id": "org/repo#42",
            "occurred_at": occurred_at.isoformat(),
            "excerpt": "Merged change lowers worker memory from 25 MiB to 8 MiB.",
            "metadata": {
                "changed_field": "worker_memory_mb",
                "previous_value": 25,
                "current_value": 8,
            },
        },
        {
            "source_type": "runtime_metric",
            "source_name": "Runtime telemetry",
            "external_id": "worker-memory",
            "occurred_at": occurred_at.isoformat(),
            "excerpt": "Worker effective limit is now 8 MiB.",
        },
    ]


def _release_context() -> dict:
    return {
        "worker_memory_mb": 8,
        "runbook_validated": False,
        "deployment_window_open": True,
    }


def test_permission_validation_keeps_write_opt_in():
    assert mcp_auth.validate_api_key_permissions("mcp:workflow mcp:read") == "mcp:read mcp:workflow"
    assert "mcp:write" not in mcp_auth.DEFAULT_MCP_API_KEY_PERMISSIONS
    with pytest.raises(ValueError, match="Unsupported"):
        mcp_auth.validate_api_key_permissions("mcp:read superuser")


def test_mcp_middleware_enforces_key_and_browser_origin(monkeypatch):
    monkeypatch.setattr(settings, "MCP_REMOTE_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_REQUIRE_API_KEY", True)
    monkeypatch.setattr(settings, "MCP_ALLOWED_ORIGINS", "https://brain.veriflowai.me")

    async def fake_authenticate(api_key: str):
        return _principal("org-a", mcp_auth.MCP_READ_SCOPE) if api_key == "valid" else None

    monkeypatch.setattr(mcp_auth, "authenticate_mcp_api_key", fake_authenticate)
    app = FastAPI()

    @app.post("/")
    async def principal_echo(request: Request):
        return {"org_id": request.state.mcp_principal.org_id}

    secured = mcp_auth.MCPApiKeyAuthMiddleware(app)
    with TestClient(secured) as client:
        missing = client.post("/", headers={"Content-Type": "application/json"})
        assert missing.status_code == 401
        invalid = client.post("/", headers={"X-Brain-Api-Key": "bad", "Content-Type": "application/json"})
        assert invalid.status_code == 401
        forbidden = client.post(
            "/",
            headers={
                "X-Brain-Api-Key": "valid",
                "Origin": "https://untrusted.example",
                "Content-Type": "application/json",
            },
        )
        assert forbidden.status_code == 403
        allowed = client.post(
            "/",
            headers={
                "X-Brain-Api-Key": "valid",
                "Origin": "https://brain.veriflowai.me",
                "Content-Type": "application/json",
            },
        )
        assert allowed.status_code == 200
        assert allowed.json() == {"org_id": "org-a"}


def test_transport_security_uses_public_hostname_and_origin(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://brain.veriflowai.me")
    monkeypatch.setattr(settings, "MCP_ALLOWED_ORIGINS", "")
    policy = mcp_server_module._default_transport_security()

    assert policy.enable_dns_rebinding_protection is True
    assert "brain.veriflowai.me" in policy.allowed_hosts
    assert "brain.veriflowai.me:*" in policy.allowed_hosts
    assert policy.allowed_origins == ["https://brain.veriflowai.me"]


@pytest.mark.asyncio
async def test_evaluate_workflow_returns_auditable_briefs_and_never_uses_caller_org(monkeypatch):
    service = WorkflowService(
        repository=InMemoryWorkflowRepository(),
        enable_qwen_compilation=False,
    )
    monkeypatch.setattr(mcp_server_module, "workflow_service", service)
    server = mcp_server_module.create_mcp_server(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
    evaluate = server._tool_manager.get_tool("evaluate_workflow").fn
    principal = _principal("org-a", mcp_auth.MCP_WORKFLOW_SCOPE)
    context = _FakeContext(principal)

    valid = await evaluate(
        template_id="release-safety",
        evidence=_valid_release_evidence(),
        live_context={**_release_context(), "org_id": "org-b"},
        ctx=context,
    )
    assert valid["org_id"] == "org-a"
    assert valid["decision_brief"]["verdict"] == "suspended"
    assert valid["decision_brief"]["human_approval_required"] is True

    stale = await evaluate(
        template_id="release-safety",
        evidence=_valid_release_evidence(age_hours=200),
        live_context=_release_context(),
        ctx=context,
    )
    assert stale["decision_brief"]["verdict"] == "review_required"
    assert any(item["field"] == "freshness" for item in stale["decision_brief"]["missing_evidence"])

    missing = await evaluate(
        template_id="release-safety",
        evidence=[],
        live_context=_release_context(),
        ctx=context,
    )
    assert missing["decision_brief"]["verdict"] == "review_required"
    assert any(item["field"] == "evidence" for item in missing["decision_brief"]["missing_evidence"])


@pytest.mark.asyncio
async def test_mcp_tool_scope_and_human_action_gate(monkeypatch):
    async def fake_check(**kwargs):
        return {
            "result": "auto_execute",
            "auto_execute": True,
            "org_id_seen": kwargs["org_id"],
        }

    monkeypatch.setattr(mcp_server_module.tools, "check_intercept", fake_check)
    server = mcp_server_module.create_mcp_server(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
    check = server._tool_manager.get_tool("check_intercept").fn

    with pytest.raises(ToolError, match="mcp:check"):
        await check(
            agent_id="agent-1",
            decision_text="ship it",
            ctx=_FakeContext(_principal("org-a", mcp_auth.MCP_READ_SCOPE)),
        )

    result = await check(
        agent_id="agent-1",
        decision_text="ship it",
        ctx=_FakeContext(_principal("org-a", mcp_auth.MCP_CHECK_SCOPE)),
    )
    assert result["org_id_seen"] == "org-a"
    assert result["auto_execute"] is False
    assert result["human_approval_required"] is True
    assert result["external_action_permitted"] is False


def test_authenticated_streamable_http_mcp_e2e_and_org_isolation(monkeypatch):
    monkeypatch.setattr(settings, "MCP_REMOTE_ENABLED", True)
    monkeypatch.setattr(settings, "MCP_REQUIRE_API_KEY", True)
    principals = {
        "key-org-a": _principal(
            "org-a",
            mcp_auth.MCP_READ_SCOPE,
            mcp_auth.MCP_CHECK_SCOPE,
            mcp_auth.MCP_WORKFLOW_SCOPE,
        ),
        "key-org-b": _principal("org-b", mcp_auth.MCP_READ_SCOPE),
    }

    async def fake_authenticate(api_key: str):
        return principals.get(api_key)

    async def fake_recall(*, context: str, top_k: int, org_id: str):
        return {"skills": [{"context": context, "org_id": org_id}]}

    async def fake_check(**kwargs):
        return {"result": "clear", "auto_execute": True, "org_id_seen": kwargs["org_id"]}

    monkeypatch.setattr(mcp_auth, "authenticate_mcp_api_key", fake_authenticate)
    monkeypatch.setattr(mcp_server_module.tools, "recall_skills", fake_recall)
    monkeypatch.setattr(mcp_server_module.tools, "check_intercept", fake_check)
    monkeypatch.setattr(
        mcp_server_module,
        "workflow_service",
        WorkflowService(repository=InMemoryWorkflowRepository(), enable_qwen_compilation=False),
    )
    server = mcp_server_module.create_mcp_server(
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False)
    )
    app = _streamable_app(server)
    initialize = _jsonrpc(
        "initialize",
        1,
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        },
    )

    with TestClient(app) as client:
        assert client.post("/mcp/", headers=_headers("missing"), json=initialize).status_code == 401
        assert client.post("/mcp/", json=initialize).status_code == 401

        initialized = client.post("/mcp/", headers=_headers("key-org-a"), json=initialize)
        assert initialized.status_code == 200
        tools = client.post("/mcp/", headers=_headers("key-org-a"), json=_jsonrpc("tools/list", 2, {}))
        assert tools.status_code == 200
        assert {tool["name"] for tool in tools.json()["result"]["tools"]} == {
            "recall_skills",
            "check_intercept",
            "evaluate_workflow",
            "compile_experience",
        }

        # The stray org_id is ignored; the key is the only organization source.
        recall_a = client.post(
            "/mcp/",
            headers=_headers("key-org-a"),
            json=_jsonrpc(
                "tools/call",
                3,
                {"name": "recall_skills", "arguments": {"context": "deploy", "org_id": "org-b"}},
            ),
        )
        assert recall_a.status_code == 200
        assert _tool_result(recall_a)["skills"][0]["org_id"] == "org-a"

        check = client.post(
            "/mcp/",
            headers=_headers("key-org-a"),
            json=_jsonrpc(
                "tools/call",
                4,
                {"name": "check_intercept", "arguments": {"agent_id": "agent-a", "decision_text": "deploy"}},
            ),
        )
        check_result = _tool_result(check)
        assert check_result["org_id_seen"] == "org-a"
        assert check_result["auto_execute"] is False
        assert check_result["human_approval_required"] is True

        evaluated = client.post(
            "/mcp/",
            headers=_headers("key-org-a"),
            json=_jsonrpc(
                "tools/call",
                5,
                {
                    "name": "evaluate_workflow",
                    "arguments": {
                        "template_id": "release-safety",
                        "evidence": _valid_release_evidence(),
                        "live_context": _release_context(),
                    },
                },
            ),
        )
        assert _tool_result(evaluated)["org_id"] == "org-a"

        recall_b = client.post(
            "/mcp/",
            headers=_headers("key-org-b"),
            json=_jsonrpc("tools/call", 6, {"name": "recall_skills", "arguments": {"context": "deploy"}}),
        )
        assert _tool_result(recall_b)["skills"][0]["org_id"] == "org-b"

        denied = client.post(
            "/mcp/",
            headers=_headers("key-org-b"),
            json=_jsonrpc(
                "tools/call",
                7,
                {"name": "check_intercept", "arguments": {"agent_id": "agent-b", "decision_text": "deploy"}},
            ),
        )
        assert denied.status_code == 200
        assert denied.json()["result"]["isError"] is True
        assert "mcp:check" in denied.json()["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_main_mcp_routes_redirect_and_retire_legacy(monkeypatch):
    """Legacy SSE must be an explicit migration response, never a public connector."""
    from httpx import ASGITransport, AsyncClient

    from backend.main import app

    monkeypatch.setattr(settings, "MCP_REMOTE_ENABLED", True)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        legacy = await client.get("/mcp/sse")
        assert legacy.status_code == 410
        assert legacy.json()["migration_endpoint"] == "/mcp/"
        canonical = await client.get("/mcp", follow_redirects=False)
        assert canonical.status_code == 308
        assert canonical.headers["location"] == "/mcp/"
