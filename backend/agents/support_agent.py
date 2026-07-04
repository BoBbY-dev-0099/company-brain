"""Support agent: resolves customer tickets and compiles experiences."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from backend.agents.base import AgentRunResult, MCPToolLoopAgent
from backend.core import propagator

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are the Support Agent for Company Brain demo.

Your job:
  1. Read the user's ticket.
  2. Call recall_skills to find relevant prior experience.
  3. Apply the recommended_action from any matching skill, citing the skill_id.
  4. Once the ticket is resolved (or you'd send a response), call
     compile_experience ONCE with event_id, event_type='ticket_resolved',
     and a content summary so the brain can learn from this resolution.
  5. Reply to the user in 2-4 sentences. Be concrete; reference the skill that
     guided your answer if one matched.

Always check the brain BEFORE answering. The brain's recommendation overrides
your default reasoning unless you have a specific reason to deviate (in which
case explain why in your answer).
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


async def run(user_message: str, metadata: dict[str, Any] | None = None) -> AgentRunResult:
    agent = get_agent()
    ticket_id = (metadata or {}).get("ticket_id") or f"ticket-{uuid.uuid4().hex[:8]}"

    await propagator.broadcast_agent_action(
        agent_id=agent.agent_id,
        action_type="ticket_received",
        content=user_message[:200],
        metadata={"ticket_id": ticket_id},
    )

    result = await agent.run(user_message)

    await propagator.broadcast_agent_action(
        agent_id=agent.agent_id,
        action_type="ticket_resolved",
        content=result.response[:200],
        metadata={
            "ticket_id": ticket_id,
            "skills_used": result.skills_used,
            "iterations": result.iterations,
        },
    )
    return result
