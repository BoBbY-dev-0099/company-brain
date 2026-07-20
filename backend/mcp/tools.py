"""MCP tool implementations.

These are the actual Python functions that back the MCP tools. The MCP server
(server.py) registers scoped wrappers over authenticated Streamable HTTP.
In-process backend integrations import these functions directly to avoid transport loopback.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from backend.brain import store
from backend.core import compiler, interceptor, propagator
from backend.core.schema import (
    DecisionCheckRequest,
    DecisionCheckResponse,
    InterceptResult,
    RawEvent,
)
from backend.sources.models import RealityMemory
from backend.sources.store import get_source_repository

logger = logging.getLogger(__name__)


async def recall_skills(context: str, top_k: int = 5, org_id: str = "default") -> dict[str, Any]:
    """Recall the most relevant active skills for a free-text context."""
    skills = await interceptor.recall_skills_for_context(context, top_k=top_k, org_id=org_id)
    return {
        "skills": [
            {
                "skill_id": s.skill_id,
                "name": s.name,
                "version": s.version,
                "domain": s.domain,
                "summary": s.summary,
                "confidence": s.provenance.confidence,
                "intercept_message": s.executable.intercept_message,
                "recommended_action": s.executable.recommended_action,
                "avoid_actions": s.executable.avoid_actions,
                "auto_execute": s.executable.auto_execute,
                "anti_conditions": s.knowledge.anti_conditions,
            }
            for s in skills
        ]
    }


async def check_intercept(
    agent_id: str,
    decision_text: str,
    domain: str | None = None,
    metadata: dict[str, Any] | None = None,
    org_id: str = "default",
) -> dict[str, Any]:
    """Pre-flight check: would this decision be intercepted by the brain?

    Pass ``metadata`` with live system state (e.g. config values) so the
    Semantic Applicability Gate can evaluate skill preconditions.
    """
    req = DecisionCheckRequest(
        agent_id=agent_id,
        decision_text=decision_text,
        domain=domain,
        metadata=metadata or {},
        org_id=org_id,
    )
    resp: DecisionCheckResponse = await interceptor.check_decision(req)

    if resp.matched_skill is not None and resp.result != InterceptResult.CLEAR:
        await propagator.broadcast_intercept(
            agent_id=agent_id,
            skill=resp.matched_skill,
            result=resp.result,
            confidence=resp.confidence,
            org_id=org_id,
        )

    return {
        "result": resp.result.value,
        "confidence": resp.confidence,
        "matched_skill_id": resp.matched_skill.skill_id if resp.matched_skill else None,
        "matched_skill_name": resp.matched_skill.name if resp.matched_skill else None,
        "intercept_message": resp.intercept_message,
        "recommended_action": resp.recommended_action,
        "auto_execute": resp.auto_execute,
        "rationale": resp.rationale,
        "applicability_status": resp.applicability_status,
        "suspension_reason": resp.suspension_reason,
        "suspension_evidence": resp.suspension_evidence,
    }


async def compile_experience(
    event_id: str,
    agent_id: str,
    event_type: str,
    content: str,
    outcome: str = "",
    metadata: dict[str, Any] | None = None,
    org_id: str = "default",
) -> dict[str, Any]:
    """Compile a raw event into a skill, persist, and propagate."""
    event = RawEvent(
        event_id=event_id,
        agent_id=agent_id,
        event_type=event_type,
        content=content,
        outcome=outcome,
        metadata=metadata or {},
        org_id=org_id,
    )
    skill = await compiler.compile_event_to_skill(event)
    saved = await store.save_skill(skill, org_id=org_id)
    await store.save_event(event, skill_compiled=saved.skill_id, org_id=org_id)
    await propagator.propagate_skill(saved, is_new=(saved.version == 1), org_id=org_id)
    return {
        "skill_id": saved.skill_id,
        "name": saved.name,
        "version": saved.version,
        "domain": saved.domain,
        "summary": saved.summary,
        "confidence": saved.provenance.confidence,
    }


async def inspect_memory(
    query: str = "",
    include_superseded: bool = False,
    top_k: int = 10,
    org_id: str = "default",
) -> dict[str, Any]:
    """Inspect source-linked Reality Memory without exposing another org."""
    memories = await get_source_repository().list_memories(
        org_id,
        query=query or None,
        include_superseded=include_superseded,
        limit=top_k,
    )
    return {"memories": [memory.model_dump(mode="json") for memory in memories]}


async def query_evidence(
    top_k: int = 10,
    org_id: str = "default",
) -> dict[str, Any]:
    """Return immutable source-event summaries for an organization."""
    events = await get_source_repository().list_ingestions(org_id, limit=top_k)
    return {
        "evidence": [
            {
                "ingestion_id": event.ingestion_id,
                "provider": event.provider.value,
                "external_id": event.external_id,
                "source_type": event.source_type,
                "source_name": event.source_name,
                "source_url": event.source_url,
                "occurred_at": event.occurred_at.isoformat(),
                "retrieved_at": event.retrieved_at.isoformat(),
                "excerpt": event.excerpt,
                "raw_payload_sha256": event.raw_payload_sha256,
                "freshness": event.freshness,
                "availability": event.availability,
                "acl_scope": event.acl_scope,
                "stage": event.stage.value,
                "qwen_status": event.qwen_status,
                "memory_id": event.memory_id,
            }
            for event in events
        ]
    }


async def write_operational_note(
    note_id: str,
    agent_id: str,
    subject: str,
    claim: str,
    evidence_refs: list[str],
    scope: str = "",
    org_id: str = "default",
) -> dict[str, Any]:
    """Write an evidence-linked note that another agent can safely read.

    This creates a non-Qwen-generated Reality Memory claim. It is deliberately
    separate from resolved-experience compilation and cannot execute actions.
    Every evidence reference must belong to the API-key-resolved organization.
    """
    values = {
        "note_id": note_id.strip(),
        "agent_id": agent_id.strip(),
        "subject": subject.strip(),
        "claim": claim.strip(),
        "scope": scope.strip(),
    }
    if not all(values[key] for key in ("note_id", "agent_id", "subject", "claim")):
        raise ValueError("note_id, agent_id, subject, and claim are required")
    refs = list(dict.fromkeys(str(item).strip() for item in evidence_refs if str(item).strip()))
    if not refs:
        raise ValueError("At least one evidence reference is required")
    repository = get_source_repository()
    for ref in refs:
        record = await repository.get_ingestion_by_id(org_id, ref)
        if record is None:
            raise ValueError(f"Evidence reference is not available in this organization: {ref}")
        if record.availability != "available":
            raise ValueError(f"Evidence reference is unavailable: {ref}")

    existing = await repository.get_operational_note(org_id, values["note_id"])
    if existing is not None:
        if (
            existing.agent_id != values["agent_id"]
            or existing.subject != values["subject"][:160]
            or existing.scope != values["scope"][:240]
            or existing.claim != values["claim"][:2000]
            or existing.evidence_refs != refs
        ):
            raise ValueError("Operational note ID already exists with different content.")
        return {
            "note": existing.model_dump(mode="json"),
            "memory_id": existing.memory_id,
            "idempotent": True,
            "human_approval_required": True,
            "external_action_permitted": False,
        }

    claim_key = f"agent-note:{values['scope']}:{values['subject']}".strip(":").lower()
    stable = hashlib.sha256(
        f"{org_id}|{values['note_id']}|{values['claim']}".encode("utf-8")
    ).hexdigest()[:24]
    memory = await repository.reconcile_memory(
        RealityMemory(
            memory_id=f"memory-note-{stable}",
            org_id=org_id,
            claim_key=claim_key,
            subject=values["subject"][:160],
            predicate="agent_reports",
            scope=values["scope"][:240],
            claim=values["claim"][:2000],
            source_ingestion_ids=refs,
            source_evidence_ids=refs,
            qwen_rationale="Agent-authored operational note; Qwen did not generate this claim.",
            qwen_generated=False,
        )
    )
    from backend.sources.models import OperationalNote

    note = await repository.save_operational_note(
        OperationalNote(
            note_id=values["note_id"],
            org_id=org_id,
            agent_id=values["agent_id"],
            subject=values["subject"][:160],
            scope=values["scope"][:240],
            claim=values["claim"][:2000],
            evidence_refs=refs,
            memory_id=memory.memory_id,
            qwen_generated=False,
        )
    )
    return {
        "note": note.model_dump(mode="json"),
        "memory_id": memory.memory_id,
        "memory_status": memory.status.value,
        "source_evidence_ids": refs,
        "qwen_generated": False,
        "idempotent": False,
        "human_approval_required": True,
        "external_action_permitted": False,
    }


async def query_cross_agent_memory(
    subject: str = "",
    scope: str = "",
    top_k: int = 10,
    org_id: str = "default",
) -> dict[str, Any]:
    """Read shared agent notes and their Reality Memory lineage."""
    repository = get_source_repository()
    notes = await repository.list_operational_notes(
        org_id,
        subject=subject,
        scope=scope,
        limit=top_k,
    )
    memories = await repository.list_memories(
        org_id,
        query=subject or None,
        include_superseded=True,
        limit=top_k,
    )
    evidence_ids = list(dict.fromkeys(ref for note in notes for ref in note.evidence_refs))
    evidence = []
    for evidence_id in evidence_ids:
        item = await repository.get_ingestion_by_id(org_id, evidence_id)
        if item is not None:
            evidence.append(
                {
                    "ingestion_id": item.ingestion_id,
                    "provider": item.provider.value,
                    "source_name": item.source_name,
                    "excerpt": item.excerpt,
                    "freshness": item.freshness,
                    "availability": item.availability,
                    "raw_payload_sha256": item.raw_payload_sha256,
                }
            )
    return {
        "notes": [note.model_dump(mode="json") for note in notes],
        "memories": [memory.model_dump(mode="json") for memory in memories],
        "evidence": evidence,
        "agent_ids": sorted({note.agent_id for note in notes}),
        "org_id": org_id,
        "human_approval_required": True,
        "external_action_permitted": False,
    }


def attestation() -> dict[str, Any]:
    """Describe the current audit boundary without inventing an attestation."""
    import hashlib
    from datetime import datetime, timezone

    tools_manifest = [
        {
            "name": "recall_skills",
            "purpose": "Surface fleet memory before planning",
        },
        {
            "name": "check_intercept",
            "purpose": "Pre-flight governance with optional SAG metadata",
        },
        {
            "name": "evaluate_workflow",
            "purpose": "Return an evidence-backed DecisionBrief for a workflow template",
        },
        {
            "name": "compile_experience",
            "purpose": "Write resolved experience back to the brain",
        },
        {
            "name": "inspect_memory",
            "purpose": "Inspect current and superseded source-backed Reality Memory",
        },
        {
            "name": "query_evidence",
            "purpose": "Inspect immutable source-event evidence summaries",
        },
        {
            "name": "write_operational_note",
            "purpose": "Write an evidence-linked note into shared Reality Memory",
        },
        {
            "name": "query_cross_agent_memory",
            "purpose": "Read shared agent notes with provenance",
        },
    ]
    measurement = hashlib.sha256(b"company-brain-build-metadata-v1").hexdigest()
    return {
        "tee_capable": False,
        "platform": "Standard cloud host (TDX capability checked at runtime)",
        "attestation_verified": False,
        "measurement": measurement,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "mcp_endpoint": "/mcp/",
        "attestation_endpoint": "/mcp/attestation",
        "tools": tools_manifest,
        "narrative": (
            "This metadata endpoint does not claim a hardware quote. The runtime "
            "route reports TDX only when the running host verifies it; otherwise "
            "decision integrity uses the explicit RSA audit fallback."
        ),
    }
