"""The single, real-source NexaFlow release safety template.

NexaFlow intentionally ships one aggregate decision instead of a gallery of
unrelated demos.  The template is code-owned; source adapters deliver the
evidence and the server derives the live values before evaluating SAG.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from backend.workflows.models import (
    EvidenceInput,
    LiveContextField,
    WorkflowEvaluationCase,
    WorkflowFixture,
    WorkflowMemoryType,
    WorkflowTemplate,
    WorkflowVerdict,
    workflow_now,
)


DEMO_SCENARIO_VERSION = "nexaflow-live-v1"


def _fixture_time(minutes_ago: int) -> Any:
    """Keep the API fixture fresh for narrow unit tests; the UI never replays it."""
    return workflow_now() - timedelta(minutes=minutes_ago)


def build_templates() -> tuple[WorkflowTemplate, ...]:
    """Return the one server-owned NexaFlow operating decision."""
    return (
        WorkflowTemplate(
            template_id="nexaflow-release-safety",
            version=1,
            title="NexaFlow release safety",
            description=(
                "Use the latest real Slack incident, Alibaba OSS runbook, and merged GitHub "
                "change to decide whether a fulfillment release remains safe."
            ),
            source_types=["slack_message", "alibaba_oss_object", "google_drive_document", "github_pull_request"],
            required_source_types=["slack_message", "alibaba_oss_object", "github_pull_request"],
            required_evidence_fields=["source_type", "external_id", "occurred_at", "excerpt"],
            evidence_max_age_hours=168,
            live_context_schema=[
                LiveContextField(
                    name="configured_memory_meets_runbook",
                    value_type="boolean",
                    description="The merged configuration still meets the approved runbook minimum.",
                ),
                LiveContextField(
                    name="linked_incident_open",
                    value_type="boolean",
                    description="A related Slack incident remains open.",
                ),
            ],
            sag_rule={
                "and": [
                    {"eq": ["configured_memory_meets_runbook", True]},
                    {"eq": ["linked_incident_open", False]},
                ]
            },
            memory_type=WorkflowMemoryType.POLICY,
            prior_memory_summary=(
                "NexaFlow fulfillment workers may be promoted only when the merged "
                "memory configuration meets the current Alibaba OSS runbook and no linked "
                "operations incident is open."
            ),
            recommended_action=(
                "Suspend the release, restore or re-approve the worker memory setting, "
                "and have the engineering release owner resolve the cited incident."
            ),
            owner_role="NexaFlow engineering release owner",
            # This is deliberately test-only.  The root console has no fixture/replay
            # control and only calls the aggregate real-source endpoint.
            demo_fixture=WorkflowFixture(
                fixture_id="nexaflow-test-only-release-safety",
                title="Test-only real-source shape",
                description="A unit-test fixture; it is not shown in the NexaFlow console.",
                evidence=[
                    EvidenceInput(
                        source_type="alibaba_oss_object",
                        source_name="Alibaba Cloud OSS runbook",
                        external_id="test-runbook",
                        occurred_at=_fixture_time(3),
                        excerpt="Fulfillment workers require at least 24 MiB.",
                    ),
                    EvidenceInput(
                        source_type="slack_message",
                        source_name="Slack #ops-incidents",
                        external_id="test-incident",
                        occurred_at=_fixture_time(2),
                        excerpt="SEV-2 remains open.",
                    ),
                    EvidenceInput(
                        source_type="github_pull_request",
                        source_name="GitHub",
                        external_id="test-pr",
                        occurred_at=_fixture_time(1),
                        excerpt="Merged configuration sets NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=8.",
                    ),
                ],
                live_context={"configured_memory_meets_runbook": False, "linked_incident_open": True},
            ),
            evaluation_cases=[
                WorkflowEvaluationCase(
                    case_id="suspended",
                    description="A merged memory reduction or open incident suspends release.",
                    expected_verdict=WorkflowVerdict.SUSPENDED,
                ),
                WorkflowEvaluationCase(
                    case_id="missing_or_stale",
                    description="Missing or stale required source evidence requires review.",
                    expected_verdict=WorkflowVerdict.REVIEW_REQUIRED,
                ),
                WorkflowEvaluationCase(
                    case_id="safe_with_human_approval",
                    description="Fresh evidence with an approved configuration can proceed only with human approval.",
                    expected_verdict=WorkflowVerdict.PROCEED_WITH_HUMAN_APPROVAL,
                ),
            ],
        ),
    )


def get_template(template_id: str) -> WorkflowTemplate | None:
    return next((item for item in build_templates() if item.template_id == template_id), None)
