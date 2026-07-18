"""MCP tool implementations.

These are the actual Python functions that back the MCP tools. The MCP server
(server.py) registers scoped wrappers over authenticated Streamable HTTP.
In-process agents import these functions directly to avoid transport loopback.
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


def attestation() -> dict[str, Any]:
    """Mock attestation for the demo. Real TDX path is for enterprise."""
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
    ]
    measurement = hashlib.sha256(b"company-brain-mock-enclave-v1").hexdigest()
    return {
        "tee_capable": True,
        "platform": "Intel TDX (Alibaba Cloud g8i / gn8v-tee)",
        "attestation_verified": True,
        "measurement": measurement,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "mcp_endpoint": "/mcp/",
        "attestation_endpoint": "/mcp/attestation",
        "tools": tools_manifest,
        "narrative": (
            "Demo runs on standard cloud; TDX path available for enterprise. "
            "This endpoint returns a mock attestation envelope to demonstrate "
            "the integration shape — production deployments would attest the "
            "running enclave's measurement and bind it to the brain's signing key."
        ),
    }
