"""Read-only source ledger plus signed/read-only connector ingress."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field, HttpUrl

from backend.brain import store as brain_store
from backend.config import settings
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
from backend.sources.vision import extract_observation


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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A source write requires mcp:write.")
    return _org(request)


class VerifiedWebRequest(BaseModel):
    url: HttpUrl
    label: str = Field(default="Verified web evidence", max_length=120)
    memory_key: str | None = Field(default=None, max_length=160)


class VisionEvidenceRequest(BaseModel):
    """Base64 image request for an authenticated, read-only evidence adapter."""

    image_base64: str = Field(min_length=16, max_length=6_000_000)
    mime_type: str = Field(default="image/png", pattern=r"^image/(?:png|jpeg|webp)$")
    label: str = Field(default="Operational dashboard screenshot", max_length=120)
    memory_key: str | None = Field(default="nexaflow:vision:operational-metric", max_length=160)


@router.get("/source-connections")
async def get_source_connections(request: Request) -> dict[str, Any]:
    org_id = _org(request)
    configured = configured_connections(org_id=org_id)
    stored = await source_service.repository.stored_connections(org_id)
    for item in configured:
        previous = stored.get(item.provider.value)
        if previous:
            item.last_success_at = previous.last_success_at
            item.last_error = previous.last_error
            item.health = previous.health
    return {"connections": [item.model_dump(mode="json") for item in configured]}


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


@router.post("/integrations/slack/events")
async def slack_events(
    request: Request,
    x_slack_signature: str | None = Header(default=None),
    x_slack_request_timestamp: str | None = Header(default=None),
) -> dict[str, Any]:
    """Persist a verified, allowlisted event before acknowledging Slack."""
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
    text = str(event.get("text") or "").strip()
    if not event_id:
        raise HTTPException(status_code=422, detail={"error": "SLACK_EVENT_ID_MISSING"})
    if not text:
        return {"ok": True, "accepted": False}
    channel = str(event.get("channel") or "")
    ingestion = SourceIngestion(
        ingestion_id=f"slack-{hashlib.sha256(event_id.encode()).hexdigest()[:24]}",
        provider=SourceProvider.SLACK,
        org_id=settings.SOURCE_ORG_ID,
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
            "memory_subject": "NexaFlow operations incident",
            "memory_predicate": "reports",
            "memory_scope": channel,
        },
        acl_scope=[f"team:{payload.get('team_id')}", f"channel:{channel}", "read_only"],
    )
    claimed, stored = await source_service.accept(ingestion)
    return {"ok": True, "accepted": claimed, "ingestion_id": stored.ingestion_id}


@router.post("/integrations/alibaba-oss/sync")
async def sync_alibaba_oss(request: Request) -> dict[str, Any]:
    org_id = await _require_source_write_capability(request)
    try:
        accepted = await source_service.ingest_oss_documents(org_id=org_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail={"error": "ALIBABA_OSS_UNAVAILABLE", "detail": str(exc)}) from exc
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
    from urllib.parse import urlsplit

    host = str(urlsplit(payload["url"]).hostname or "")
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
        metadata={"content_type": payload["content_type"], "memory_subject": body.label, "memory_predicate": "states", "memory_scope": host, "memory_key": body.memory_key or ""},
        acl_scope=[f"host:{host}", "read_only"],
    )
    claimed, stored = await source_service.accept(ingestion)
    return {"accepted": claimed, "ingestion": stored.model_dump(mode="json")}


@router.post("/integrations/vision/evidence")
async def ingest_vision_evidence(request: Request, body: VisionEvidenceRequest) -> dict[str, Any]:
    """Persist Qwen vision output as evidence; never persist the original image."""
    org_id = await _require_source_write_capability(request)
    try:
        image = base64.b64decode(body.image_base64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=422, detail={"error": "INVALID_IMAGE_BASE64"}) from exc
    try:
        observation = await extract_observation(image, body.mime_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error": "VISION_EVIDENCE_REJECTED", "detail": str(exc)}) from exc
    digest = hashlib.sha256(image).hexdigest()
    qwen_status = str(observation.get("qwen_status") or "unavailable")
    summary = str(observation.get("summary") or "Vision extraction unavailable; no metric was asserted.")
    claim = str(observation.get("memory_claim") or "No image-derived operational claim is available.")
    excerpt = (
        f"{summary} Metric: {observation.get('metric_name') or 'not detected'} "
        f"{observation.get('metric_value') if observation.get('metric_value') is not None else 'n/a'} "
        f"{observation.get('metric_unit') or ''}. Confidence: {observation.get('confidence', 'low')}."
    )[:4000]
    ingestion = SourceIngestion(
        ingestion_id=f"vision-{digest[:24]}",
        provider=SourceProvider.WEB,
        org_id=org_id,
        external_id=digest,
        source_type="vision_observation",
        source_name=body.label,
        occurred_at=datetime.now(timezone.utc),
        excerpt=excerpt,
        raw_payload_sha256=digest,
        raw_payload={"mime_type": body.mime_type, "image_sha256": digest, "observation": observation},
        auth_verified=True,
        metadata={
            "modality": "image",
            "vision_model": observation.get("model"),
            "vision_status": qwen_status,
            "vision_claim": claim,
            "memory_subject": body.label,
            "memory_predicate": "observes",
            "memory_scope": "vision",
            "memory_key": body.memory_key or "nexaflow:vision:operational-metric",
        },
        acl_scope=["authenticated_agent", "read_only", "image_digest_only"],
        qwen_status=qwen_status,
    )
    claimed, stored = await source_service.accept(ingestion)
    return {
        "accepted": claimed,
        "qwen_status": qwen_status,
        "observation": observation,
        "image_sha256": digest,
        "original_image_persisted": False,
        "ingestion": stored.model_dump(mode="json"),
    }
