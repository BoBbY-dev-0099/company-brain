"""The three code-owned, judge-ready workflow templates.

These are intentionally not user-configurable.  A compact set of templates
makes the product immediately legible while retaining one shared operational
memory contract.
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


DEMO_SCENARIO_VERSION = "judge-demo-v1"


def _fixture_time(minutes_ago: int) -> Any:
    """Fresh relative timestamps keep the deterministic fixture replayable."""
    return workflow_now() - timedelta(minutes=minutes_ago)


def _shared_cases() -> list[WorkflowEvaluationCase]:
    return [
        WorkflowEvaluationCase(
            case_id="valid_evidence",
            description="Required evidence and every live condition support a safe, human-approved path.",
            expected_verdict=WorkflowVerdict.PROCEED_WITH_HUMAN_APPROVAL,
        ),
        WorkflowEvaluationCase(
            case_id="changed_condition",
            description="Fresh evidence changes a prior assumption and suspends the old action.",
            expected_verdict=WorkflowVerdict.SUSPENDED,
        ),
        WorkflowEvaluationCase(
            case_id="missing_evidence",
            description="Absent, stale, or unavailable evidence requests review instead of a fabricated answer.",
            expected_verdict=WorkflowVerdict.REVIEW_REQUIRED,
        ),
    ]


def build_templates() -> tuple[WorkflowTemplate, ...]:
    """Return a fresh immutable-by-convention catalog for API callers.

    Fresh fixture timestamps are deliberate: the values and IDs are stable,
    while a demo should not become falsely stale simply because it is replayed
    after a week.
    """
    release = WorkflowTemplate(
        template_id="release-safety",
        version=1,
        title="Release Safety",
        description=(
            "Suspend a deployment/runbook when a PR or runtime change makes a "
            "previously safe operating assumption false."
        ),
        source_types=["github_pull_request", "runtime_metric", "deployment_runbook"],
        required_source_types=["github_pull_request", "runtime_metric"],
        required_evidence_fields=["source_type", "external_id", "occurred_at", "excerpt"],
        evidence_max_age_hours=168,
        live_context_schema=[
            LiveContextField(
                name="worker_memory_mb",
                value_type="number",
                description="Current worker memory limit available to the release.",
            ),
            LiveContextField(
                name="runbook_validated",
                value_type="boolean",
                description="Whether the runbook has been validated against the current runtime.",
            ),
            LiveContextField(
                name="deployment_window_open",
                value_type="boolean",
                description="Whether the approved deployment window is currently open.",
            ),
        ],
        sag_rule={
            "and": [
                {"gte": ["worker_memory_mb", 25]},
                {"eq": ["runbook_validated", True]},
                {"eq": ["deployment_window_open", True]},
            ]
        },
        memory_type=WorkflowMemoryType.POLICY,
        prior_memory_summary=(
            "The bulk-export runbook is safe only when workers have at least "
            "25 MiB available and the runbook matches the active runtime."
        ),
        recommended_action=(
            "Suspend the release, restore or revalidate worker memory, and require "
            "an engineering owner to approve a revised runbook."
        ),
        owner_role="Engineering release owner",
        demo_fixture=WorkflowFixture(
            fixture_id="judge-demo-v1-release-memory-drop",
            title="PR lowers worker memory below the runbook requirement",
            description=(
                "A merged PR changes the worker limit from 25 MiB to 8 MiB; the "
                "old runbook must not be followed unchanged."
            ),
            evidence=[
                EvidenceInput(
                    source_type="github_pull_request",
                    source_name="GitHub",
                    external_id="acme/company-brain#842",
                    url="https://github.com/acme/company-brain/pull/842",
                    occurred_at=_fixture_time(7),
                    excerpt="Merged PR #842 changes EXPORT_WORKER_MEMORY_MB from 25 to 8.",
                    metadata={
                        "changed_field": "worker_memory_mb",
                        "previous_value": 25,
                        "current_value": 8,
                    },
                ),
                EvidenceInput(
                    source_type="runtime_metric",
                    source_name="Runtime telemetry",
                    external_id="memory-limit-worker-export",
                    occurred_at=_fixture_time(4),
                    excerpt="export-worker effective memory limit is 8 MiB after the deploy.",
                    metadata={"worker_memory_mb": 8},
                ),
            ],
            live_context={
                "worker_memory_mb": 8,
                "runbook_validated": False,
                "deployment_window_open": True,
            },
        ),
        evaluation_cases=_shared_cases(),
    )

    money = WorkflowTemplate(
        template_id="money-safety",
        version=1,
        title="Money Safety",
        description=(
            "Prevent an automatic refund when current customer or policy evidence "
            "requires accountable human review."
        ),
        source_types=["support_ticket", "billing_policy", "customer_contract"],
        required_source_types=["support_ticket", "billing_policy"],
        required_evidence_fields=["source_type", "external_id", "occurred_at", "excerpt"],
        evidence_max_age_hours=720,
        live_context_schema=[
            LiveContextField(
                name="days_since_first_charge",
                value_type="number",
                description="Days since the customer's first charge.",
            ),
            LiveContextField(
                name="is_enterprise_contract",
                value_type="boolean",
                description="Whether contractual terms override the standard refund flow.",
            ),
            LiveContextField(
                name="policy_exception_open",
                value_type="boolean",
                description="Whether an unresolved policy exception exists.",
            ),
        ],
        sag_rule={
            "and": [
                {"lte": ["days_since_first_charge", 14]},
                {"eq": ["is_enterprise_contract", False]},
                {"eq": ["policy_exception_open", False]},
            ]
        },
        memory_type=WorkflowMemoryType.POLICY,
        prior_memory_summary=(
            "The standard automatic-refund path is limited to non-enterprise "
            "customers in the first 14 days with no open policy exception."
        ),
        recommended_action=(
            "Pause the automatic refund and route the case with the cited policy "
            "and contract evidence to the support operations owner."
        ),
        owner_role="Support operations owner",
        demo_fixture=WorkflowFixture(
            fixture_id="judge-demo-v1-money-policy-exception",
            title="An enterprise contract blocks an automatic refund",
            description=(
                "A refund request looks routine until contract and policy evidence "
                "show an enterprise exception and an expired standard window."
            ),
            evidence=[
                EvidenceInput(
                    source_type="support_ticket",
                    source_name="Support",
                    external_id="SUP-4412",
                    url="https://support.example.test/tickets/SUP-4412",
                    occurred_at=_fixture_time(11),
                    excerpt="Customer requests an automatic refund for the annual workspace plan.",
                    metadata={"customer_id": "cus_demo_128"},
                ),
                EvidenceInput(
                    source_type="billing_policy",
                    source_name="Billing policy",
                    external_id="POL-REFUND-2026-03",
                    occurred_at=_fixture_time(20),
                    excerpt="Enterprise contracts and requests outside 14 days require finance review.",
                    metadata={"policy_version": "2026-03"},
                ),
                EvidenceInput(
                    source_type="customer_contract",
                    source_name="CRM contract record",
                    external_id="CTR-9981",
                    occurred_at=_fixture_time(13),
                    excerpt="Account is an enterprise annual contract with a negotiated refund exception.",
                ),
            ],
            live_context={
                "days_since_first_charge": 41,
                "is_enterprise_contract": True,
                "policy_exception_open": True,
            },
        ),
        evaluation_cases=_shared_cases(),
    )

    rollout = WorkflowTemplate(
        template_id="rollout-safety",
        version=1,
        title="Rollout Safety",
        description=(
            "Hold a feature-flag expansion when current reliability evidence no "
            "longer supports the planned rollout."
        ),
        source_types=["observability_metric", "incident", "feature_flag"],
        required_source_types=["observability_metric", "incident"],
        required_evidence_fields=["source_type", "external_id", "occurred_at", "excerpt"],
        evidence_max_age_hours=24,
        live_context_schema=[
            LiveContextField(
                name="error_rate_percent",
                value_type="number",
                description="Current error rate for the rollout cohort.",
            ),
            LiveContextField(
                name="sample_size",
                value_type="number",
                description="Number of observed cohort requests/events.",
            ),
            LiveContextField(
                name="incident_open",
                value_type="boolean",
                description="Whether an unresolved related incident is open.",
            ),
        ],
        sag_rule={
            "and": [
                {"lte": ["error_rate_percent", 1.0]},
                {"gte": ["sample_size", 1000]},
                {"eq": ["incident_open", False]},
            ]
        },
        memory_type=WorkflowMemoryType.DECISION,
        prior_memory_summary=(
            "Expand a feature flag only after the cohort has at least 1,000 "
            "observations, error rate at or below 1%, and no open related incident."
        ),
        recommended_action=(
            "Hold the expansion at its current cohort, investigate the reliability "
            "signal, and require the product rollout owner to approve any restart."
        ),
        owner_role="Product rollout owner",
        demo_fixture=WorkflowFixture(
            fixture_id="judge-demo-v1-rollout-error-spike",
            title="Live error evidence suspends a feature-flag expansion",
            description=(
                "A planned 50% expansion is blocked because the 10% cohort has a "
                "3.8% error rate and an unresolved incident."
            ),
            evidence=[
                EvidenceInput(
                    source_type="observability_metric",
                    source_name="Observability",
                    external_id="metric-dashboard-widgets-error-rate",
                    occurred_at=_fixture_time(3),
                    excerpt="New dashboard widgets cohort error rate is 3.8% across 2,540 requests.",
                    metadata={"error_rate_percent": 3.8, "sample_size": 2540},
                ),
                EvidenceInput(
                    source_type="incident",
                    source_name="Incident management",
                    external_id="INC-237",
                    occurred_at=_fixture_time(2),
                    excerpt="INC-237 remains open: widget rendering failures correlate with the rollout cohort.",
                    metadata={"incident_open": True},
                ),
                EvidenceInput(
                    source_type="feature_flag",
                    source_name="Feature flag service",
                    external_id="flag-new-dashboard-widgets",
                    occurred_at=_fixture_time(5),
                    excerpt="new_dashboard_widgets is currently at 10%; a 50% expansion is scheduled.",
                ),
            ],
            live_context={
                "error_rate_percent": 3.8,
                "sample_size": 2540,
                "incident_open": True,
            },
        ),
        evaluation_cases=_shared_cases(),
    )

    return (release, money, rollout)


def get_template(template_id: str) -> WorkflowTemplate | None:
    """Find a template by stable identifier without exposing mutable globals."""
    return next((item for item in build_templates() if item.template_id == template_id), None)
