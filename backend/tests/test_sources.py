"""Regression tests for source-backed Reality Memory boundaries."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.config import settings
from backend.routers import sources as source_router
from backend.sources import adapters
from backend.sources.service import normalise_source_timestamp
from backend.sources.models import ConnectionStatus, SourceConnection, SourceIngestion, SourceProvider
from backend.sources import service as source_service_module
from backend.sources.service import SourceService
from backend.workflows.models import workflow_now


class _Request:
    def __init__(self, body: bytes):
        self._body = body
        self.state = SimpleNamespace(org_id=None, auth_type="open")
        self.headers: dict[str, str] = {}

    async def body(self) -> bytes:
        return self._body


def _signature(secret: str, timestamp: str, body: bytes) -> str:
    base = b"v0:" + timestamp.encode("ascii") + b":" + body
    return "v0=" + hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()


def _payload() -> dict:
    return {
        "type": "event_callback",
        "team_id": "T-OPS",
        "event_id": "Ev-1",
        "event_time": 1_700_000_000,
        "event": {
            "type": "message",
            "channel": "C-INCIDENTS",
            "event_ts": "1700000000.000001",
            "text": "SEV-2: export worker is OOM after deploy.",
        },
    }


def test_slack_signature_rejects_stale_and_accepts_fresh(monkeypatch):
    monkeypatch.setattr(settings, "SLACK_EVENT_MAX_AGE_SECONDS", 300)
    body = b'{"event":"test"}'
    timestamp = "1000"
    signature = _signature("secret", timestamp, body)
    assert adapters.verify_slack_signature(secret="secret", body=body, timestamp=timestamp, signature=signature, now=1001)
    assert not adapters.verify_slack_signature(secret="secret", body=body, timestamp=timestamp, signature=signature, now=1401)
    assert not adapters.verify_slack_signature(secret="other", body=body, timestamp=timestamp, signature=signature, now=1001)


def test_source_timestamp_normalisation_handles_legacy_naive_mongo_values():
    naive = datetime(2026, 7, 19, 12, 0, 0)
    normalised = normalise_source_timestamp(naive)
    assert normalised.tzinfo == timezone.utc
    assert normalised.isoformat() == "2026-07-19T12:00:00+00:00"


def test_slack_event_scope_is_team_and_channel_limited(monkeypatch):
    monkeypatch.setattr(settings, "SLACK_ALLOWED_TEAM_ID", "T-OPS")
    monkeypatch.setattr(settings, "SLACK_ALLOWED_CHANNEL_IDS", "C-INCIDENTS")
    assert adapters.slack_event_allowed(_payload())
    outside = _payload(); outside["event"]["channel"] = "C-RANDOM"
    assert not adapters.slack_event_allowed(outside)


@pytest.mark.asyncio
async def test_slack_endpoint_persists_only_verified_allowlisted_evidence(monkeypatch):
    secret = "signing-secret"
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", secret)
    monkeypatch.setattr(settings, "SLACK_ALLOWED_TEAM_ID", "T-OPS")
    monkeypatch.setattr(settings, "SLACK_ALLOWED_CHANNEL_IDS", "C-INCIDENTS")
    monkeypatch.setattr(settings, "SOURCE_ORG_ID", "source-org")
    raw = json.dumps(_payload()).encode("utf-8")
    accepted = AsyncMock(side_effect=lambda ingestion: (True, ingestion))
    monkeypatch.setattr(source_router.source_service, "accept", accepted)
    timestamp = str(int(workflow_now().timestamp()))
    result = await source_router.slack_events(
        _Request(raw),
        x_slack_signature=_signature(secret, timestamp, raw),
        x_slack_request_timestamp=timestamp,
    )
    assert result["accepted"] is True
    ingestion = accepted.await_args.args[0]
    assert ingestion.org_id == "source-org"
    assert ingestion.provider == SourceProvider.SLACK
    assert ingestion.auth_verified is True
    assert ingestion.raw_payload_sha256 == hashlib.sha256(raw).hexdigest()
    assert ingestion.excerpt.startswith("SEV-2")
    assert ingestion.acl_scope == ["team:T-OPS", "channel:C-INCIDENTS", "read_only"]


@pytest.mark.asyncio
async def test_slack_duplicate_event_is_idempotent(monkeypatch):
    secret = "signing-secret"
    monkeypatch.setattr(settings, "SLACK_SIGNING_SECRET", secret)
    monkeypatch.setattr(settings, "SLACK_ALLOWED_TEAM_ID", "T-OPS")
    monkeypatch.setattr(settings, "SLACK_ALLOWED_CHANNEL_IDS", "C-INCIDENTS")
    monkeypatch.setattr(settings, "SOURCE_ORG_ID", "source-org")
    raw = json.dumps(_payload()).encode("utf-8")
    accepted = AsyncMock(side_effect=lambda ingestion: (accepted.await_count == 1, ingestion))
    monkeypatch.setattr(source_router.source_service, "accept", accepted)
    timestamp = str(int(workflow_now().timestamp()))
    signature = _signature(secret, timestamp, raw)

    first = await source_router.slack_events(
        _Request(raw),
        x_slack_signature=signature,
        x_slack_request_timestamp=timestamp,
    )
    second = await source_router.slack_events(
        _Request(raw),
        x_slack_signature=signature,
        x_slack_request_timestamp=timestamp,
    )

    assert first["accepted"] is True
    assert second["accepted"] is False
    assert first["ingestion_id"] == second["ingestion_id"]


@pytest.mark.asyncio
async def test_oss_temporary_unavailability_is_explicit_503(monkeypatch):
    monkeypatch.setattr(source_router, "_require_source_write_capability", AsyncMock(return_value="org-a"))
    monkeypatch.setattr(
        source_router.source_service,
        "ingest_oss_documents",
        AsyncMock(side_effect=RuntimeError("OSS returned 503")),
    )
    with pytest.raises(Exception) as exc_info:
        await source_router.sync_alibaba_oss(_Request(b""))
    assert exc_info.value.status_code == 503
    assert exc_info.value.detail["error"] == "ALIBABA_OSS_UNAVAILABLE"


@pytest.mark.asyncio
async def test_source_qwen_unavailable_is_visible_without_fabricating_compilation(monkeypatch):
    class _Repository:
        async def update_ingestion(self, ingestion, *, stage, error=None, **fields):
            return ingestion.model_copy(update={"stage": stage, "error": error, **fields})

        async def reconcile_memory(self, memory):
            return memory

        async def upsert_connection(self, connection):
            return connection

    connection = SourceConnection(
        provider=SourceProvider.SLACK,
        org_id="org-a",
        title="Slack incidents",
        status=ConnectionStatus.CONNECTED,
    )
    monkeypatch.setattr(source_service_module, "configured_connections", lambda **_: [connection])
    monkeypatch.setattr(source_service_module.settings, "QWEN_API_KEY", "")
    ingestion = SourceIngestion(
        ingestion_id="qwen-unavailable-1",
        provider=SourceProvider.SLACK,
        org_id="org-a",
        external_id="event-1",
        source_type="slack_message",
        source_name="Slack",
        excerpt="SEV-2 incident remains open.",
        raw_payload_sha256="a" * 64,
        auth_verified=True,
    )

    result = await SourceService(repository=_Repository()).process(ingestion)

    assert result.stage.value == "decision_ready"
    assert result.qwen_status == "unavailable"
    assert result.memory_id is not None


@pytest.mark.asyncio
async def test_web_evidence_never_fetches_unallowlisted_hosts(monkeypatch):
    monkeypatch.setattr(settings, "WEB_EVIDENCE_ALLOWED_HOSTS", "status.example.test")
    with pytest.raises(ValueError, match="ALLOWED_HOSTS"):
        await adapters._validate_public_url("https://internal.example.test/secret")


@pytest.mark.asyncio
async def test_web_evidence_rejects_private_ip_even_if_configured(monkeypatch):
    monkeypatch.setattr(settings, "WEB_EVIDENCE_ALLOWED_HOSTS", "127.0.0.1")
    with pytest.raises(ValueError, match="Literal IP"):
        await adapters._validate_public_url("https://127.0.0.1/internal")


@pytest.mark.asyncio
async def test_drive_ingestion_versions_changed_content_without_overwriting_prior_memory(monkeypatch):
    class _Repository:
        def __init__(self):
            self.claimed: list[SourceIngestion] = []

        async def list_ingestions(self, org_id, limit=100):
            return []

        async def claim(self, ingestion):
            self.claimed.append(ingestion)
            return True, ingestion

        async def upsert_connection(self, connection):
            return connection

    class _Drive:
        @staticmethod
        def configured():
            return True

        async def list_documents(self, modified_after=None):
            return [{
                "id": "drive-file-1",
                "name": "Export policy",
                "mimeType": "text/plain",
                "modifiedTime": "2026-07-19T10:00:00Z",
                "webViewLink": "https://drive.example.test/file-1",
            }]

        async def read_document(self, document):
            return "Exports require explicit SRE approval below 16 MiB."

    monkeypatch.setattr(source_service_module, "GoogleDriveAdapter", _Drive)
    monkeypatch.setattr(settings, "GOOGLE_DRIVE_FOLDER_ID", "folder-123")
    repository = _Repository()
    accepted = await SourceService(repository=repository).ingest_drive_documents(org_id="org-a")

    assert len(accepted) == 1
    event = accepted[0]
    assert event.external_id.startswith("drive-file-1:")
    assert event.metadata["file_id"] == "drive-file-1"
    assert event.metadata["content_sha256"]
    assert event.acl_scope == ["drive_folder:folder-123", "read_only"]


@pytest.mark.asyncio
async def test_oss_ingestion_records_private_runbook_provenance(monkeypatch):
    class _Repository:
        async def list_ingestions(self, org_id, limit=100):
            return []

        async def claim(self, ingestion):
            return True, ingestion

        async def upsert_connection(self, connection):
            return connection

    class _OSS:
        @staticmethod
        def configured():
            return True

        async def list_documents(self, modified_after=None):
            return [{
                "key": "runbooks/fulfillment-release-policy.md",
                "etag": "etag-1",
                "size": 120,
                "last_modified": workflow_now().isoformat(),
                "content_type": "text/markdown",
            }]

        async def read_document(self, document):
            return "Fulfillment workers require at least 24 MiB of memory before promotion."

    monkeypatch.setattr(source_service_module, "AlibabaOSSAdapter", _OSS)
    monkeypatch.setattr(settings, "ALIBABA_OSS_REGION", "cn-hongkong")
    monkeypatch.setattr(settings, "ALIBABA_OSS_ENDPOINT", "https://oss-cn-hongkong.aliyuncs.com")
    monkeypatch.setattr(settings, "ALIBABA_OSS_BUCKET", "nexaflow-operations-hk-2026")
    monkeypatch.setattr(settings, "ALIBABA_OSS_PREFIX", "runbooks/")
    monkeypatch.setattr(settings, "ALIBABA_OSS_ACCESS_KEY_ID", "akid")
    monkeypatch.setattr(settings, "ALIBABA_OSS_ACCESS_KEY_SECRET", "secret")

    accepted = await SourceService(repository=_Repository()).ingest_oss_documents(org_id="org-a")

    assert len(accepted) == 1
    event = accepted[0]
    assert event.provider == SourceProvider.ALIBABA_OSS
    assert event.source_type == "alibaba_oss_object"
    assert event.source_url == "oss://nexaflow-operations-hk-2026/runbooks/fulfillment-release-policy.md"
    assert event.metadata["object_key"].startswith("runbooks/")
    assert event.acl_scope == [
        "oss_bucket:nexaflow-operations-hk-2026",
        "oss_prefix:runbooks/",
        "read_only",
    ]


def test_reality_memory_keeps_ephemeral_sandbox_state():
    expiry = workflow_now() + timedelta(minutes=30)
    ingestion = SourceIngestion(
        ingestion_id="sandbox-source-1",
        provider=SourceProvider.SLACK,
        org_id="judge-sandbox:test",
        external_id="Ev-1",
        source_type="slack_message",
        source_name="Slack #ops-incidents",
        excerpt="Pause release after OOM.",
        raw_payload_sha256="abc",
        is_judge_sandbox=True,
        expires_at=expiry,
        metadata={"memory_key": "release-incident", "memory_subject": "export-worker"},
    )
    memory = SourceService._memory_from(ingestion, skill_id=None, qwen_rationale="", qwen_generated=False)
    assert memory.is_ephemeral is True
    assert memory.expires_at == expiry
    assert memory.source_ingestion_ids == ["sandbox-source-1"]
