"""Product agent: cross-session memory demo.

Before answering, this agent looks up prior sessions for the same user_id and
prepends a context line ("Last session you asked about X. Since then, N skills
compiled...") so the demo shows the brain bridging conversations.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from backend.agents.base import AgentRunResult, MCPToolLoopAgent
from backend.brain import store
from backend.core import propagator
from backend.core.schema import SessionMemory, utc_now

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are the Product Agent for Company Brain demo.

Your job:
  1. ALWAYS call recall_skills first — the brain reflects what the company has
     learned across all teams since the user's last session.
  2. If the user message includes a "CROSS-SESSION CONTEXT" preamble, weave
     it into your answer naturally (e.g., "Picking up from your earlier
     question about X — the brain has since compiled a skill that...").
  3. Cite the specific skill_id(s) you're drawing from.
  4. Reply in 3-5 sentences, focused on what's actionable for the user now.

Do NOT compile_experience for product-conversation turns; product Q&A is
not a resolved event.
"""


class ProductAgent(MCPToolLoopAgent):
    agent_id = "product-agent-1"
    agent_type = "product"
    system_prompt = _SYSTEM_PROMPT

    def __init__(self) -> None:
        super().__init__()
        self._cross_session_preamble: str = ""

    async def pre_messages(self, user_message: str) -> list[dict[str, Any]]:
        if self._cross_session_preamble:
            return [{"role": "system", "content": self._cross_session_preamble}]
        return []


_singleton: ProductAgent | None = None


def get_agent() -> ProductAgent:
    global _singleton
    if _singleton is None:
        _singleton = ProductAgent()
    return _singleton


async def _build_cross_session_context(
    user_id: str,
    current_session_id: str | None,
    org_id: str = "default",
) -> str:
    sessions = await store.get_sessions_for_user(user_id, limit=10, org_id=org_id)
    other = [s for s in sessions if s.session_id != current_session_id]
    if not other:
        return ""

    skill_count = await store.get_skill_count(active_only=True, org_id=org_id)

    last = other[0]
    if not last.unresolved_intents and not last.key_decisions:
        return ""

    bits: list[str] = []
    if last.unresolved_intents:
        bits.append(f"unresolved intent: {last.unresolved_intents[0]}")
    if last.key_decisions:
        bits.append(f"prior decision: {last.key_decisions[0]}")

    return (
        "CROSS-SESSION CONTEXT for the Product Agent:\n"
        f"  In session #{last.session_id} this user had — {'; '.join(bits)}.\n"
        f"  Since then, the Company Brain has {skill_count} active skills, "
        f"some of which may now resolve that intent. Reference them by skill_id."
    )


async def run(
    user_message: str,
    user_id: str = "demo-user",
    session_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    org_id: str | None = None,
) -> tuple[AgentRunResult, str]:
    from backend.config import settings

    agent = get_agent()
    resolved_org = org_id or settings.DEMO_ORG_ID
    session_id = session_id or f"session-{uuid.uuid4().hex[:6]}"

    agent._cross_session_preamble = await _build_cross_session_context(
        user_id, session_id, org_id=resolved_org
    )

    await propagator.broadcast_agent_action(
        agent_id=agent.agent_id,
        action_type="qa_received",
        content=user_message[:200],
        metadata={"session_id": session_id},
        org_id=resolved_org,
    )

    result = await agent.run(user_message, org_id=resolved_org)

    # Persist session memory for the next turn.
    existing = await store.get_session(session_id, org_id=resolved_org)
    if existing is None:
        existing = SessionMemory(
            session_id=session_id,
            user_id=user_id,
            agent_id=agent.agent_id,
            org_id=resolved_org,
        )
    existing.turn_count += 1
    existing.org_id = resolved_org
    existing.brain_skills_used = list(dict.fromkeys(existing.brain_skills_used + result.skills_used))
    if user_message and len(existing.unresolved_intents) < 5:
        existing.unresolved_intents.append(user_message[:120])
        existing.unresolved_intents = existing.unresolved_intents[-5:]
    existing.last_updated = utc_now()
    await store.save_session(existing, org_id=resolved_org)

    await propagator.broadcast_agent_action(
        agent_id=agent.agent_id,
        action_type="qa_answered",
        content=result.response[:200],
        metadata={
            "session_id": session_id,
            "skills_used": result.skills_used,
            "iterations": result.iterations,
        },
        org_id=resolved_org,
    )

    return result, session_id
