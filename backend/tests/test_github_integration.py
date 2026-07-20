"""Unit tests for durable GitHub webhook intake.

These tests keep Mongo, Qwen, and GitHub off the network by replacing every
boundary.  Their main assertion is ordering: success is impossible until raw
evidence, compiled memory, the audit record, and the SSE propagation have all
completed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from backend.core.schema import CompanyBrainSkill, SkillProvenance
from backend.routers import github_integration as github


class _Request:
    def __init__(self, body: bytes, org_id: str = "github-test") -> None:
        self._body = body
        self.state = SimpleNamespace(org_id=org_id)

    async def body(self) -> bytes:
        return self._body


class _DiffResponse:
    text = "diff --git a/worker.py b/worker.py\n+memory limit reduced"

    def raise_for_status(self) -> None:
        return None


class _DiffClient:
    async def __aenter__(self) -> _DiffClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, *args: object, **kwargs: object) -> _DiffResponse:
        return _DiffResponse()


def _payload() -> dict[str, Any]:
    return {
        "action": "closed",
        "repository": {"full_name": "acme/company-api"},
        "pull_request": {
            "merged": True,
            "number": 42,
            "title": "Lower worker memory",
            "body": "Keep exports safe after lowering the worker limit.",
            "diff_url": "https://example.test/pr/42.diff",
            "html_url": "https://example.test/pr/42",
            "merge_commit_sha": "abc123",
            "changed_files": 3,
        },
    }


def _signature(secret: str, raw: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.mark.asyncio
async def test_merged_pr_persists_raw_event_audit_and_sse_before_success(monkeypatch):
    secret = "webhook-secret"
    monkeypatch.setattr(github.settings, "GITHUB_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(github.settings, "GITHUB_TOKEN", "github-token")
    monkeypatch.setattr(github.settings, "SOURCE_ORG_ID", "github-test")
    monkeypatch.setattr(github.httpx, "AsyncClient", lambda **_: _DiffClient())

    calls: list[str] = []
    event_doc: dict[str, Any] = {}
    compiled = CompanyBrainSkill(
        skill_id="worker-memory-runbook",
        name="Worker memory runbook",
        provenance=SkillProvenance(human_confirmed_outcome_count=1),
    )

    async def get_event(*_args: object, **_kwargs: object):
        calls.append("get_event")
        return None

    async def claim_event(event, **_kwargs: object):
        calls.append("claim_event")
        event_doc.update(event.model_dump(mode="python"))
        event_doc.update({"ingestion_status": "received", "skill_compiled": None})
        return True, dict(event_doc)

    async def compile_event(event):
        calls.append("compile")
        assert "memory limit reduced" in event.content
        assert event.metadata["files_changed"] == 3
        return compiled

    async def save_skill(skill, **_kwargs: object):
        calls.append("save_skill")
        return skill

    async def update_event(event_id, org_id, status, **kwargs: object):
        calls.append(f"update:{status}")
        assert event_id == event_doc["event_id"]
        assert org_id == "github-test"
        event_doc["ingestion_status"] = status
        event_doc.update({key: value for key, value in kwargs.items() if value is not None})
        return dict(event_doc)

    async def save_audit(doc):
        calls.append("save_audit")
        assert doc["event_id"] == event_doc["event_id"]
        assert doc["skill_id"] == compiled.skill_id
        return "audit-42"

    async def upsert_key(*_args: object):
        calls.append("upsert_key")

    async def propagate(skill, **_kwargs: object):
        calls.append("propagate")
        assert skill.skill_id == compiled.skill_id

    monkeypatch.setattr(github.store, "get_event", get_event)
    monkeypatch.setattr(github.store, "claim_event", claim_event)
    monkeypatch.setattr(github.store, "get_skill", AsyncMock(return_value=None))
    monkeypatch.setattr(github.store, "save_skill", save_skill)
    monkeypatch.setattr(github.store, "update_event_ingestion", update_event)
    monkeypatch.setattr(github.store, "save_audit_log", save_audit)
    monkeypatch.setattr(github.store, "upsert_public_audit_key", upsert_key)
    monkeypatch.setattr(github.compiler, "compile_event_to_skill", compile_event)
    monkeypatch.setattr(github.propagator, "propagate_skill", propagate)
    monkeypatch.setattr(
        github.rsa_audit,
        "sign_decision",
        lambda *_args, **_kwargs: {
            "signature": "signature",
            "payload": "payload",
            "public_key_fingerprint": "fingerprint",
            "algorithm": "RSA-PSS-SHA256",
            "timestamp": "2026-07-18T00:00:00Z",
        },
    )
    monkeypatch.setattr(github.rsa_audit, "public_key_pem", lambda: "public-key")

    raw = json.dumps(_payload()).encode("utf-8")
    result = await github.github_pr_webhook(
        _Request(raw),
        x_hub_signature_256=_signature(secret, raw),
        x_github_event="pull_request",
        x_github_delivery="delivery-42",
    )

    assert result["ok"] is True
    assert result["duplicate"] is False
    assert result["skill_id"] == compiled.skill_id
    assert result["audit_id"] == "audit-42"
    assert result["workflow_run_id"] is None
    assert result["workflow_status"] is None
    assert result["ingestion_status"] == "completed"
    assert calls == [
        "get_event",
        "claim_event",
        "compile",
        "save_skill",
        "update:skill_persisted",
        "save_audit",
        "upsert_key",
        "update:audited",
        "propagate",
        "update:sse_propagated",
        "update:completed",
    ]


@pytest.mark.asyncio
async def test_completed_delivery_is_idempotent_without_recompile(monkeypatch):
    secret = "webhook-secret"
    monkeypatch.setattr(github.settings, "GITHUB_WEBHOOK_SECRET", secret)
    compiled = AsyncMock()
    monkeypatch.setattr(github.compiler, "compile_event_to_skill", compiled)

    existing = {
        "event_id": "github-pr-known",
        "ingestion_status": "completed",
        "skill_compiled": "known-skill",
        "audit_id": "known-audit",
        "metadata": {
            "repo": "acme/company-api",
            "pr_number": 42,
            "commit_sha": "abc123",
            "html_url": "https://example.test/pr/42",
        },
    }
    monkeypatch.setattr(github.store, "get_event", AsyncMock(return_value=existing))

    raw = json.dumps(_payload()).encode("utf-8")
    result = await github.github_pr_webhook(
        _Request(raw),
        x_hub_signature_256=_signature(secret, raw),
        x_github_event="pull_request",
        x_github_delivery="delivery-42",
    )

    assert result["ok"] is True
    assert result["duplicate"] is True
    assert result["skill_id"] == "known-skill"
    compiled.assert_not_awaited()


def test_event_identity_uses_delivery_and_fallback_is_stable():
    assert github._event_id("same-delivery", "a/b", 1, "sha") == github._event_id(
        "same-delivery", "other/repo", 99, "other"
    )
    assert github._event_id(None, "a/b", 1, "sha") == github._event_id(
        None, "a/b", 1, "sha"
    )
