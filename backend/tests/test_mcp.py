"""Smoke tests for MCP tool implementations.

These exercise the in-process functions that back the MCP tools, but skip the
full SSE handshake. Mongo and Qwen are not required: tools are tested with
monkeypatched stubs.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.core.schema import (
    ApplicabilityCondition,
    ApplicabilityOperator,
    ApplicabilityStatus,
    CompanyBrainSkill,
    DecisionCheckResponse,
    InterceptResult,
    SkillExecutable,
    SkillKnowledge,
    SkillPattern,
    SkillProvenance,
)
from backend.mcp import tools as brain_tools


def _sag_skill() -> CompanyBrainSkill:
    return CompanyBrainSkill(
        skill_id="data-export-large-file-timeout",
        name="Large data export timeout",
        domain="engineering",
        summary="Large chunk exports timeout",
        pattern=SkillPattern(
            keywords=["data export", "timeout", "chunk", "file size", "csv", "large"],
            entity_types=["api_endpoint"],
            context_signals=["sync_request"],
        ),
        knowledge=SkillKnowledge(anti_conditions=[]),
        executable=SkillExecutable(
            intercept_message="Use smaller chunks",
            recommended_action="Reduce chunk size",
            auto_execute=True,
        ),
        provenance=SkillProvenance(confidence=0.94),
        invalidated_if=[
            ApplicabilityCondition(
                key="export_chunk_size_mb",
                operator=ApplicabilityOperator.lte,
                value=10,
            )
        ],
    )


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
    assert out["tee_capable"] is False
    assert "Standard cloud" in out["platform"]
    assert "narrative" in out
    assert "tools" in out
    assert len(out["tools"]) == 6
    assert out["mcp_endpoint"] == "/mcp/"
    assert "measurement" in out


@pytest.mark.asyncio
async def test_check_intercept_forwards_metadata_to_sag(monkeypatch):
    """MCP check_intercept must pass metadata into the interceptor for SAG."""
    skill = _sag_skill()
    captured: dict = {}

    async def fake_check_decision(req):
        captured["metadata"] = req.metadata
        return DecisionCheckResponse(
            result=InterceptResult.suspended,
            confidence=0.94,
            matched_skill=skill,
            intercept_message=skill.executable.intercept_message,
            recommended_action=skill.executable.recommended_action,
            auto_execute=True,
            rationale="suspended by applicability gate",
            applicability_status=ApplicabilityStatus.suspended.value,
            suspension_reason="export_chunk_size_mb <= 10",
            suspension_evidence={"export_chunk_size_mb": 8},
        )

    monkeypatch.setattr("backend.mcp.tools.interceptor.check_decision", fake_check_decision)
    monkeypatch.setattr(
        "backend.mcp.tools.propagator.broadcast_intercept",
        AsyncMock(),
    )

    out = await brain_tools.check_intercept(
        agent_id="eng-01",
        decision_text="Increase data export chunk size to improve throughput",
        metadata={"export_chunk_size_mb": 8},
    )

    assert captured["metadata"] == {"export_chunk_size_mb": 8}
    assert out["result"] == "suspended"
    assert out["applicability_status"] == ApplicabilityStatus.suspended.value
    assert out["suspension_reason"] == "export_chunk_size_mb <= 10"
    assert out["suspension_evidence"] == {"export_chunk_size_mb": 8}


@pytest.mark.asyncio
async def test_check_intercept_metadata_defaults_empty(monkeypatch):
    captured: dict = {}

    async def fake_check_decision(req):
        captured["metadata"] = req.metadata
        return DecisionCheckResponse(
            result=InterceptResult.CLEAR,
            confidence=0.0,
            rationale="brain is empty",
        )

    monkeypatch.setattr("backend.mcp.tools.interceptor.check_decision", fake_check_decision)

    out = await brain_tools.check_intercept(
        agent_id="eng-01",
        decision_text="Unrelated decision",
    )

    assert captured["metadata"] == {}
    assert out["result"] == "clear"
    assert out["applicability_status"] is None
