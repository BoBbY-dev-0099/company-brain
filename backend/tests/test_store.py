"""Integration smoke for the store layer.

Skipped automatically if MongoDB is not reachable. Run a local Mongo first:
    docker compose up -d
"""

from __future__ import annotations

import os
import uuid

import pytest

from backend.brain import store
from backend.core.schema import (
    CompanyBrainSkill,
    DecayRate,
    SessionMemory,
    SkillExecutable,
    SkillKnowledge,
    SkillPattern,
    SkillProvenance,
)


_skip = pytest.mark.skipif(
    os.environ.get("RUN_MONGO_TESTS") != "1",
    reason="set RUN_MONGO_TESTS=1 to run integration smoke",
)


@pytest.fixture(scope="module")
async def db():
    await store.init_db()
    yield store.get_db()
    await store.close()


def _make_skill(skill_id: str, conf: float = 0.6) -> CompanyBrainSkill:
    return CompanyBrainSkill(
        skill_id=skill_id,
        name=f"Skill {skill_id}",
        domain="engineering",
        pattern=SkillPattern(keywords=["k"]),
        knowledge=SkillKnowledge(anti_conditions=["nope"]),
        executable=SkillExecutable(),
        provenance=SkillProvenance(confidence=conf, decay_rate=DecayRate.MEDIUM),
    )


@_skip
@pytest.mark.asyncio
async def test_save_and_get_skill(db):
    sid = f"smoke-{uuid.uuid4().hex[:6]}"
    s = _make_skill(sid)
    await store.save_skill(s)
    got = await store.get_skill(sid)
    assert got is not None
    assert got.skill_id == sid


@_skip
@pytest.mark.asyncio
async def test_save_skill_increments_version(db):
    sid = f"vers-{uuid.uuid4().hex[:6]}"
    s = _make_skill(sid)
    saved1 = await store.save_skill(s)
    saved2 = await store.save_skill(s)
    assert saved1.version == 2  # the second call upserts and bumps
    assert saved2.version == 3


@_skip
@pytest.mark.asyncio
async def test_reinforce_promotes_auto_execute(db):
    sid = f"reinf-{uuid.uuid4().hex[:6]}"
    s = _make_skill(sid, conf=0.83)
    await store.save_skill(s)

    # Enough reinforcements to cross 0.85
    for _ in range(2):
        await store.reinforce_skill(sid)

    final = await store.get_skill(sid)
    assert final is not None
    assert final.provenance.confidence >= 0.85
    assert final.executable.auto_execute is True


@_skip
@pytest.mark.asyncio
async def test_session_persistence(db):
    sid = f"sess-{uuid.uuid4().hex[:6]}"
    sess = SessionMemory(session_id=sid, agent_id="product-agent-1", user_id="demo-user")
    await store.save_session(sess)
    got = await store.get_session(sid)
    assert got is not None
    assert got.session_id == sid
