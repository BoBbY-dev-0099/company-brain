"""Read-only NexaFlow edge cache for intermittent warehouse connectivity.

This service deliberately does not run a local model or execute actions. It
keeps the latest server-issued decision/memory snapshot available on a small
node and marks the snapshot stale when the central console cannot be reached.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI

logger = logging.getLogger(__name__)

app = FastAPI(title="NexaFlow Edge Cache", version="1.0.0")
CACHE_PATH = Path(os.getenv("EDGE_CACHE_PATH", "/opt/company-brain/edge-cache/overview.json"))
CENTRAL_BASE_URL = os.getenv("CENTRAL_BASE_URL", "").rstrip("/")
SYNC_INTERVAL_SECONDS = max(10, int(os.getenv("SYNC_INTERVAL_SECONDS", "300")))
_sync_task: asyncio.Task[None] | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_snapshot(status: str = "not_synced") -> dict[str, Any]:
    return {
        "status": status,
        "mode": "edge_cache",
        "central_url_configured": bool(CENTRAL_BASE_URL),
        "synced_at": None,
        "source_connections": [],
        "memories": [],
        "latest_release_check": None,
        "external_action_permitted": False,
        "human_approval_required": True,
    }


def _read_snapshot() -> dict[str, Any]:
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _empty_snapshot()


def _write_snapshot(snapshot: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(snapshot, default=str), encoding="utf-8")
    temporary.replace(CACHE_PATH)


async def sync_once() -> dict[str, Any]:
    """Pull only the public, read-only overview from the central console."""
    if not CENTRAL_BASE_URL:
        snapshot = _empty_snapshot("not_configured")
        _write_snapshot(snapshot)
        return snapshot
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            response = await client.get(f"{CENTRAL_BASE_URL}/api/nexaflow/overview")
            response.raise_for_status()
            overview = response.json()
        snapshot = {
            "status": "fresh",
            "mode": "edge_cache",
            "central_url_configured": True,
            "synced_at": _now(),
            "source_connections": overview.get("connections", []),
            "memories": overview.get("memories", [])[:20],
            "latest_release_check": overview.get("latest_release_check"),
            "external_action_permitted": False,
            "human_approval_required": True,
        }
        _write_snapshot(snapshot)
        return snapshot
    except Exception as exc:  # noqa: BLE001
        logger.warning("edge sync unavailable: %s", exc)
        current = _read_snapshot()
        current["status"] = "stale" if current.get("synced_at") else "unavailable"
        current["last_sync_error"] = str(exc)[:240]
        _write_snapshot(current)
        return current


async def _sync_loop() -> None:
    while True:
        await sync_once()
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)


@app.on_event("startup")
async def start_edge_sync() -> None:
    global _sync_task
    _sync_task = asyncio.create_task(_sync_loop())


@app.on_event("shutdown")
async def stop_edge_sync() -> None:
    global _sync_task
    if _sync_task is not None:
        _sync_task.cancel()
        _sync_task = None


@app.get("/health")
async def health() -> dict[str, Any]:
    snapshot = _read_snapshot()
    return {
        "status": "ok",
        "mode": "edge_cache",
        "snapshot_status": snapshot.get("status"),
        "synced_at": snapshot.get("synced_at"),
        "external_action_permitted": False,
    }


@app.get("/memory")
async def memory() -> dict[str, Any]:
    """Return the cached source-backed memory and latest governed decision."""
    return _read_snapshot()
