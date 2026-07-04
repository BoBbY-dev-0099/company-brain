"""Engineering agent: reviews PRs with a brain pre-flight intercept."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from backend.agents.base import AgentRunResult, MCPToolLoopAgent
from backend.core import propagator
from backend.core.schema import DecisionCheckRequest, InterceptResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are the Engineering Agent for Company Brain demo.

You review proposed PR changes. Your job:
  1. Call recall_skills with the PR description to surface relevant prior
     engineering decisions.
  2. If a skill matches, follow its recommended_action and intercept_message.
     Specifically call out the skill_id you applied.
  3. If the system has flagged this PR with a pre-flight intercept (you'll
     see "PRE-FLIGHT INTERCEPT" in the user message), do NOT approve the PR
     as-is. Recommend the alternative the brain suggests.
  4. If you actually proceed with a review, call compile_experience with
     event_type='pr_reviewed' so the brain learns from your reasoning.
  5. Reply with: a verdict (APPROVE / BLOCK / REVISE), the reasoning, and the
     skill_id(s) that informed your call.
"""


class EngineeringAgent(MCPToolLoopAgent):
    agent_id = "engineering-agent-1"
    agent_type = "engineering"
    system_prompt = _SYSTEM_PROMPT


_singleton: EngineeringAgent | None = None


def get_agent() -> EngineeringAgent:
    global _singleton
    if _singleton is None:
        _singleton = EngineeringAgent()
    return _singleton


async def _pre_flight(
    user_message: str,
    agent_id: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, bool, str | None]:
    """Run check_intercept against the brain BEFORE the LLM call.

    Returns (augmented_message, intercepted, matched_skill_id).
    """
    from backend.core.interceptor import check_decision  # local import avoids cycle

    req = DecisionCheckRequest(
        agent_id=agent_id,
        decision_text=user_message,
        domain="engineering",
        metadata=metadata or {},
    )
    resp = await check_decision(req)

    if resp.result == InterceptResult.CLEAR or resp.matched_skill is None:
        return user_message, False, None

    await propagator.broadcast_intercept(
        agent_id=agent_id,
        skill=resp.matched_skill,
        result=resp.result,
        confidence=resp.confidence,
    )

    if resp.result == InterceptResult.suspended:
        augmented = (
            f"PRE-FLIGHT SAG SUSPENSION from Company Brain:\n"
            f"  result: suspended\n"
            f"  matched skill: {resp.matched_skill.skill_id} ({resp.matched_skill.name})\n"
            f"  suspension_reason: {resp.suspension_reason}\n"
            f"  evidence: {resp.suspension_evidence}\n\n"
            f"Original PR description:\n{user_message}"
        )
    else:
        augmented = (
            f"PRE-FLIGHT INTERCEPT from Company Brain:\n"
            f"  result: {resp.result.value}\n"
            f"  matched skill: {resp.matched_skill.skill_id} ({resp.matched_skill.name})\n"
            f"  confidence: {resp.confidence:.2f}\n"
            f"  intercept_message: {resp.intercept_message}\n"
            f"  recommended_action: {resp.recommended_action}\n\n"
            f"Original PR description:\n{user_message}"
        )
    return augmented, True, resp.matched_skill.skill_id


async def run(user_message: str, metadata: dict[str, Any] | None = None) -> AgentRunResult:
    agent = get_agent()
    pr_id = (metadata or {}).get("pr_id") or f"pr-{uuid.uuid4().hex[:8]}"

    augmented, pre_intercepted, pre_skill = await _pre_flight(
        user_message,
        agent.agent_id,
        metadata=metadata,
    )

    await propagator.broadcast_agent_action(
        agent_id=agent.agent_id,
        action_type="pr_received",
        content=user_message[:200],
        metadata={"pr_id": pr_id, "pre_intercepted": pre_intercepted, "pre_skill": pre_skill},
    )

    result = await agent.run(augmented)

    if pre_intercepted:
        result.intercepted = True
        if not result.intercept_skill:
            result.intercept_skill = pre_skill

    await propagator.broadcast_agent_action(
        agent_id=agent.agent_id,
        action_type="pr_reviewed",
        content=result.response[:200],
        metadata={
            "pr_id": pr_id,
            "skills_used": result.skills_used,
            "intercepted": result.intercepted,
            "intercept_skill": result.intercept_skill,
        },
    )
    return result


__all__ = ["run", "get_agent"]
