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
_TEST_ORG_ID = "pytest-store"


@pytest.fixture
async def db():
    await store.init_db()
    db_handle = store.get_db()
    try:
        yield db_handle
    finally:
        for collection in ("skills", "events", "sessions", "skill_outcomes"):
            await db_handle[collection].delete_many({"org_id": _TEST_ORG_ID})
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
    await store.save_skill(s, org_id=_TEST_ORG_ID)
    got = await store.get_skill(sid, org_id=_TEST_ORG_ID)
    assert got is not None
    assert got.skill_id == sid


@_skip
@pytest.mark.asyncio
async def test_save_skill_increments_version(db):
    sid = f"vers-{uuid.uuid4().hex[:6]}"
    s = _make_skill(sid)
    saved1 = await store.save_skill(s, org_id=_TEST_ORG_ID)
    first_version = saved1.version
    saved2 = await store.save_skill(s, org_id=_TEST_ORG_ID)
    assert first_version == 1
    assert saved2.version == 2


@_skip
@pytest.mark.asyncio
async def test_human_confirmed_outcome_promotes_auto_execute(db):
    sid = f"reinf-{uuid.uuid4().hex[:6]}"
    s = _make_skill(sid, conf=0.83)
    await store.save_skill(s, org_id=_TEST_ORG_ID)

    # Only persisted human-confirmed effective outcomes can cross the threshold.
    for _ in range(2):
        outcome = await store.record_human_outcome(
            sid,
            _TEST_ORG_ID,
            "confirmed_effective",
            "reviewer@example.test",
        )
        assert outcome["reinforced"] is True

    final = await store.get_skill(sid, org_id=_TEST_ORG_ID)
    assert final is not None
    assert final.provenance.confidence >= 0.85
    assert final.provenance.human_confirmed_outcome_count == 2
    assert final.executable.auto_execute is True


@_skip
@pytest.mark.asyncio
async def test_non_effective_human_outcome_does_not_reinforce(db):
    sid = f"rejected-{uuid.uuid4().hex[:6]}"
    s = _make_skill(sid, conf=0.83)
    await store.save_skill(s, org_id=_TEST_ORG_ID)

    outcome = await store.record_human_outcome(
        sid,
        _TEST_ORG_ID,
        "rejected",
        "reviewer@example.test",
        note="The evidence did not support this recommendation.",
    )

    final = await store.get_skill(sid, org_id=_TEST_ORG_ID)
    assert outcome["reinforced"] is False
    assert final is not None
    assert final.provenance.confidence == 0.83
    assert final.provenance.human_confirmed_outcome_count == 0
    assert final.executable.auto_execute is False


@_skip
@pytest.mark.asyncio
async def test_session_persistence(db):
    sid = f"sess-{uuid.uuid4().hex[:6]}"
    sess = SessionMemory(session_id=sid, agent_id="product-agent-1", user_id="demo-user")
    await store.save_session(sess, org_id=_TEST_ORG_ID)
    got = await store.get_session(sid, org_id=_TEST_ORG_ID)
    assert got is not None
    assert got.session_id == sid
