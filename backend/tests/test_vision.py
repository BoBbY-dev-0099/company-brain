"""Multimodal evidence stays typed, redacted, and honest when Qwen is down."""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.config import settings
from backend.routers import sources as source_router
from backend.sources import vision
from backend.sources.models import ConnectionStatus, IngestionStage, SourceConnection, SourceIngestion, SourceProvider
from backend.sources.service import SourceService


@pytest.mark.asyncio
async def test_qwen_vision_extracts_typed_observation_without_persisting_image(monkeypatch):
    content = '{"summary":"Worker memory is 95%","memory_claim":"Worker memory is near capacity.","metric_name":"memory_usage","metric_value":95,"metric_unit":"percent","confidence":"high","needs_review":true}'

    class _Completions:
        async def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    monkeypatch.setattr(
        vision,
        "_client",
        lambda: SimpleNamespace(chat=SimpleNamespace(completions=_Completions())),
    )
    image = b"fake-png-bytes"
    result = await vision.extract_observation(image, "image/png")

    assert result["qwen_status"] == "compiled"
    assert result["metric_value"] == 95
    assert result["confidence"] == "high"
    assert image.decode("ascii") not in str(result)


@pytest.mark.asyncio
async def test_qwen_vision_unavailable_never_fabricates_metric(monkeypatch):
    monkeypatch.setattr(settings, "QWEN_API_KEY", "")
    result = await vision.extract_observation(b"fake-png-bytes", "image/png")

    assert result["qwen_status"] == "unavailable"
    assert result["metric_value"] is None
    assert result["needs_review"] is True


@pytest.mark.asyncio
async def test_vision_route_stores_digest_only_and_source_metadata(monkeypatch):
    image = b"fake-png-bytes"
    request = SimpleNamespace(
        state=SimpleNamespace(auth_type="agent", org_id="org-a"),
        headers={"X-Brain-Api-Key": "key"},
    )
    monkeypatch.setattr(source_router, "_require_source_write_capability", AsyncMock(return_value="org-a"))
    monkeypatch.setattr(
        source_router,
        "extract_observation",
        AsyncMock(
            return_value={
                "qwen_status": "compiled",
                "model": "qwen-vl-plus",
                "summary": "Worker memory is 95%.",
                "memory_claim": "Worker memory is near capacity.",
                "metric_name": "memory_usage",
                "metric_value": 95,
                "metric_unit": "percent",
                "confidence": "high",
                "needs_review": True,
            }
        ),
    )
    accepted = AsyncMock(side_effect=lambda ingestion: (True, ingestion))
    monkeypatch.setattr(source_router.source_service, "accept", accepted)

    body = source_router.VisionEvidenceRequest(
        image_base64=base64.b64encode(image).decode("ascii"),
        mime_type="image/png",
    )
    result = await source_router.ingest_vision_evidence(request, body)
    ingestion = accepted.await_args.args[0]

    assert result["original_image_persisted"] is False
    assert result["qwen_status"] == "compiled"
    assert ingestion.provider == SourceProvider.WEB
    assert ingestion.source_type == "vision_observation"
    assert ingestion.metadata["modality"] == "image"
    assert ingestion.raw_payload["image_sha256"] == result["image_sha256"]
    assert "fake-png-bytes" not in str(ingestion.raw_payload)


@pytest.mark.asyncio
async def test_vision_memory_uses_qwen_claim_and_preserves_unavailable_state(monkeypatch):
    class _Repository:
        async def update_ingestion(self, ingestion, *, stage, error=None, **fields):
            return ingestion.model_copy(update={"stage": stage, "error": error, **fields})

        async def reconcile_memory(self, memory):
            return memory

        async def upsert_connection(self, connection):
            return connection

    ingestion = SourceIngestion(
        ingestion_id="vision-1",
        provider=SourceProvider.WEB,
        org_id="org-a",
        external_id="image-1",
        source_type="vision_observation",
        source_name="Grafana screenshot",
        excerpt="Worker memory 95 percent.",
        raw_payload_sha256="a" * 64,
        metadata={
            "modality": "image",
            "vision_status": "compiled",
            "vision_claim": "Worker memory is near capacity.",
        },
    )
    monkeypatch.setattr(vision.settings, "QWEN_API_KEY", "")
    monkeypatch.setattr(
        "backend.sources.service.configured_connections",
        lambda **_: [
            SourceConnection(
                provider=SourceProvider.WEB,
                org_id="org-a",
                title="Verified web evidence",
                status=ConnectionStatus.CONTRACT_READY,
            )
        ],
    )
    result = await SourceService(repository=_Repository()).process(ingestion)

    assert result.stage == IngestionStage.DECISION_READY
    assert result.qwen_status == "compiled"
    assert result.memory_id is not None
