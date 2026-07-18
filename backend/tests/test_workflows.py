"""Unit/API tests for the code-owned generalized workflow engine."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.schema import CompanyBrainSkill
from backend.workflows.models import (
    EvidenceInput,
    WorkflowOutcomeRequest,
    WorkflowRunRequest,
    WorkflowRunStatus,
    WorkflowVerdict,
    workflow_now,
)
from backend.workflows.service import WorkflowService
from backend.workflows.store import InMemoryWorkflowRepository


VALID_CONTEXTS: dict[str, dict[str, Any]] = {
    "release-safety": {
        "worker_memory_mb": 25,
        "runbook_validated": True,
        "deployment_window_open": True,
    },
    "money-safety": {
        "days_since_first_charge": 7,
        "is_enterprise_contract": False,
        "policy_exception_open": False,
    },
    "rollout-safety": {
        "error_rate_percent": 0.4,
        "sample_size": 1500,
        "incident_open": False,
    },
}


def _valid_evidence(service: WorkflowService, template_id: str) -> list[EvidenceInput]:
    template = service.get_template(template_id)
    now = workflow_now()
    return [
        EvidenceInput(
            source_type=source_type,
            source_name="Test source",
            external_id=f"{template_id}-{source_type}",
            occurred_at=now,
            excerpt=f"Fresh {source_type} evidence supports this evaluation.",
        )
        for source_type in template.required_source_types
    ]


@pytest.fixture
def service() -> WorkflowService:
    return WorkflowService(
        repository=InMemoryWorkflowRepository(),
        enable_qwen_compilation=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("template_id", ["release-safety", "money-safety", "rollout-safety"])
async def test_each_fixture_suspends_changed_prior_memory(service: WorkflowService, template_id: str):
    run = await service.run_workflow(
        WorkflowRunRequest(template_id=template_id, fixture=True),
        org_id="judge-demo",
    )
    assert run.is_demo_fixture is True
    assert run.decision_brief.verdict == WorkflowVerdict.SUSPENDED
    assert run.decision_brief.status == WorkflowRunStatus.SUSPENDED
    assert run.decision_brief.evidence
    assert all(item.is_demo_fixture for item in run.decision_brief.evidence)
    assert run.decision_brief.sag_trace["status"] == "evaluated"


@pytest.mark.asyncio
@pytest.mark.parametrize("template_id", ["release-safety", "money-safety", "rollout-safety"])
async def test_each_template_accepts_valid_evidence_but_requires_human_approval(
    service: WorkflowService, template_id: str
):
    run = await service.run_workflow(
        WorkflowRunRequest(
            template_id=template_id,
            evidence=_valid_evidence(service, template_id),
            live_context=VALID_CONTEXTS[template_id],
        ),
        org_id="sandbox",
    )
    assert run.is_demo_fixture is False
    assert run.decision_brief.verdict == WorkflowVerdict.PROCEED_WITH_HUMAN_APPROVAL
    assert run.decision_brief.status == WorkflowRunStatus.AWAITING_HUMAN_APPROVAL
    assert run.decision_brief.human_approval_required is True
    assert run.decision_brief.missing_evidence == []


@pytest.mark.asyncio
@pytest.mark.parametrize("template_id", ["release-safety", "money-safety", "rollout-safety"])
async def test_each_template_returns_review_not_a_fabricated_decision_when_evidence_is_missing(
    service: WorkflowService, template_id: str
):
    run = await service.run_workflow(
        WorkflowRunRequest(template_id=template_id, live_context=VALID_CONTEXTS[template_id]),
        org_id="sandbox",
    )
    assert run.decision_brief.verdict == WorkflowVerdict.REVIEW_REQUIRED
    assert run.decision_brief.status == WorkflowRunStatus.REVIEW_REQUIRED
    assert any(item.field == "evidence" for item in run.decision_brief.missing_evidence)
    assert run.decision_brief.sag_trace["status"] == "not_evaluated"


@pytest.mark.asyncio
@pytest.mark.parametrize("template_id", ["release-safety", "money-safety", "rollout-safety"])
async def test_approved_outcome_is_audited_and_resolves_a_run(service: WorkflowService, template_id: str):
    run = await service.run_workflow(
        WorkflowRunRequest(
            template_id=template_id,
            evidence=_valid_evidence(service, template_id),
            live_context=VALID_CONTEXTS[template_id],
        ),
        org_id="sandbox",
    )
    updated = await service.record_outcome(
        run.run_id,
        WorkflowOutcomeRequest(
            approved=True,
            outcome="confirmed_effective",
            note="Release owner verified the replacement runbook.",
            actor="engineering.owner@example.test",
        ),
        org_id="sandbox",
    )
    assert updated.decision_brief.status == WorkflowRunStatus.RESOLVED
    assert updated.outcomes[-1].approved is True
    assert updated.outcomes[-1].note == "Release owner verified the replacement runbook."
    # No compiled/persisted skill exists in this API-key-free unit test.
    assert updated.outcomes[-1].reinforcement_applied is False


@pytest.mark.asyncio
async def test_fixture_outcome_never_reinforces_but_real_confirmed_outcome_can(service, monkeypatch):
    calls: list[dict[str, Any]] = []

    async def fake_compile(event):
        return CompanyBrainSkill(skill_id="compiled-workflow-skill", name="Compiled workflow skill")

    async def fake_save_skill(skill, org_id="default"):
        return skill

    async def fake_record(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return {"reinforced": True}

    from backend.workflows import service as service_module

    monkeypatch.setattr(service_module.brain_store, "save_skill", fake_save_skill)
    guarded = WorkflowService(
        repository=InMemoryWorkflowRepository(),
        compile_event=fake_compile,
        human_outcome_recorder=fake_record,
        enable_qwen_compilation=True,
    )
    fixture = await guarded.run_workflow(
        WorkflowRunRequest(template_id="release-safety", fixture=True), org_id="judge-demo"
    )
    fixture_result = await guarded.record_outcome(
        fixture.run_id,
        WorkflowOutcomeRequest(approved=True, outcome="confirmed_effective", actor="judge"),
        org_id="judge-demo",
    )
    assert fixture_result.outcomes[-1].reinforcement_eligible is False
    assert calls == []

    real = await guarded.run_workflow(
        WorkflowRunRequest(
            template_id="release-safety",
            evidence=_valid_evidence(guarded, "release-safety"),
            live_context=VALID_CONTEXTS["release-safety"],
        ),
        org_id="sandbox",
    )
    real_result = await guarded.record_outcome(
        real.run_id,
        WorkflowOutcomeRequest(approved=True, outcome="confirmed_effective", actor="release-owner"),
        org_id="sandbox",
    )
    assert real_result.outcomes[-1].reinforcement_eligible is True
    assert real_result.outcomes[-1].reinforcement_applied is True
    assert calls[0]["args"][:4] == (
        "compiled-workflow-skill",
        "sandbox",
        "confirmed_effective",
        "release-owner",
    )


@pytest.mark.asyncio
async def test_existing_compiled_skill_is_reused_without_a_second_qwen_compile(monkeypatch):
    from backend.workflows import service as service_module

    async def fake_get_skill(skill_id, org_id="default"):
        assert skill_id == "github-pr-memory"
        assert org_id == "sandbox"
        return CompanyBrainSkill(
            skill_id="github-pr-memory",
            name="Persisted GitHub PR memory",
            summary="A merged PR changed a release assumption.",
        )

    async def should_not_compile(_event):
        raise AssertionError("existing compiled skill must prevent a second Qwen compile")

    monkeypatch.setattr(service_module.brain_store, "get_skill", fake_get_skill)
    reusable = WorkflowService(
        repository=InMemoryWorkflowRepository(),
        compile_event=should_not_compile,
        enable_qwen_compilation=True,
    )
    run = await reusable.run_workflow(
        WorkflowRunRequest(
            template_id="release-safety",
            evidence=_valid_evidence(reusable, "release-safety"),
            live_context=VALID_CONTEXTS["release-safety"],
            compiled_skill_id="github-pr-memory",
        ),
        org_id="sandbox",
    )
    compiled = [item for item in run.decision_brief.memory_refs if item.skill_id]
    assert len(compiled) == 1
    assert compiled[0].skill_id == "github-pr-memory"
    assert compiled[0].is_ephemeral is False
    assert compiled[0].provenance["reused_from_source_event"] is True


@pytest.mark.asyncio
async def test_source_catalog_keeps_canonical_fixture_data_separate_from_sandbox_inputs(service):
    canonical = await service.list_sources(org_id="judge-demo")
    assert len(canonical) == 8
    assert all(item.is_demo_fixture for item in canonical)

    await service.run_workflow(
        WorkflowRunRequest(
            template_id="release-safety",
            evidence=_valid_evidence(service, "release-safety"),
            live_context=VALID_CONTEXTS["release-safety"],
        ),
        org_id="sandbox",
    )
    sandbox = await service.list_sources(org_id="sandbox")
    assert any(not item.is_demo_fixture for item in sandbox)
    assert any(item.is_demo_fixture for item in sandbox)


def test_router_exposes_stable_workflow_contract(monkeypatch):
    from backend.routers import workflows

    local_service = WorkflowService(
        repository=InMemoryWorkflowRepository(), enable_qwen_compilation=False
    )
    monkeypatch.setattr(workflows, "service", local_service)
    app = FastAPI()
    app.include_router(workflows.router)
    client = TestClient(app)

    templates = client.get("/workflow-templates")
    assert templates.status_code == 200
    assert {item["template_id"] for item in templates.json()["templates"]} == {
        "release-safety",
        "money-safety",
        "rollout-safety",
    }
    created = client.post("/workflow-runs", json={"template_id": "release-safety", "fixture": True})
    assert created.status_code == 201
    payload = created.json()
    assert payload["decision_brief"]["verdict"] == "suspended"
    fetched = client.get(f"/workflow-runs/{payload['run_id']}")
    assert fetched.status_code == 200
    sources = client.get("/workflow-sources")
    assert sources.status_code == 200
    assert len(sources.json()["sources"]) == 8


def test_router_rejects_public_writes_to_the_canonical_judge_fixture(monkeypatch):
    from backend.routers import workflows

    local_service = WorkflowService(
        repository=InMemoryWorkflowRepository(), enable_qwen_compilation=False
    )
    monkeypatch.setattr(workflows, "service", local_service)
    monkeypatch.setattr(workflows.settings, "DEMO_ORG_ID", "judge-demo-v1")
    app = FastAPI()
    app.include_router(workflows.router)
    client = TestClient(app)

    response = client.post("/workflow-runs", json={"template_id": "release-safety", "fixture": True})
    assert response.status_code == 409
    assert "immutable" in response.json()["detail"]
