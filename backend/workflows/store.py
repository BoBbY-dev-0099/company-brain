"""Persistence adapters for workflow runs and normalized evidence.

The normal application path uses the already-initialised Motor database.  The
in-memory adapter deliberately remains available for local demos, unit tests,
and API imports before FastAPI's Mongo lifespan has started.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Protocol

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

from backend.brain import store as brain_store
from backend.workflows.models import EvidenceRecord, WorkflowRun


class WorkflowRepository(Protocol):
    async def save_run(self, run: WorkflowRun) -> WorkflowRun: ...

    async def get_run(self, run_id: str, org_id: str) -> WorkflowRun | None: ...

    async def list_runs(self, *, org_id: str, limit: int = 20) -> list[WorkflowRun]: ...

    async def save_sources(self, sources: list[EvidenceRecord]) -> None: ...

    async def list_sources(
        self,
        *,
        org_id: str,
        template_id: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]: ...

    async def purge_expired(self, *, now: datetime | None = None) -> None: ...


class InMemoryWorkflowRepository:
    """Process-local store with the same org isolation as the Mongo adapter."""

    def __init__(self) -> None:
        self._runs: dict[tuple[str, str], WorkflowRun] = {}
        self._sources: dict[tuple[str, str, str], EvidenceRecord] = {}
        self._lock = asyncio.Lock()

    async def save_run(self, run: WorkflowRun) -> WorkflowRun:
        async with self._lock:
            self._runs[(run.org_id, run.run_id)] = run.model_copy(deep=True)
        return run.model_copy(deep=True)

    async def get_run(self, run_id: str, org_id: str) -> WorkflowRun | None:
        async with self._lock:
            run = self._runs.get((org_id, run_id))
            if run and run.expires_at and run.expires_at <= datetime.now(timezone.utc):
                self._runs.pop((org_id, run_id), None)
                return None
            return run.model_copy(deep=True) if run else None

    async def list_runs(self, *, org_id: str, limit: int = 20) -> list[WorkflowRun]:
        async with self._lock:
            values = [
                run.model_copy(deep=True)
                for (run_org, _), run in self._runs.items()
                if run_org == org_id
                and (run.expires_at is None or run.expires_at > datetime.now(timezone.utc))
            ]
        values.sort(key=lambda run: run.updated_at, reverse=True)
        return values[:limit]

    async def save_sources(self, sources: list[EvidenceRecord]) -> None:
        async with self._lock:
            for source in sources:
                self._sources[(source.org_id, source.template_id, source.evidence_id)] = source.model_copy(deep=True)

    async def list_sources(
        self,
        *,
        org_id: str,
        template_id: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        async with self._lock:
            values = [
                source.model_copy(deep=True)
                for (source_org, source_template, _), source in self._sources.items()
                if source_org == org_id
                and (template_id is None or source_template == template_id)
                and (source.expires_at is None or source.expires_at > datetime.now(timezone.utc))
            ]
        values.sort(key=lambda source: source.occurred_at or source.normalized_at, reverse=True)
        return values[:limit]

    async def purge_expired(self, *, now: datetime | None = None) -> None:
        current = now or datetime.now(timezone.utc)
        async with self._lock:
            self._runs = {
                key: run for key, run in self._runs.items()
                if run.expires_at is None or run.expires_at > current
            }
            self._sources = {
                key: source for key, source in self._sources.items()
                if source.expires_at is None or source.expires_at > current
            }


class MongoWorkflowRepository:
    """Motor-backed workflow persistence kept separate from the legacy store."""

    def __init__(self, db: AsyncIOMotorDatabase) -> None:
        self._db = db
        self._indexes_ready = False
        self._index_lock = asyncio.Lock()

    async def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        async with self._index_lock:
            if self._indexes_ready:
                return
            await self._db.workflow_runs.create_index(
                [("run_id", ASCENDING), ("org_id", ASCENDING)], unique=True
            )
            await self._db.workflow_runs.create_index(
                [("org_id", ASCENDING), ("updated_at", DESCENDING)]
            )
            await self._db.workflow_runs.create_index("expires_at", expireAfterSeconds=0)
            await self._db.workflow_sources.create_index(
                [("evidence_id", ASCENDING), ("org_id", ASCENDING), ("template_id", ASCENDING)],
                unique=True,
            )
            await self._db.workflow_sources.create_index(
                [("org_id", ASCENDING), ("occurred_at", DESCENDING)]
            )
            await self._db.workflow_sources.create_index("expires_at", expireAfterSeconds=0)
            self._indexes_ready = True

    async def save_run(self, run: WorkflowRun) -> WorkflowRun:
        await self._ensure_indexes()
        await self._db.workflow_runs.replace_one(
            {"run_id": run.run_id, "org_id": run.org_id},
            run.model_dump(mode="python"),
            upsert=True,
        )
        return run

    async def get_run(self, run_id: str, org_id: str) -> WorkflowRun | None:
        await self._ensure_indexes()
        now = datetime.now(timezone.utc)
        doc = await self._db.workflow_runs.find_one({
            "run_id": run_id,
            "org_id": org_id,
            "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}, {"expires_at": {"$exists": False}}],
        })
        if not doc:
            return None
        doc.pop("_id", None)
        return WorkflowRun.model_validate(doc)

    async def list_runs(self, *, org_id: str, limit: int = 20) -> list[WorkflowRun]:
        await self._ensure_indexes()
        now = datetime.now(timezone.utc)
        cursor = self._db.workflow_runs.find({
            "org_id": org_id,
            "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}, {"expires_at": {"$exists": False}}],
        }).sort("updated_at", DESCENDING).limit(limit)
        output: list[WorkflowRun] = []
        async for doc in cursor:
            doc.pop("_id", None)
            output.append(WorkflowRun.model_validate(doc))
        return output

    async def save_sources(self, sources: list[EvidenceRecord]) -> None:
        if not sources:
            return
        await self._ensure_indexes()
        for source in sources:
            await self._db.workflow_sources.replace_one(
                {
                    "evidence_id": source.evidence_id,
                    "org_id": source.org_id,
                    "template_id": source.template_id,
                },
                source.model_dump(mode="python"),
                upsert=True,
            )

    async def list_sources(
        self,
        *,
        org_id: str,
        template_id: str | None = None,
        limit: int = 50,
    ) -> list[EvidenceRecord]:
        await self._ensure_indexes()
        now = datetime.now(timezone.utc)
        query: dict = {
            "org_id": org_id,
            "$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}, {"expires_at": {"$exists": False}}],
        }
        if template_id:
            query["template_id"] = template_id
        cursor = self._db.workflow_sources.find(query).sort("occurred_at", DESCENDING).limit(limit)
        output: list[EvidenceRecord] = []
        async for doc in cursor:
            doc.pop("_id", None)
            output.append(EvidenceRecord.model_validate(doc))
        return output

    async def purge_expired(self, *, now: datetime | None = None) -> None:
        await self._ensure_indexes()
        current = now or datetime.now(timezone.utc)
        await self._db.workflow_runs.delete_many({"expires_at": {"$lte": current}})
        await self._db.workflow_sources.delete_many({"expires_at": {"$lte": current}})


_fallback_repository = InMemoryWorkflowRepository()


def get_workflow_repository() -> WorkflowRepository:
    """Use Mongo after app startup, otherwise keep tests and local imports usable."""
    try:
        return MongoWorkflowRepository(brain_store.get_db())
    except RuntimeError:
        return _fallback_repository


def get_fallback_repository() -> InMemoryWorkflowRepository:
    """Testing hook; production code should use :func:`get_workflow_repository`."""
    return _fallback_repository
