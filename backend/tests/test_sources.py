"""Regression tests for source-backed Reality Memory boundaries."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.config import settings
from backend.routers import sources as source_router
from backend.sources import adapters
from backend.sources.models import SourceIngestion, SourceProvider
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
