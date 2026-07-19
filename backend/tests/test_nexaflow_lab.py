"""Contract coverage for the judge-facing NexaFlow temporal-memory lab."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from backend.demo.nexaflow_lab import SCENARIOS, run_nexaflow_scenario, scenario_catalog
from backend.middleware.auth import _judge_session_path
from backend.sources.models import IngestionStage, RealityMemory
from backend.sources.service import source_service


def test_nexaflow_catalog_contains_the_four_honest_memory_scenarios():
    catalog = scenario_catalog()
    assert [item["id"] for item in catalog] == [
        "sla-conflict",
        "stale-owner",
        "agent-handoff",
        "absence-of-evidence",
    ]
    assert "No confirmed" in SCENARIOS["absence-of-evidence"]["answer"]["headline"]
    assert SCENARIOS["sla-conflict"]["answer"]["status"] == "conflict_detected"


def test_nexaflow_run_route_consumes_the_browser_judge_session():
    assert _judge_session_path("/demo-company/nexaflow/agent-handoff") is True


@pytest.mark.asyncio
async def test_nexaflow_runs_fixture_evidence_through_the_shared_source_contract(monkeypatch):
    accepted = []

    async def accept(ingestion):
        accepted.append(ingestion)
        return True, ingestion

    async def process(ingestion):
        return ingestion.model_copy(
            update={
                "stage": IngestionStage.DECISION_READY,
                "memory_id": f"memory-{ingestion.ingestion_id}",
                "qwen_status": "compiled_ephemeral",
                "is_judge_sandbox": True,
            }
        )

    async def get_memory(org_id, memory_id):
        return RealityMemory(
            memory_id=memory_id,
            org_id=org_id,
            claim_key="nexaflow-acme-api-latency",
            subject="Acme Corp",
            predicate="API latency concern",
            scope="customer handoff",
            claim="A source-linked fixture memory.",
            is_ephemeral=True,
        )

    monkeypatch.setattr(source_service, "accept", accept)
    monkeypatch.setattr(source_service, "process", process)
    monkeypatch.setattr(source_service.repository, "get_memory", get_memory)

    result = await run_nexaflow_scenario(scenario_id="agent-handoff", org_id="judge-sandbox:test")

    assert result["mode"] == "judge_sandbox"
    assert result["scenario"]["id"] == "agent-handoff"
    assert result["answer"]["status"] == "context_updated"
    assert len(accepted) == 2
    assert all(item.metadata["fixture"] is True for item in accepted)
    assert all(item.metadata["memory_key"] == "nexaflow-acme-api-latency" for item in accepted)
    assert [item["qwen_status"] for item in result["events"]] == ["compiled_ephemeral", "compiled_ephemeral"]
    assert len(result["memories"]) == 2
