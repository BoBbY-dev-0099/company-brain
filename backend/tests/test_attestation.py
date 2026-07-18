import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app
from backend.services import tdx_attestation


@pytest.mark.asyncio
async def test_tdx_binary_missing_returns_503(monkeypatch):
    monkeypatch.setattr(tdx_attestation, "tdx_guest_present", lambda: False)
    monkeypatch.setattr(
        "backend.routers.attestation.settings.TDX_BINARY_PATH",
        "/nonexistent/tdx-app",
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/attestation/quote",
            json={
                "skill_id": "data-export-large-file-timeout",
                "decision": "suspended",
                "metadata": {"export_chunk_size_mb": 8},
                "timestamp": "2026-07-18T12:00:00+00:00",
            },
        )
    assert resp.status_code == 503
    detail = resp.json()["detail"]
    assert detail["error"] == "TDX_UNAVAILABLE"
    assert detail["fallback"] == "RSA_AUDIT"


@pytest.mark.asyncio
async def test_invalid_request_returns_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/attestation/quote",
            json={
                "skill_id": "",
                "decision": "suspended",
                "metadata": {},
                "timestamp": "not-iso",
            },
        )
    assert resp.status_code == 422
