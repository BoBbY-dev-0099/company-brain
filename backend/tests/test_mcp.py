"""Smoke tests for MCP tool implementations.

These exercise the in-process functions that back the MCP tools, but skip the
full SSE handshake. Mongo and Qwen are not required: tools are tested with
monkeypatched stubs.
"""

from __future__ import annotations

import pytest

from backend.core.schema import (
    CompanyBrainSkill,
    SkillExecutable,
    SkillKnowledge,
    SkillPattern,
    SkillProvenance,
)
from backend.mcp import tools as brain_tools


@pytest.mark.asyncio
async def test_recall_skills_empty(monkeypatch):
    async def fake_recall(_context, top_k=5, org_id="default"):
        return []
    monkeypatch.setattr(
        "backend.mcp.tools.interceptor.recall_skills_for_context",
        fake_recall,
    )
    out = await brain_tools.recall_skills(context="anything")
    assert out == {"skills": []}


@pytest.mark.asyncio
async def test_recall_skills_with_match(monkeypatch):
    s = CompanyBrainSkill(
        skill_id="x",
        name="X",
        domain="engineering",
        summary="sum",
        pattern=SkillPattern(keywords=["k"]),
        knowledge=SkillKnowledge(anti_conditions=["nope"]),
        executable=SkillExecutable(intercept_message="msg", recommended_action="do x", auto_execute=True),
        provenance=SkillProvenance(confidence=0.9),
    )

    async def fake_recall(_context, top_k=5, org_id="default"):
        return [s]
    monkeypatch.setattr(
        "backend.mcp.tools.interceptor.recall_skills_for_context",
        fake_recall,
    )
    out = await brain_tools.recall_skills(context="anything")
    assert len(out["skills"]) == 1
    sk = out["skills"][0]
    assert sk["skill_id"] == "x"
    assert sk["auto_execute"] is True
    assert sk["intercept_message"] == "msg"
    assert sk["recommended_action"] == "do x"


def test_attestation_payload_shape():
    out = brain_tools.attestation()
    assert out["tee_capable"] is True
    assert "Intel TDX" in out["platform"]
    assert "narrative" in out
