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
from backend.sources.models import IngestionStage, SourceIngestion, SourceProvider


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
    assert len(out["tools"]) == 8
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


@pytest.mark.asyncio
async def test_cross_agent_note_is_shared_with_source_lineage_and_is_idempotent(monkeypatch):
    source = SourceIngestion(
        ingestion_id="source-1",
        provider=SourceProvider.SLACK,
        org_id="org-a",
        external_id="event-1",
        source_type="slack_message",
        source_name="Slack",
        excerpt="Fulfillment OOM incident is open.",
        raw_payload_sha256="a" * 64,
        stage=IngestionStage.DECISION_READY,
    )

    class _Repository:
        def __init__(self):
            self.notes = {}
            self.memories = []

        async def get_ingestion_by_id(self, org_id, ingestion_id):
            return source if org_id == source.org_id and ingestion_id == source.ingestion_id else None

        async def get_operational_note(self, org_id, note_id):
            return self.notes.get((org_id, note_id))

        async def reconcile_memory(self, memory):
            self.memories.append(memory)
            return memory

        async def save_operational_note(self, note):
            self.notes[(note.org_id, note.note_id)] = note
            return note

        async def list_operational_notes(self, org_id, subject=None, scope=None, limit=20):
            return [note for (note_org, _), note in self.notes.items() if note_org == org_id][:limit]

        async def list_memories(self, org_id, query=None, include_superseded=False, limit=20):
            return [memory for memory in self.memories if memory.org_id == org_id][:limit]

    repository = _Repository()
    monkeypatch.setattr(brain_tools, "get_source_repository", lambda: repository)

    written = await brain_tools.write_operational_note(
        note_id="sales-acme-1",
        agent_id="sales-agent",
        subject="Acme fulfillment blocker",
        claim="Acme release concern is tied to the open fulfillment OOM incident.",
        evidence_refs=["source-1"],
        scope="acme",
        org_id="org-a",
    )
    replay = await brain_tools.write_operational_note(
        note_id="sales-acme-1",
        agent_id="sales-agent",
        subject="Acme fulfillment blocker",
        claim="Acme release concern is tied to the open fulfillment OOM incident.",
        evidence_refs=["source-1"],
        scope="acme",
        org_id="org-a",
    )
    read = await brain_tools.query_cross_agent_memory(
        subject="Acme",
        scope="acme",
        org_id="org-a",
    )

    assert written["qwen_generated"] is False
    assert written["external_action_permitted"] is False
    assert replay["idempotent"] is True
    assert read["agent_ids"] == ["sales-agent"]
    assert read["notes"][0]["memory_id"] == written["memory_id"]
    assert read["evidence"][0]["ingestion_id"] == "source-1"


@pytest.mark.asyncio
async def test_cross_agent_note_rejects_cross_org_evidence_and_note_rewrite(monkeypatch):
    class _Repository:
        async def get_ingestion_by_id(self, org_id, ingestion_id):
            return None

        async def get_operational_note(self, org_id, note_id):
            return None

    monkeypatch.setattr(brain_tools, "get_source_repository", lambda: _Repository())
    with pytest.raises(ValueError, match="not available in this organization"):
        await brain_tools.write_operational_note(
            note_id="foreign-note",
            agent_id="cs-agent",
            subject="Acme",
            claim="Foreign claim",
            evidence_refs=["org-b-source"],
            org_id="org-a",
        )
