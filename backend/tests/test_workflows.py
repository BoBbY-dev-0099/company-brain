"""Core contract tests for the one code-owned NexaFlow workflow."""

from __future__ import annotations

import pytest

from backend.workflows.models import EvidenceInput, WorkflowOutcomeRequest, WorkflowRunRequest, WorkflowRunStatus, WorkflowVerdict, workflow_now
from backend.workflows.service import WorkflowService
from backend.workflows.store import InMemoryWorkflowRepository


TEMPLATE = "nexaflow-release-safety"


def _evidence() -> list[EvidenceInput]:
    now = workflow_now()
    return [
        EvidenceInput(source_type="slack_message", source_name="Slack", external_id="incident-1", occurred_at=now, excerpt="SEV-2 resolved."),
        EvidenceInput(source_type="google_drive_document", source_name="Drive", external_id="runbook-1", occurred_at=now, excerpt="Workers require at least 24 MiB."),
        EvidenceInput(source_type="github_pull_request", source_name="GitHub", external_id="pr-1", occurred_at=now, excerpt="Merged worker configuration is 32 MiB."),
    ]


@pytest.fixture
def service() -> WorkflowService:
    return WorkflowService(repository=InMemoryWorkflowRepository(), enable_qwen_compilation=False)


@pytest.mark.asyncio
async def test_safe_evidence_requires_human_approval(service: WorkflowService):
    run = await service.run_workflow(
        WorkflowRunRequest(template_id=TEMPLATE, evidence=_evidence(), live_context={"configured_memory_meets_runbook": True, "linked_incident_open": False}),
        org_id="nexaflow-demo",
    )
    assert run.decision_brief.verdict == WorkflowVerdict.PROCEED_WITH_HUMAN_APPROVAL
    assert run.decision_brief.status == WorkflowRunStatus.AWAITING_HUMAN_APPROVAL
    assert run.decision_brief.human_approval_required is True


@pytest.mark.asyncio
async def test_changed_condition_suspends(service: WorkflowService):
    run = await service.run_workflow(
        WorkflowRunRequest(template_id=TEMPLATE, evidence=_evidence(), live_context={"configured_memory_meets_runbook": False, "linked_incident_open": True}),
        org_id="nexaflow-demo",
    )
    assert run.decision_brief.verdict == WorkflowVerdict.SUSPENDED
    assert run.decision_brief.status == WorkflowRunStatus.SUSPENDED
    assert run.decision_brief.sag_trace["status"] == "evaluated"


@pytest.mark.asyncio
async def test_missing_evidence_returns_review(service: WorkflowService):
    run = await service.run_workflow(
        WorkflowRunRequest(template_id=TEMPLATE, evidence=_evidence()[:2], live_context={"configured_memory_meets_runbook": True}),
        org_id="nexaflow-demo",
    )
    assert run.decision_brief.verdict == WorkflowVerdict.REVIEW_REQUIRED
    assert any(item.field == "source_type" for item in run.decision_brief.missing_evidence)
    assert any(item.field == "linked_incident_open" for item in run.decision_brief.missing_evidence)


@pytest.mark.asyncio
async def test_human_outcome_resolves_without_external_execution(service: WorkflowService):
    run = await service.run_workflow(
        WorkflowRunRequest(template_id=TEMPLATE, evidence=_evidence(), live_context={"configured_memory_meets_runbook": False, "linked_incident_open": True}),
        org_id="nexaflow-demo",
    )
    updated = await service.record_outcome(
        run.run_id,
        WorkflowOutcomeRequest(approved=True, outcome="confirmed_effective", actor="release.owner@nexaflow.test", note="Release remains paused."),
        org_id="nexaflow-demo",
    )
    assert updated.decision_brief.status == WorkflowRunStatus.RESOLVED
    assert updated.outcomes[-1].reinforcement_applied is False
