"""Coverage for the public four-module judge launchpad boundary."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.schema import CompanyBrainSkill
from backend.demo.judge_session import issue_judge_session, parse_judge_session
from backend.workflows.models import EvidenceInput, WorkflowOutcomeRequest, WorkflowRunRequest, workflow_now
from backend.workflows.service import WorkflowService
from backend.workflows.store import InMemoryWorkflowRepository


def _release_evidence() -> list[EvidenceInput]:
    now = workflow_now()
    return [
        EvidenceInput(
            source_type="github_pull_request",
            source_name="GitHub",
            external_id="PR-judge-sandbox",
            occurred_at=now,
            excerpt="A safe sample PR changed the worker configuration.",
        ),
        EvidenceInput(
            source_type="runtime_metric",
            source_name="Runtime",
            external_id="metric-judge-sandbox",
            occurred_at=now,
            excerpt="A safe sample runtime metric is available.",
        ),
    ]


def _release_context() -> dict[str, object]:
    return {
        "worker_memory_mb": 25,
        "runbook_validated": True,
        "deployment_window_open": True,
    }


def test_judge_session_is_signed_and_expires():
    token, session = issue_judge_session(now=10_000)
    parsed = parse_judge_session(token, now=10_001)
    assert parsed == session
    assert parsed.org_id.startswith("judge-sandbox:")
    assert parse_judge_session(f"{token}tampered", now=10_001) is None
    assert parse_judge_session(token, now=session.expires_at) is None


def test_demo_module_catalog_is_server_owned(monkeypatch):
    from backend.routers import workflows

    monkeypatch.setattr(workflows, "service", WorkflowService(repository=InMemoryWorkflowRepository(), enable_qwen_compilation=False))
    app = FastAPI()
    app.include_router(workflows.router)
    response = TestClient(app).get("/demo/modules")
    assert response.status_code == 200
    modules = response.json()["modules"]
    assert [module["id"] for module in modules] == [
        "workflow", "release-safety", "money-safety", "rollout-safety",
    ]
    assert all("route" in module and "primary_action" in module for module in modules)


def test_browser_session_scopes_runs_without_a_caller_org_override(monkeypatch):
    from backend.middleware.auth import auth_middleware
    from backend.routers import workflows

    monkeypatch.setattr(workflows, "service", WorkflowService(repository=InMemoryWorkflowRepository(), enable_qwen_compilation=False))
    app = FastAPI()
    app.middleware("http")(auth_middleware)
    app.include_router(workflows.router)
    client = TestClient(app)
    session = client.post("/demo/session")
    assert session.status_code == 200
    created = client.post(
        "/workflow-runs",
        json={"template_id": "release-safety", "fixture": True, "org_id": "pretend-org"},
    )
    assert created.status_code == 201
    assert created.json()["org_id"].startswith("judge-sandbox:")
    assert created.json()["is_judge_sandbox"] is True
    history = client.get("/workflow-runs")
    assert history.status_code == 200
    assert [run["run_id"] for run in history.json()["runs"]] == [created.json()["run_id"]]


def test_judge_mcp_key_is_disposable_scoped_and_bound_to_browser_org(monkeypatch):
    from backend.middleware.auth import auth_middleware
    from backend.routers import workflows

    captured: dict[str, object] = {}

    async def fake_create_api_key(org_id, name, permissions, expires_at=None):
        captured.update({"org_id": org_id, "name": name, "permissions": permissions, "expires_at": expires_at})
        return {
            "key_id": "judge-mcp-key",
            "api_key": "cbk_disposable",
            "org_id": org_id,
            "name": name,
            "permissions": permissions,
            "expires_at": expires_at.isoformat() if expires_at else None,
        }

    monkeypatch.setattr(workflows.brain_store, "create_api_key", fake_create_api_key)
    app = FastAPI()
    app.middleware("http")(auth_middleware)
    app.include_router(workflows.router)
    client = TestClient(app)

    assert client.post("/demo/mcp-session").status_code == 409
    assert client.post("/demo/session").status_code == 200
    created = client.post("/demo/mcp-session")
    assert created.status_code == 200
    body = created.json()
    assert body["api_key"] == "cbk_disposable"
    assert body["permissions"] == "mcp:read mcp:workflow"
    assert body["mcp_endpoint"].endswith("/mcp/")
    assert str(captured["org_id"]).startswith("judge-sandbox:")
    assert captured["permissions"] == "mcp:read mcp:workflow"
    assert captured["expires_at"] is not None


@pytest.mark.asyncio
async def test_judge_sandbox_memory_is_ephemeral_and_never_reinforces(monkeypatch):
    from backend.workflows import service as service_module

    saved: list[str] = []
    reinforced: list[str] = []

    async def fake_compile(_event):
        return CompanyBrainSkill(skill_id="sandbox-memory", name="Sandbox memory", summary="Sample memory")

    async def fake_save(skill, org_id="default"):
        saved.append(f"{skill.skill_id}:{org_id}")
        return skill

    async def fake_reinforce(*args, **kwargs):
        reinforced.append("called")
        return {"reinforced": True}

    monkeypatch.setattr(service_module.brain_store, "save_skill", fake_save)
    repo = InMemoryWorkflowRepository()
    service = WorkflowService(
        repository=repo,
        compile_event=fake_compile,
        human_outcome_recorder=fake_reinforce,
        enable_qwen_compilation=True,
    )
    run = await service.run_workflow(
        WorkflowRunRequest(template_id="release-safety", evidence=_release_evidence(), live_context=_release_context()),
        org_id="judge-sandbox:abc",
        is_judge_sandbox=True,
    )
    assert run.is_judge_sandbox is True
    assert run.expires_at is not None
    assert saved == []
    compiled = [memory for memory in run.decision_brief.memory_refs if memory.provenance.get("kind") == "compiled_event"]
    assert compiled and compiled[0].is_ephemeral is True

    updated = await service.record_outcome(
        run.run_id,
        WorkflowOutcomeRequest(approved=True, outcome="confirmed_effective", actor="judge"),
        org_id="judge-sandbox:abc",
    )
    assert updated.outcomes[-1].reinforcement_eligible is False
    assert reinforced == []

    await repo.purge_expired(now=run.expires_at + timedelta(seconds=1))
    assert await repo.get_run(run.run_id, "judge-sandbox:abc") is None
