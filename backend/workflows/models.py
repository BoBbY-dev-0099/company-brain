"""Typed public contracts for Company Brain operational workflows."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def workflow_now() -> datetime:
    """Timezone-aware clock used by all workflow records."""
    return datetime.now(timezone.utc)


class WorkflowMemoryType(str, Enum):
    POLICY = "policy"
    INCIDENT = "incident"
    DECISION = "decision"
    COMMITMENT = "commitment"
    EXCEPTION = "exception"


class EvidenceAvailability(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class EvidenceFreshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class WorkflowVerdict(str, Enum):
    """The decision from deterministic evidence/SAG evaluation.

    ``proceed_with_human_approval`` is intentionally not an auto-execution
    outcome.  Every workflow in this package remains human approved.
    """

    PROCEED_WITH_HUMAN_APPROVAL = "proceed_with_human_approval"
    SUSPENDED = "suspended"
    REVIEW_REQUIRED = "review_required"


class WorkflowRunStatus(str, Enum):
    AWAITING_HUMAN_APPROVAL = "awaiting_human_approval"
    SUSPENDED = "suspended"
    REVIEW_REQUIRED = "review_required"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class LiveContextField(BaseModel):
    name: str
    value_type: str
    required: bool = True
    description: str


class WorkflowEvaluationCase(BaseModel):
    case_id: str
    description: str
    expected_verdict: WorkflowVerdict


class EvidenceInput(BaseModel):
    """Inbound material before it is normalized into a source-backed record."""

    source_type: str = "unknown"
    source_name: str | None = None
    external_id: str | None = None
    url: str | None = None
    occurred_at: datetime | None = None
    excerpt: str = ""
    availability: EvidenceAvailability = EvidenceAvailability.AVAILABLE
    # A caller may report freshness, but the service recomputes stale records
    # against the template's freshness window rather than trusting the claim.
    freshness: EvidenceFreshness | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRecord(EvidenceInput):
    """Normalized evidence stored on a workflow run and source catalog."""

    evidence_id: str
    template_id: str
    scenario_version: str
    org_id: str = "default"
    is_demo_fixture: bool = False
    normalized_at: datetime = Field(default_factory=workflow_now)
    freshness: EvidenceFreshness = EvidenceFreshness.UNKNOWN


class WorkflowFixture(BaseModel):
    fixture_id: str
    title: str
    description: str
    evidence: list[EvidenceInput] = Field(default_factory=list)
    live_context: dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplate(BaseModel):
    """A versioned template intentionally owned by application code."""

    template_id: str
    version: int = 1
    title: str
    description: str
    source_types: list[str]
    required_source_types: list[str]
    required_evidence_fields: list[str]
    evidence_max_age_hours: int
    live_context_schema: list[LiveContextField]
    sag_rule: dict[str, Any]
    memory_type: WorkflowMemoryType
    prior_memory_summary: str
    recommended_action: str
    owner_role: str
    human_approval_required: bool = True
    demo_fixture: WorkflowFixture
    evaluation_cases: list[WorkflowEvaluationCase] = Field(default_factory=list)


class DecisionFact(BaseModel):
    statement: str
    source_evidence_ids: list[str] = Field(default_factory=list)


class DecisionInference(BaseModel):
    text: str
    generated_by: str
    is_model_generated: bool = False


class MissingEvidence(BaseModel):
    field: str
    reason: str
    source_evidence_id: str | None = None


class MemoryReference(BaseModel):
    memory_id: str
    memory_type: WorkflowMemoryType
    summary: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    skill_id: str | None = None
    is_ephemeral: bool = False


class DecisionBrief(BaseModel):
    """Shared response shape used by every workflow card/detail page."""

    facts: list[DecisionFact] = Field(default_factory=list)
    inference: DecisionInference
    missing_evidence: list[MissingEvidence] = Field(default_factory=list)
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    memory_refs: list[MemoryReference] = Field(default_factory=list)
    sag_trace: dict[str, Any] = Field(default_factory=dict)
    verdict: WorkflowVerdict
    status: WorkflowRunStatus
    owner: str
    recommended_next_action: str
    human_approval_required: bool = True


class WorkflowOutcomeRequest(BaseModel):
    approved: bool
    outcome: str = Field(min_length=1, max_length=160)
    note: str = Field(default="", max_length=2_000)
    actor: str | None = Field(default=None, max_length=120)


class WorkflowOutcome(BaseModel):
    approved: bool
    outcome: str
    actor: str | None = None
    recorded_at: datetime = Field(default_factory=workflow_now)
    reinforcement_eligible: bool = False
    reinforcement_applied: bool = False
    note: str | None = None


class WorkflowRunRequest(BaseModel):
    """A fixture-only call is enough for the judge route.

    Setting ``fixture`` to false enables the same contract for a genuine
    integration or a sandbox scenario.  Missing fields are deliberately
    accepted and returned as ``review_required`` instead of being invented.
    """

    template_id: str
    fixture: bool = False
    evidence: list[EvidenceInput] = Field(default_factory=list)
    live_context: dict[str, Any] = Field(default_factory=dict)
    # Server integrations may already have compiled and persisted a Company
    # Brain skill from this exact source event.  Referencing it avoids a second
    # model call and preserves the single human-outcome reinforcement path.
    compiled_skill_id: str | None = None


class WorkflowRun(BaseModel):
    run_id: str
    template_id: str
    template_version: int
    scenario_version: str
    org_id: str
    is_demo_fixture: bool = False
    live_context: dict[str, Any] = Field(default_factory=dict)
    decision_brief: DecisionBrief
    outcomes: list[WorkflowOutcome] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=workflow_now)
    updated_at: datetime = Field(default_factory=workflow_now)
