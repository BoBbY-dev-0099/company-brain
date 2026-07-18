"""Support agent: resolves customer tickets and compiles experiences."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from backend.agents.base import AgentRunResult, MCPToolLoopAgent
from backend.config import settings
from backend.core import propagator

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are the Support Agent for Company Brain demo.

Your job:
  1. Read the user's ticket carefully — answer THAT ticket only.
  2. Call recall_skills with a short paraphrase of the ticket topic
     (e.g. "SaaS refund policy days since purchase").
  3. Prefer skills about refunds / billing / purchase windows when the ticket
     is about refunds. Ignore unrelated skills (MongoDB, exports, auth tokens)
     even if they appear in recall results.
  4. Apply the recommended_action from the best matching refund/billing skill,
     citing its skill_id.
  5. Call compile_experience ONCE with event_type='ticket_resolved' after you
     decide the answer.
  6. Reply in 2-4 sentences about the customer's refund/policy question.
     Do NOT invent unrelated infrastructure advice.

Always check the brain BEFORE answering. Ground every sentence in the ticket
topic + the matched skill.
"""


class SupportAgent(MCPToolLoopAgent):
    agent_id = "support-agent-1"
    agent_type = "support"
    system_prompt = _SYSTEM_PROMPT


_singleton: SupportAgent | None = None


def get_agent() -> SupportAgent:
    global _singleton
    if _singleton is None:
        _singleton = SupportAgent()
    return _singleton


async def run(
    user_message: str,
    metadata: dict[str, Any] | None = None,
    org_id: str | None = None,
) -> AgentRunResult:
    agent = get_agent()
    resolved_org = org_id or settings.DEMO_ORG_ID
    ticket_id = (metadata or {}).get("ticket_id") or f"ticket-{uuid.uuid4().hex[:8]}"

    await propagator.broadcast_agent_action(
        agent_id=agent.agent_id,
        action_type="ticket_received",
        content=user_message[:200],
        metadata={"ticket_id": ticket_id},
        org_id=resolved_org,
    )

    result = await agent.run(user_message, org_id=resolved_org)

    await propagator.broadcast_agent_action(
        agent_id=agent.agent_id,
        action_type="ticket_resolved",
        content=result.response[:200],
        metadata={
            "ticket_id": ticket_id,
            "skills_used": result.skills_used,
            "iterations": result.iterations,
        },
        org_id=resolved_org,
    )
    return result
