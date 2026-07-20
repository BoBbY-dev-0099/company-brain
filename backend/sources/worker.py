"""Durable source-ingestion worker for Docker/ECS deployment."""

from __future__ import annotations

import asyncio
import logging

from backend.brain import store
from backend.config import settings
from backend.sources.runtime_config import load_runtime_config
from backend.sources.service import source_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


async def run() -> None:
    await store.init_db()
    last_config_load = 0.0
    last_oss_sync = 0.0
    try:
        while True:
            processed = await source_service.process_pending()
            if processed:
                logger.info("processed %d source event(s)", len(processed))
            now = asyncio.get_running_loop().time()
            if now - last_config_load >= 10.0:
                last_config_load = now
                try:
                    await load_runtime_config()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not refresh operator source configuration: %s", exc)
            if now - last_oss_sync >= settings.ALIBABA_OSS_SYNC_INTERVAL_SECONDS:
                last_oss_sync = now
                try:
                    accepted = await source_service.ingest_oss_documents(org_id=settings.SOURCE_ORG_ID)
                    if accepted:
                        logger.info("accepted %d Alibaba OSS runbook object(s)", len(accepted))
                except RuntimeError as exc:
                    if "not configured" not in str(exc):
                        logger.warning("Alibaba OSS sync unavailable: %s", exc)
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Alibaba OSS sync failed: %s", exc)
            await asyncio.sleep(max(0.5, settings.SOURCE_WORKER_POLL_SECONDS))
    finally:
        await store.close()


if __name__ == "__main__":
    asyncio.run(run())
