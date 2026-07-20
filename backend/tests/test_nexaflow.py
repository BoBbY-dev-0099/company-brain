"""NexaFlow aggregate decision: only persisted, fresh source evidence counts."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend import main
from backend.routers import nexaflow
from backend.sources.models import IngestionStage, SourceIngestion, SourceProvider
from backend.sources.service import source_service


class _Repository:
    def __init__(self, records: list[SourceIngestion]) -> None:
        self.records = records

    async def list_ingestions(self, _org_id: str, limit: int = 80) -> list[SourceIngestion]:
        return self.records[:limit]


class _Request:
    state = SimpleNamespace(org_id="caller-controlled-org")


def _source(provider: SourceProvider, excerpt: str, source_type: str) -> SourceIngestion:
    now = datetime.now(timezone.utc)
    return SourceIngestion(
        ingestion_id=f"{provider.value}-1",
        provider=provider,
        org_id="nexaflow-demo",
        external_id=f"{provider.value}-external-1",
        source_type=source_type,
        source_name=provider.value,
        occurred_at=now,
        retrieved_at=now,
        excerpt=excerpt,
        raw_payload_sha256="a" * 64,
        stage=IngestionStage.DECISION_READY,
        qwen_status="compiled",
        memory_id=f"memory-{provider.value}",
    )


@pytest.mark.asyncio
async def test_release_check_suspends_for_open_incident_and_memory_drop(monkeypatch):
    records = [
        _source(SourceProvider.SLACK, "SEV-2: fulfillment workers are OOM. Pause promotion.", "slack_message"),
        _source(SourceProvider.GOOGLE_DRIVE, "Fulfillment workers require at least 24 MiB of memory before promotion.", "google_drive_document"),
        _source(SourceProvider.GITHUB, "+NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=8", "github_pull_request"),
    ]
    monkeypatch.setattr(source_service, "repository", _Repository(records))

    response = await nexaflow.release_check(_Request())

    assert response["run"]["org_id"] == "nexaflow-demo"
    assert response["run"]["decision_brief"]["verdict"] == "suspended"
    assert response["parsing"]["runbook_minimum_memory_mb"] == 24
    assert response["parsing"]["merged_worker_memory_mb"] == 8
    assert response["parsing"]["linked_incident_open"] is True


@pytest.mark.asyncio
async def test_release_check_requires_review_when_required_source_is_missing(monkeypatch):
    records = [
        _source(SourceProvider.GOOGLE_DRIVE, "Fulfillment workers require at least 24 MiB of memory before promotion.", "google_drive_document"),
        _source(SourceProvider.GITHUB, "+NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=32", "github_pull_request"),
    ]
    monkeypatch.setattr(source_service, "repository", _Repository(records))

    response = await nexaflow.release_check(_Request())

    assert response["run"]["decision_brief"]["verdict"] == "review_required"
    assert any("slack_message" in item["reason"] for item in response["run"]["decision_brief"]["missing_evidence"])


@pytest.mark.asyncio
async def test_release_check_requires_review_for_same_time_conflicting_runbooks(monkeypatch):
    now = datetime.now(timezone.utc)
    first = _source(
        SourceProvider.ALIBABA_OSS,
        "Fulfillment workers require at least 24 MiB of memory.",
        "alibaba_oss_object",
    ).model_copy(update={"occurred_at": now, "raw_payload_sha256": "a" * 64})
    second = _source(
        SourceProvider.ALIBABA_OSS,
        "Fulfillment workers require at least 32 MiB of memory.",
        "alibaba_oss_object",
    ).model_copy(update={"occurred_at": now, "raw_payload_sha256": "b" * 64})
    records = [
        _source(SourceProvider.SLACK, "SEV-2 OOM: pause promotion.", "slack_message"),
        first,
        second,
        _source(SourceProvider.GITHUB, "+NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=32", "github_pull_request"),
    ]
    monkeypatch.setattr(source_service, "repository", _Repository(records))

    response = await nexaflow.release_check(_Request())

    assert response["run"]["decision_brief"]["verdict"] == "review_required"
    assert response["source_selection"]["alibaba_oss"] is None


def test_parsers_need_real_nexaflow_markers():
    assert nexaflow._runbook_minimum("Fulfillment workers require at least 24 MiB.") == 24
    assert nexaflow._github_memory_value("+NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=8") == 8
    assert nexaflow._github_memory_value("a generic memory setting is 8") is None
    assert nexaflow._incident_state("SEV-2 OOM: pause promotion") is True
    assert nexaflow._incident_state("SEV-2: OOM. Pause promotion until the incident is resolved.") is True
    assert nexaflow._incident_state("SEV-2 OOM resolved") is False
    assert nexaflow._incident_state("daily standup notes") is None


@pytest.mark.asyncio
async def test_readiness_reports_scenario_and_canonical_counts(monkeypatch):
    class _ReadinessRepository:
        async def list_ingestions(self, _org_id: str, limit: int = 1000):
            return [object(), object(), object()][:limit]

        async def list_memories(self, _org_id: str, include_superseded: bool = True, limit: int = 1000):
            return [
                SimpleNamespace(status=SimpleNamespace(value="active")),
                SimpleNamespace(status=SimpleNamespace(value="superseded")),
            ][:limit]

    class _ReadinessWorkflowService:
        async def list_runs(self, *, org_id: str, limit: int = 1000):
            return [object()][:limit]

    monkeypatch.setattr(main.source_service, "repository", _ReadinessRepository())
    monkeypatch.setattr(main, "WorkflowService", lambda: _ReadinessWorkflowService())
    monkeypatch.setattr(main.settings, "SOURCE_ORG_ID", "nexaflow-demo")
    monkeypatch.setattr(main.settings, "DEMO_SCENARIO_VERSION", "nexaflow-live-v1")

    response = await main.demo_readiness()

    assert response["scenario_version"] == "nexaflow-live-v1"
    assert response["source_org_id"] == "nexaflow-demo"
    assert response["database_status"] == "connected"
    assert response["canonical_counts"] == {
        "evidence": 3,
        "memories": 2,
        "active_memories": 1,
        "workflow_runs": 1,
    }
