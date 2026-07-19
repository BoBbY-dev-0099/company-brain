"""Durable source-ingestion worker for Docker/ECS deployment."""

from __future__ import annotations

import asyncio
import logging

from backend.brain import store
from backend.config import settings
from backend.sources.service import source_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def run() -> None:
    await store.init_db()
    last_drive_sync = 0.0
    try:
        while True:
            processed = await source_service.process_pending()
            if processed:
                logger.info("processed %d source event(s)", len(processed))
            now = asyncio.get_running_loop().time()
            if now - last_drive_sync >= settings.GOOGLE_DRIVE_SYNC_INTERVAL_SECONDS:
                last_drive_sync = now
                try:
                    accepted = await source_service.ingest_drive_documents(org_id=settings.SOURCE_ORG_ID)
                    if accepted:
                        logger.info("accepted %d Drive document(s)", len(accepted))
                except RuntimeError as exc:
                    if "not configured" not in str(exc):
                        logger.warning("Drive sync unavailable: %s", exc)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Drive sync failed: %s", exc)
            await asyncio.sleep(max(0.5, settings.SOURCE_WORKER_POLL_SECONDS))
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(run())
