"""The optional edge profile is a stale-aware read-only cache."""

from __future__ import annotations

import pytest

from backend import edge


@pytest.mark.asyncio
async def test_edge_without_central_url_is_explicitly_not_configured(tmp_path, monkeypatch):
    path = tmp_path / "overview.json"
    monkeypatch.setattr(edge, "CACHE_PATH", path)
    monkeypatch.setattr(edge, "CENTRAL_BASE_URL", "")

    snapshot = await edge.sync_once()

    assert snapshot["status"] == "not_configured"
    assert snapshot["human_approval_required"] is True
    assert snapshot["external_action_permitted"] is False
    assert edge._read_snapshot()["status"] == "not_configured"


@pytest.mark.asyncio
async def test_edge_marks_existing_snapshot_stale_when_sync_fails(tmp_path, monkeypatch):
    path = tmp_path / "overview.json"
    monkeypatch.setattr(edge, "CACHE_PATH", path)
    monkeypatch.setattr(edge, "CENTRAL_BASE_URL", "http://central.invalid")
    edge._write_snapshot(
        {
            "status": "fresh",
            "synced_at": "2026-07-20T00:00:00+00:00",
            "memories": [{"memory_id": "m-1"}],
            "external_action_permitted": False,
            "human_approval_required": True,
        }
    )

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, *args, **kwargs):
            raise RuntimeError("central unavailable")

    monkeypatch.setattr(edge.httpx, "AsyncClient", lambda **_: _Client())
    snapshot = await edge.sync_once()

    assert snapshot["status"] == "stale"
    assert snapshot["memories"] == [{"memory_id": "m-1"}]
    assert snapshot["external_action_permitted"] is False
