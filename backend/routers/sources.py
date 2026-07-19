"""Source adapter, Reality Memory, and controlled replay HTTP surface."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, HttpUrl

from backend.config import settings
from backend.brain import store as brain_store
from backend.demo.judge_session import is_judge_sandbox_org
from backend.sources.adapters import (
    fetch_verified_web_evidence,
    redact_slack_payload,
    sha256_payload,
    slack_event_allowed,
    utc_from_epoch,
    verify_slack_signature,
)
from backend.sources.models import SourceIngestion, SourceProvider
from backend.sources.service import configured_connections, source_service


router = APIRouter(tags=["sources"])


def _org(request: Request) -> str:
    return getattr(request.state, "org_id", None) or settings.DEMO_ORG_ID


async def _require_source_write_capability(request: Request) -> str:
    if getattr(request.state, "auth_type", None) != "agent":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Brain-Api-Key is required")
    raw_key = request.headers.get("X-Brain-Api-Key", "")
    record = await brain_store.get_db()["api_keys"].find_one({"api_key": raw_key, "revoked_at": None})
    permissions = str((record or {}).get("permissions", "")).split()
    if "mcp:write" not in permissions:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A source-sync request requires an API key with mcp:write.",
        )
    return _org(request)


class VerifiedWebRequest(BaseModel):
    url: HttpUrl
    label: str = Field(default="Verified web evidence", max_length=120)
    memory_key: str | None = Field(default=None, max_length=160)


@router.get("/source-connections")
async def get_source_connections(request: Request) -> dict[str, Any]:
    org_id = _org(request)
    configured = configured_connections(org_id=org_id)
    try:
        stored = await source_service.repository.stored_connections(org_id)
    except RuntimeError:
        stored = {}
    output = []
    for item in configured:
        prior = stored.get(item.provider.value)
        if prior:
            item.last_success_at = prior.last_success_at
            item.last_error = prior.last_error
            item.health = prior.health
        output.append(item.model_dump(mode="json"))
    return {"connections": output}


@router.get("/source-events")
async def get_source_events(request: Request, limit: int = 30) -> dict[str, Any]:
    records = await source_service.repository.list_ingestions(_org(request), limit=limit)
    return {"events": [item.model_dump(mode="json") for item in records]}


@router.get("/reality-memory")
async def get_reality_memory(
    request: Request,
    query: str | None = None,
    include_superseded: bool = False,
    limit: int = 30,
) -> dict[str, Any]:
    memories = await source_service.repository.list_memories(
        _org(request), query=query, include_superseded=include_superseded, limit=limit
    )
    return {"memories": [item.model_dump(mode="json") for item in memories]}


@router.get("/reality-overview")
async def get_reality_overview(request: Request) -> dict[str, Any]:
    org_id = _org(request)
    events = await source_service.repository.list_ingestions(org_id, limit=8)
    memories = await source_service.repository.list_memories(org_id, include_superseded=True, limit=8)
    return {
        "connections": (await get_source_connections(request))["connections"],
        "events": [item.model_dump(mode="json") for item in events],
        "memories": [item.model_dump(mode="json") for item in memories],
        "mode": "judge_sandbox" if is_judge_sandbox_org(org_id) else "sandbox",
    }


@router.post("/integrations/slack/events")
async def slack_events(
    request: Request,
    x_slack_signature: str | None = Header(default=None),
    x_slack_request_timestamp: str | None = Header(default=None),
) -> dict[str, Any]:
    raw = await request.body()
    if not settings.SLACK_SIGNING_SECRET.strip():
        raise HTTPException(status_code=503, detail={"error": "SLACK_NOT_CONFIGURED"})
    if not verify_slack_signature(
        secret=settings.SLACK_SIGNING_SECRET,
        body=raw,
        timestamp=x_slack_request_timestamp,
        signature=x_slack_signature,
    ):
        raise HTTPException(status_code=401, detail={"error": "INVALID_SLACK_SIGNATURE"})
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail={"error": "INVALID_SLACK_PAYLOAD"}) from exc
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    if payload.get("type") != "event_callback" or not slack_event_allowed(payload):
        return {"ok": True, "accepted": False}
    event = payload.get("event") or {}
    event_id = str(payload.get("event_id") or "")
    if not event_id:
        raise HTTPException(status_code=422, detail={"error": "SLACK_EVENT_ID_MISSING"})
    channel = str(event.get("channel") or "")
    text = str(event.get("text") or "").strip()
    if not text:
        return {"ok": True, "accepted": False}
    org_id = settings.SOURCE_ORG_ID
    ingestion = SourceIngestion(
        ingestion_id=f"slack-{hashlib.sha256(event_id.encode()).hexdigest()[:24]}",
        provider=SourceProvider.SLACK,
        org_id=org_id,
        external_id=event_id,
        source_type="slack_message",
        source_name="Slack #ops-incidents",
        occurred_at=utc_from_epoch(event.get("event_ts") or payload.get("event_time")),
        excerpt=text[:20000],
        raw_payload_sha256=sha256_payload(raw),
        raw_payload=redact_slack_payload(payload),
        auth_verified=True,
        metadata={
            "team_id": payload.get("team_id"),
            "channel_id": channel,
            "thread_ts": event.get("thread_ts") or event.get("ts"),
            "memory_subject": "Operations incident",
            "memory_predicate": "reports",
            "memory_scope": channel,
        },
        acl_scope=[f"team:{payload.get('team_id')}", f"channel:{channel}", "read_only"],
    )
    claimed, stored = await source_service.accept(ingestion)
    return {"ok": True, "accepted": claimed, "ingestion_id": stored.ingestion_id}


@router.post("/integrations/google-drive/sync")
async def sync_google_drive(request: Request) -> dict[str, Any]:
    org_id = await _require_source_write_capability(request)
    try:
        accepted = await source_service.ingest_drive_documents(org_id=org_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail={"error": "GOOGLE_DRIVE_UNAVAILABLE", "detail": str(exc)}) from exc
    return {"accepted": len(accepted), "ingestion_ids": [item.ingestion_id for item in accepted]}


@router.post("/integrations/web/fetch")
async def fetch_web(request: Request, body: VerifiedWebRequest) -> dict[str, Any]:
    org_id = await _require_source_write_capability(request)
    try:
        payload = await fetch_verified_web_evidence(str(body.url))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "WEB_EVIDENCE_REJECTED", "detail": str(exc)}) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail={"error": "WEB_EVIDENCE_FETCH_FAILED", "detail": str(exc)[:300]}) from exc
    ingestion = SourceIngestion(
        ingestion_id=f"web-{uuid.uuid4().hex}",
        provider=SourceProvider.WEB,
        org_id=org_id,
        external_id=payload["content_sha256"],
        source_type="verified_web_page",
        source_name=body.label,
        source_url=payload["url"],
        excerpt=payload["excerpt"],
        raw_payload_sha256=payload["content_sha256"],
        raw_payload={"url": payload["url"], "content_type": payload["content_type"]},
        auth_verified=True,
        metadata={
            "content_type": payload["content_type"],
            "memory_subject": body.label,
            "memory_predicate": "states",
            "memory_scope": urlsplit_host(payload["url"]),
            "memory_key": body.memory_key or "",
        },
        acl_scope=[f"host:{urlsplit_host(payload['url'])}", "read_only"],
    )
    claimed, stored = await source_service.accept(ingestion)
    return {"accepted": claimed, "ingestion": stored.model_dump(mode="json")}


def urlsplit_host(value: str) -> str:
    from urllib.parse import urlsplit

    return str(urlsplit(value).hostname or "")


@router.post("/reality/replay/incident")
async def replay_incident(request: Request) -> dict[str, Any]:
    """Run a deterministic source fixture through the real source pipeline.

    This accepts no caller evidence and writes only to the browser-scoped
    sandbox when one exists.  It gives judges a complete, replayable source →
    memory trace without pretending their browser is connected to Slack/Drive.
    """
    org_id = _org(request)
    now = datetime.now(timezone.utc)
    fixture = [
        {
            "provider": SourceProvider.SLACK,
            "external": "fixture-slack-export-incident-v1",
            "source_type": "slack_message",
            "source_name": "Slack #ops-incidents",
            "excerpt": "SEV-2: export-worker started OOM-killing after the latest deployment. Pause the release until the memory limit is restored.",
            "metadata": {"memory_subject": "export-worker", "memory_predicate": "incident", "memory_scope": "production", "memory_key": "export-worker-incident"},
        },
        {
            "provider": SourceProvider.GOOGLE_DRIVE,
            "external": "fixture-drive-export-runbook-v1",
            "source_type": "google_drive_document",
            "source_name": "Google Drive — Export service runbook",
            "excerpt": "Approved runbook: export-worker requires at least 16 MiB memory. A lower effective limit requires explicit SRE validation before release.",
            "metadata": {"memory_subject": "export-worker", "memory_predicate": "minimum memory", "memory_scope": "production", "memory_key": "export-worker-minimum-memory"},
        },
        {
            "provider": SourceProvider.GITHUB,
            "external": "fixture-github-pr-842-v1",
            "source_type": "github_pull_request",
            "source_name": "GitHub PR #842",
            "excerpt": "Merged PR #842 changes EXPORT_WORKER_MEMORY_MB from 25 to 8.",
            "metadata": {"memory_subject": "export-worker", "memory_predicate": "configured memory", "memory_scope": "production", "memory_key": "export-worker-configured-memory", "changed_field": "worker_memory_mb", "previous_value": 25, "current_value": 8},
        },
    ]
    events = []
    for item in fixture:
        external = f"{item['external']}:{org_id}"
        ingestion = SourceIngestion(
            ingestion_id=f"fixture-{hashlib.sha256(external.encode()).hexdigest()[:24]}",
            provider=item["provider"],
            org_id=org_id,
            external_id=external,
            source_type=item["source_type"],
            source_name=item["source_name"],
            occurred_at=now,
            excerpt=item["excerpt"],
            raw_payload_sha256=sha256_payload(item),
            raw_payload={"fixture": "incident-to-release-v1", "provider": item["provider"].value},
            auth_verified=True,
            metadata={**item["metadata"], "fixture": True},
            acl_scope=["fixture", "judge_sandbox"],
        )
        claimed, stored = await source_service.accept(ingestion)
        if claimed or stored.stage.value != "decision_ready":
            stored = await source_service.process(stored)
        events.append(stored)
    evidence = [
        {
            "source_type": "slack_message",
            "source_name": fixture[0]["source_name"],
            "external_id": events[0].external_id,
            "occurred_at": now.isoformat(),
            "excerpt": fixture[0]["excerpt"],
            "metadata": {"source_ingestion_id": events[0].ingestion_id},
        },
        {
            "source_type": "google_drive_document",
            "source_name": fixture[1]["source_name"],
            "external_id": events[1].external_id,
            "occurred_at": now.isoformat(),
            "excerpt": fixture[1]["excerpt"],
            "metadata": {"source_ingestion_id": events[1].ingestion_id},
        },
        {
            "source_type": "github_pull_request",
            "source_name": fixture[2]["source_name"],
            "external_id": events[2].external_id,
            "occurred_at": now.isoformat(),
            "excerpt": fixture[2]["excerpt"],
            "metadata": {"source_ingestion_id": events[2].ingestion_id, **fixture[2]["metadata"]},
        },
        {
            "source_type": "runtime_metric",
            "source_name": "Runtime telemetry",
            "external_id": "fixture-export-worker-memory-v1",
            "occurred_at": now.isoformat(),
            "excerpt": "export-worker effective memory limit is 8 MiB after the deployment.",
            "metadata": {"source": "fixture runtime telemetry"},
        },
    ]
    return {
        "mode": "judge_sandbox" if is_judge_sandbox_org(org_id) else "sandbox",
        "events": [item.model_dump(mode="json") for item in events],
        "workflow": {
            "template_id": "release-safety",
            "evidence": evidence,
            "live_context": {"worker_memory_mb": 8, "runbook_validated": False, "deployment_window_open": True},
        },
    }
