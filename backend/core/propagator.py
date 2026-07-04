"""SSE propagation: a small in-process pub/sub.

Subscribers register a queue; broadcast() fans out to all queues, dropping
any subscriber whose queue is full or closed (the SSE handler removes itself
on disconnect via remove_subscriber).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from backend.brain import store
from backend.core.schema import (
    CompanyBrainSkill,
    InterceptResult,
    SSEEvent,
    SSEEventType,
)

logger = logging.getLogger(__name__)

_QUEUE_MAX = 100
_subscribers: dict[str, tuple[str | None, asyncio.Queue[SSEEvent]]] = {}


def add_subscriber(org_id: str | None = None) -> tuple[str, asyncio.Queue[SSEEvent]]:
    sub_id = uuid.uuid4().hex[:12]
    q: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=_QUEUE_MAX)
    _subscribers[sub_id] = (org_id, q)
    logger.info("SSE subscriber added: %s org=%s (total=%d)", sub_id, org_id, len(_subscribers))
    return sub_id, q


def remove_subscriber(sub_id: str) -> None:
    _subscribers.pop(sub_id, None)
    logger.info("SSE subscriber removed: %s (total=%d)", sub_id, len(_subscribers))


def subscriber_count() -> int:
    return len(_subscribers)


async def broadcast(event: SSEEvent, org_id: str | None = None) -> None:
    dead: list[str] = []
    for sub_id, (sub_org, q) in _subscribers.items():
        # If caller specifies org_id, only send to matching subscribers.
        if org_id is not None and sub_org is not None and sub_org != org_id:
            continue
        try:
            q.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("SSE subscriber %s queue full; dropping", sub_id)
            dead.append(sub_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("SSE subscriber %s broadcast error: %s", sub_id, exc)
            dead.append(sub_id)
    for sub_id in dead:
        remove_subscriber(sub_id)


def _skill_summary(skill: CompanyBrainSkill) -> dict[str, Any]:
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "version": skill.version,
        "domain": skill.domain,
        "summary": skill.summary,
        "confidence": skill.provenance.confidence,
        "reinforcement_count": skill.provenance.reinforcement_count,
        "auto_execute": skill.executable.auto_execute,
        "decay_rate": skill.provenance.decay_rate.value,
        "intercept_message": skill.executable.intercept_message,
    }


async def propagate_skill(skill: CompanyBrainSkill, is_new: bool = True, org_id: str | None = None) -> None:
    agent_ids = await store.get_all_agent_ids(org_id=org_id)
    event = SSEEvent(
        type=SSEEventType.SKILL_COMPILED if is_new else SSEEventType.SKILL_REINFORCED,
        payload={
            "skill": _skill_summary(skill),
            "agent_ids": agent_ids,
        },
    )
    await broadcast(event, org_id=org_id)


async def broadcast_intercept(
    agent_id: str,
    skill: CompanyBrainSkill,
    result: InterceptResult,
    confidence: float,
    org_id: str | None = None,
) -> None:
    event = SSEEvent(
        type=SSEEventType.DECISION_INTERCEPTED,
        payload={
            "agent_id": agent_id,
            "skill": _skill_summary(skill),
            "result": result.value,
            "confidence": confidence,
        },
    )
    await broadcast(event, org_id=org_id)


async def broadcast_agent_action(
    agent_id: str,
    action_type: str,
    content: str,
    metadata: dict[str, Any] | None = None,
    org_id: str | None = None,
) -> None:
    event = SSEEvent(
        type=SSEEventType.AGENT_ACTION,
        payload={
            "agent_id": agent_id,
            "action_type": action_type,
            "content": content,
            "metadata": metadata or {},
        },
    )
    await broadcast(event, org_id=org_id)


async def broadcast_skill_invalidated(skill_id: str, superseded_by: str | None = None) -> None:
    await broadcast(SSEEvent(
        type=SSEEventType.SKILL_INVALIDATED,
        payload={"skill_id": skill_id, "superseded_by": superseded_by},
    ))


async def broadcast_keepalive() -> None:
    await broadcast(SSEEvent(type=SSEEventType.KEEPALIVE, payload={}))
