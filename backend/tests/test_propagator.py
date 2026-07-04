"""Tests for the SSE propagator (subscriber lifecycle, broadcast, backpressure)."""

from __future__ import annotations

import asyncio

import pytest

from backend.core import propagator
from backend.core.schema import SSEEvent, SSEEventType


@pytest.fixture(autouse=True)
def _clean_subscribers():
    propagator._subscribers.clear()
    yield
    propagator._subscribers.clear()


@pytest.mark.asyncio
async def test_add_remove_subscriber():
    sub_id, q = propagator.add_subscriber()
    assert propagator.subscriber_count() == 1
    propagator.remove_subscriber(sub_id)
    assert propagator.subscriber_count() == 0
    _ = q  # silence unused-var


@pytest.mark.asyncio
async def test_broadcast_delivers_to_all_subscribers():
    sub_a_id, q_a = propagator.add_subscriber()
    sub_b_id, q_b = propagator.add_subscriber()

    event = SSEEvent(type=SSEEventType.SKILL_COMPILED, payload={"x": 1})
    await propagator.broadcast(event)

    a = await asyncio.wait_for(q_a.get(), timeout=1.0)
    b = await asyncio.wait_for(q_b.get(), timeout=1.0)
    assert a.payload["x"] == 1
    assert b.payload["x"] == 1
    propagator.remove_subscriber(sub_a_id)
    propagator.remove_subscriber(sub_b_id)


@pytest.mark.asyncio
async def test_broadcast_drops_full_subscriber():
    sub_id, q = propagator.add_subscriber()
    # Fill the queue
    for i in range(propagator._QUEUE_MAX):
        q.put_nowait(SSEEvent(type=SSEEventType.KEEPALIVE, payload={"i": i}))

    await propagator.broadcast(SSEEvent(type=SSEEventType.SKILL_COMPILED, payload={}))
    # The full subscriber should be removed.
    assert sub_id not in propagator._subscribers
