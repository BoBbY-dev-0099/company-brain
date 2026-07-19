"""MCP tool implementations.

These are the actual Python functions that back the MCP tools. The MCP server
(server.py) registers scoped wrappers over authenticated Streamable HTTP.
In-process backend integrations import these functions directly to avoid transport loopback.
"""

from __future__ import annotations

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
