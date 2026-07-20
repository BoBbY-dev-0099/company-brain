"""NexaFlow's aggregate, real-source release decision surface."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from backend.config import settings
from backend.sources.models import IngestionStage, SourceIngestion, SourceProvider
from backend.sources.service import configured_connections, source_service
from backend.workflows.models import EvidenceInput, WorkflowRunRequest
from backend.workflows.service import WorkflowService


router = APIRouter(prefix="/nexaflow", tags=["nexaflow"])
TEMPLATE_ID = "nexaflow-release-safety"
MEMORY_VARIABLE = "NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB"


def _org(request: Request) -> str:
    """The public console is deliberately fixed to the read-only NexaFlow org."""
    return settings.SOURCE_ORG_ID


def _fresh_ready(records: list[SourceIngestion], provider: SourceProvider) -> SourceIngestion | None:
    return next(
        (
            item
            for item in records
            if item.provider == provider
            and item.stage == IngestionStage.DECISION_READY
            and item.availability == "available"
            and item.freshness == "fresh"
        ),
        None,
    )


def _fresh_runbook(records: list[SourceIngestion]) -> SourceIngestion | None:
    """Select one current runbook, refusing an ambiguous same-time update."""
    candidates = [
        item
        for item in records
        if item.provider == SourceProvider.ALIBABA_OSS
        and item.stage == IngestionStage.DECISION_READY
        and item.availability == "available"
        and item.freshness == "fresh"
    ]
    # Accept pre-OSS records during migration only when no current OSS record
    # exists. New NexaFlow decisions must prefer the Alibaba source.
    if not candidates:
        candidates = [
            item
            for item in records
            if item.provider == SourceProvider.GOOGLE_DRIVE
            and item.stage == IngestionStage.DECISION_READY
            and item.availability == "available"
            and item.freshness == "fresh"
        ]
    if not candidates:
        return None
    newest_occurred_at = max(item.occurred_at for item in candidates)
    newest = [item for item in candidates if item.occurred_at == newest_occurred_at]
    fingerprints = {item.raw_payload_sha256 or item.excerpt.strip() for item in newest}
    if len(newest) > 1 and len(fingerprints) > 1:
        # Equal-time conflicting policies cannot be resolved by list order.
        return None
    return max(newest, key=lambda item: (item.retrieved_at, item.received_at, item.ingestion_id))


def _runbook_conflict(records: list[SourceIngestion]) -> bool:
    """Return True when equally-timed fresh runbooks disagree."""
    candidates = [
        item
        for item in records
        if item.provider in {SourceProvider.ALIBABA_OSS, SourceProvider.GOOGLE_DRIVE}
        and item.stage == IngestionStage.DECISION_READY
        and item.availability == "available"
        and item.freshness == "fresh"
    ]
    if not candidates:
        return False
    preferred_provider = (
        SourceProvider.ALIBABA_OSS
        if any(item.provider == SourceProvider.ALIBABA_OSS for item in candidates)
        else SourceProvider.GOOGLE_DRIVE
    )
    candidates = [item for item in candidates if item.provider == preferred_provider]
    newest_occurred_at = max(item.occurred_at for item in candidates)
    newest = [item for item in candidates if item.occurred_at == newest_occurred_at]
    return len(newest) > 1 and len({item.raw_payload_sha256 or item.excerpt.strip() for item in newest}) > 1


def _runbook_minimum(excerpt: str) -> int | None:
    patterns = (
        r"(?:at\s+least|minimum(?:\s+of)?|no\s+less\s+than|require(?:s|d)?)\s*(\d+)\s*(?:mi?b|mb)\b",
        r"(\d+)\s*(?:mi?b|mb)\s*(?:minimum|required)",
    )
    for pattern in patterns:
        match = re.search(pattern, excerpt, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _github_memory_value(excerpt: str) -> int | None:
    # Prefer the added diff line: it is the final merged configuration.
    name = re.escape(MEMORY_VARIABLE)
    patterns = (
        rf"^\+\s*(?:export\s+)?{name}\s*=\s*(\d+)\b",
        rf"{name}\s*(?:from\s+\d+\s+to|=|to)\s*(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, excerpt, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return int(match.group(1))
    return None


def _incident_state(excerpt: str) -> bool | None:
    """Return open=True, closed=False, or None when a message is not an incident."""
    value = excerpt.lower()
    if not re.search(r"\b(sev[- ]?[0-9]|incident|oom|out.of.memory|pause\s+promotion)\b", value):
        return None
    # A message can mention a future resolution condition while the incident
    # is still active (for example, "pause promotion until the incident is
    # resolved"). Treat those hold/pending forms as open rather than letting
    # the word "resolved" alone imply that the incident has cleared.
    if re.search(
        r"\b(?:until|while|pending|awaiting|not|unresolved|still|remains)\b"
        r".{0,100}\b(?:resolved|closed|mitigated|cleared)\b",
        value,
    ) or re.search(r"\b(?:pause|hold|block|stop)\b.{0,80}\b(?:promotion|release)\b", value):
        return True
    if re.search(r"\b(resolved|closed|mitigated|cleared)\b", value):
        return False
    return True


def _evidence(item: SourceIngestion) -> EvidenceInput:
    return EvidenceInput(
        source_type=(
            "alibaba_oss_object"
            if item.provider in {SourceProvider.ALIBABA_OSS, SourceProvider.GOOGLE_DRIVE}
            else item.source_type
        ),
        source_name=item.source_name or "Alibaba Cloud OSS runbook",
        external_id=item.external_id,
        url=item.source_url,
        occurred_at=item.occurred_at,
        excerpt=item.excerpt,
        metadata={
            "source_ingestion_id": item.ingestion_id,
            "provider": item.provider.value,
            "raw_payload_sha256": item.raw_payload_sha256,
            "qwen_status": item.qwen_status,
            "memory_id": item.memory_id,
        },
    )


def _matrix_case_evidence(
    case_id: str,
    *,
    memory_mb: int | None,
    incident_open: bool | None,
    runbook_minimum_mb: int | None = 24,
    age_hours: int = 0,
) -> tuple[list[EvidenceInput], dict[str, Any]]:
    """Build private, ephemeral evidence for the judge-facing Qwen matrix.

    These records deliberately use the same normalized workflow contract as a
    real source event. They are never persisted, never become canonical
    memory, and exist only to demonstrate that Qwen compiles more than the
    single live production path.
    """
    occurred_at = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    evidence: list[EvidenceInput] = []
    if incident_open is not None:
        incident_text = (
            "SEV-2: fulfillment workers are OOM. Pause promotion until the incident is resolved."
            if incident_open
            else "SEV-2 fulfillment incident resolved and mitigated; promotion may be considered after validation."
        )
        evidence.append(
            EvidenceInput(
                source_type="slack_message",
                source_name="Slack #ops-incidents",
                external_id=f"matrix-{case_id}-incident",
                occurred_at=occurred_at,
                excerpt=incident_text,
            )
        )
    if runbook_minimum_mb is not None:
        evidence.append(
            EvidenceInput(
                source_type="alibaba_oss_object",
                source_name="Alibaba Cloud OSS runbook",
                external_id=f"matrix-{case_id}-runbook",
                occurred_at=occurred_at,
                excerpt=(
                    f"Fulfillment workers require at least {runbook_minimum_mb} MiB of memory before promotion."
                ),
            )
        )
    if memory_mb is not None:
        evidence.append(
            EvidenceInput(
                source_type="github_pull_request",
                source_name="GitHub merged pull request",
                external_id=f"matrix-{case_id}-pr",
                occurred_at=occurred_at,
                excerpt=f"Merged NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB={memory_mb}.",
            )
        )
    live_context: dict[str, Any] = {}
    if runbook_minimum_mb is not None and memory_mb is not None:
        live_context["configured_memory_meets_runbook"] = memory_mb >= runbook_minimum_mb
    if incident_open is not None:
        live_context["linked_incident_open"] = incident_open
    return evidence, live_context


def _pending_reason(records: list[SourceIngestion], provider: SourceProvider, label: str) -> str:
    if provider == SourceProvider.ALIBABA_OSS and _runbook_conflict(records):
        return f"Conflicting {label} records share the newest source timestamp; human review is required."
    candidate = next((item for item in records if item.provider == provider), None)
    if candidate is None:
        return f"No {label} evidence has been ingested yet."
    if candidate.stage != IngestionStage.DECISION_READY:
        return f"Latest {label} evidence is still processing ({candidate.stage.value})."
    if candidate.freshness != "fresh":
        return f"Latest {label} evidence is stale; refresh it before release."
    return f"Latest {label} evidence is unavailable."


async def _records(org_id: str, limit: int = 80) -> list[SourceIngestion]:
    return await source_service.repository.list_ingestions(org_id, limit=limit)


async def _overview(org_id: str) -> dict[str, Any]:
    records = await _records(org_id)
    memories = await source_service.repository.list_memories(org_id, include_superseded=True, limit=30)
    try:
        latest_runs = await WorkflowService().list_runs(org_id=org_id, limit=1)
    except RuntimeError:
        latest_runs = []
    connected = []
    try:
        stored = await source_service.repository.stored_connections(org_id)
    except RuntimeError:
        stored = {}
    for connection in configured_connections(org_id=org_id):
        prior = stored.get(connection.provider.value)
        if prior:
            connection.last_success_at = prior.last_success_at
            connection.last_error = prior.last_error
            connection.health = prior.health
        connected.append(connection.model_dump(mode="json"))

    slack = _fresh_ready(records, SourceProvider.SLACK)
    runbook = _fresh_runbook(records)
    github = _fresh_ready(records, SourceProvider.GITHUB)
    ready = bool(slack and runbook and github)
    missing = [
        _pending_reason(records, provider, label)
        for provider, label, item in (
            (SourceProvider.SLACK, "Slack incident", slack),
            (SourceProvider.ALIBABA_OSS, "Alibaba OSS runbook", runbook),
            (SourceProvider.GITHUB, "GitHub merged PR", github),
        )
        if not item
    ]
    return {
        "company": "NexaFlow Logistics",
        "org_id": org_id,
        "mode": "real_source_local",
        "connections": connected,
        "evidence": [item.model_dump(mode="json") for item in records[:20]],
        "memories": [item.model_dump(mode="json") for item in memories],
        "release_check_ready": ready,
        "readiness_reasons": missing,
        "latest_release_check": latest_runs[0].model_dump(mode="json") if latest_runs else None,
        "server_time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/overview")
async def nexaflow_overview(request: Request) -> dict[str, Any]:
    return await _overview(_org(request))


@router.post("/release-check")
async def release_check(request: Request) -> dict[str, Any]:
    """Evaluate only evidence already persisted by signed/read-only connectors."""
    org_id = _org(request)
    records = await _records(org_id)
    slack = _fresh_ready(records, SourceProvider.SLACK)
    runbook = _fresh_runbook(records)
    github = _fresh_ready(records, SourceProvider.GITHUB)
    selected = [item for item in (slack, runbook, github) if item]
    live_context: dict[str, Any] = {}
    parsing: dict[str, Any] = {}

    runbook_minimum = _runbook_minimum(runbook.excerpt) if runbook else None
    configured_memory = _github_memory_value(github.excerpt) if github else None
    incident_open = _incident_state(slack.excerpt) if slack else None
    parsing.update(
        {
            "runbook_minimum_memory_mb": runbook_minimum,
            "merged_worker_memory_mb": configured_memory,
            "linked_incident_open": incident_open,
            "memory_variable": MEMORY_VARIABLE,
        }
    )
    if runbook_minimum is not None and configured_memory is not None:
        live_context["configured_memory_meets_runbook"] = configured_memory >= runbook_minimum
    if incident_open is not None:
        live_context["linked_incident_open"] = incident_open
    live_context.update(
        {
            "runbook_minimum_memory_mb": runbook_minimum,
            "merged_worker_memory_mb": configured_memory,
            "incident_summary": slack.excerpt[:300] if slack else None,
        }
    )

    try:
        run = await WorkflowService(enable_qwen_compilation=False).run_workflow(
            WorkflowRunRequest(
                template_id=TEMPLATE_ID,
                fixture=False,
                evidence=[_evidence(item) for item in selected],
                live_context=live_context,
            ),
            org_id=org_id,
            execution_origin="nexaflow_console",
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=f"Release check unavailable: {exc}") from exc

    return {
        "run": run.model_dump(mode="json"),
        "source_selection": {
            provider.value: item.ingestion_id if item else None
            for provider, item in (
                (SourceProvider.SLACK, slack),
                (SourceProvider.ALIBABA_OSS, runbook),
                (SourceProvider.GITHUB, github),
            )
        },
        "parsing": parsing,
        "boundary": "Read-only source evidence and a human-required recommendation. No deployment, Slack post, GitHub change, or OSS write was executed.",
    }


@router.post("/case-matrix")
async def case_matrix(request: Request) -> dict[str, Any]:
    """Run several private cases through the same Qwen + SAG workflow engine.

    This is a judge-facing proof surface, not a second demo product. Each run
    is ephemeral and sandbox-marked, so it cannot change canonical counts,
    durable skills, confidence, or external systems.
    """
    cases = (
        {
            "case_id": "memory_regression_and_open_incident",
            "title": "Memory regression + open incident",
            "description": "The merged worker setting is below policy while the incident is still active.",
            "memory_mb": 8,
            "incident_open": True,
            "runbook_minimum_mb": 24,
            "age_hours": 0,
        },
        {
            "case_id": "safe_configuration_resolved_incident",
            "title": "Safe configuration + resolved incident",
            "description": "Current evidence satisfies both safety predicates, but approval is still required.",
            "memory_mb": 32,
            "incident_open": False,
            "runbook_minimum_mb": 24,
            "age_hours": 0,
        },
        {
            "case_id": "open_incident_safe_memory",
            "title": "Open incident blocks a safe configuration",
            "description": "The memory value is safe, but an active incident independently blocks promotion.",
            "memory_mb": 32,
            "incident_open": True,
            "runbook_minimum_mb": 24,
            "age_hours": 0,
        },
        {
            "case_id": "missing_runbook",
            "title": "Missing runbook evidence",
            "description": "Without the current policy, the system refuses to invent a safe threshold.",
            "memory_mb": 32,
            "incident_open": False,
            "runbook_minimum_mb": None,
            "age_hours": 0,
        },
        {
            "case_id": "stale_runbook",
            "title": "Stale runbook evidence",
            "description": "An old policy is visible but outside the freshness window, so review is required.",
            "memory_mb": 8,
            "incident_open": True,
            "runbook_minimum_mb": 24,
            "age_hours": 200,
        },
    )
    service = WorkflowService()
    qwen_slots = asyncio.Semaphore(2)

    async def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
        # DashScope can rate-limit a burst of independent completions. Two
        # slots keep the judge path responsive without reducing Qwen coverage.
        async with qwen_slots:
            evidence, live_context = _matrix_case_evidence(
                case["case_id"],
                memory_mb=case["memory_mb"],
                incident_open=case["incident_open"],
                runbook_minimum_mb=case["runbook_minimum_mb"],
                age_hours=case["age_hours"],
            )
            run = await service.run_workflow(
                WorkflowRunRequest(
                    template_id=TEMPLATE_ID,
                    fixture=False,
                    evidence=evidence,
                    live_context=live_context,
                ),
                # The case matrix is intentionally private and non-persistent.
                # It uses a fixed server-owned namespace only for provenance.
                org_id="nexaflow-case-matrix",
                persist=False,
                compile_memory=True,
                is_judge_sandbox=True,
                execution_origin="nexaflow_case_matrix",
            )
        compiled = [
            ref
            for ref in run.decision_brief.memory_refs
            if ref.provenance.get("kind") == "compiled_event"
        ]
        qwen_compiled = bool(
            compiled and any(ref.provenance.get("compiler") == "qwen" for ref in compiled)
        )
        return {
            "case_id": case["case_id"],
            "title": case["title"],
            "description": case["description"],
            "verdict": run.decision_brief.verdict.value,
            "recommendation": run.decision_brief.recommended_next_action,
            "qwen": {
                "status": "compiled" if qwen_compiled else "unavailable",
                "model": settings.QWEN_COMPILER_MODEL if qwen_compiled else None,
                "summary": compiled[-1].summary if compiled else run.decision_brief.inference.text,
                "source_count": len(run.decision_brief.evidence),
                "memory_id": compiled[-1].memory_id if compiled else None,
            },
            "sag": run.decision_brief.sag_trace,
            "human_approval_required": run.decision_brief.human_approval_required,
            "ephemeral": True,
        }

    # The cases are independent. Parallel compilation keeps the judge route
    # responsive while still exercising Qwen once per reality.
    results = await asyncio.gather(*(evaluate_case(case) for case in cases))
    return {
        "scenario_version": settings.DEMO_SCENARIO_VERSION,
        "qwen_configured": bool(settings.QWEN_API_KEY),
        "cases": results,
        "boundary": "Private Qwen compilation only. No canonical memory, confidence, or external action was changed.",
    }
