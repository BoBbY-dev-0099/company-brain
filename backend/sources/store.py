"""Mongo persistence for immutable source events and Reality Memory."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.errors import DuplicateKeyError

from backend.brain import store as brain_store
from backend.core.schema import utc_now
from backend.sources.models import (
    IngestionStage,
    RealityMemory,
    RealityMemoryStatus,
    OperationalNote,
    SourceConnection,
    SourceIngestion,
)


def _clean(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    if doc is None:
        return None
    result = dict(doc)
    result.pop("_id", None)
    return result


class SourceRepository:
    def __init__(self) -> None:
        self._indexes_ready = False

    async def _ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        db = brain_store.get_db()
        await db.source_ingestions.create_index(
            [("org_id", ASCENDING), ("provider", ASCENDING), ("external_id", ASCENDING)],
            unique=True,
            name="unique_source_delivery",
        )
        await db.source_ingestions.create_index("expires_at", expireAfterSeconds=0)
        await db.source_ingestions.create_index(
            [("org_id", ASCENDING), ("stage", ASCENDING), ("received_at", ASCENDING)],
        )
        await db.source_connections.create_index(
            [("org_id", ASCENDING), ("provider", ASCENDING)], unique=True,
        )
        await db.reality_memories.create_index(
            [("org_id", ASCENDING), ("memory_id", ASCENDING)], unique=True,
        )
        await db.reality_memories.create_index(
            [("org_id", ASCENDING), ("claim_key", ASCENDING), ("status", ASCENDING)],
        )
        await db.reality_memories.create_index([("claim", TEXT), ("subject", TEXT)])
        await db.reality_memories.create_index("expires_at", expireAfterSeconds=0)
        await db.operational_notes.create_index(
            [("org_id", ASCENDING), ("note_id", ASCENDING)],
            unique=True,
            name="unique_operational_note",
        )
        await db.operational_notes.create_index(
            [("org_id", ASCENDING), ("updated_at", DESCENDING)],
            name="operational_note_recency",
        )
        self._indexes_ready = True

    async def claim(self, ingestion: SourceIngestion) -> tuple[bool, SourceIngestion]:
        await self._ensure_indexes()
        db = brain_store.get_db()
        try:
            await db.source_ingestions.insert_one(ingestion.model_dump(mode="python"))
            return True, ingestion
        except DuplicateKeyError:
            existing = await self.get_ingestion(
                ingestion.org_id, ingestion.provider.value, ingestion.external_id
            )
            if existing is None:
                raise RuntimeError("source event claim conflicted without a stored event")
            return False, existing

    async def get_ingestion(
        self, org_id: str, provider: str, external_id: str
    ) -> SourceIngestion | None:
        await self._ensure_indexes()
        doc = await brain_store.get_db().source_ingestions.find_one(
            {
                "org_id": org_id,
                "provider": provider,
                "external_id": external_id,
                "$or": [{"expires_at": None}, {"expires_at": {"$gt": utc_now()}}, {"expires_at": {"$exists": False}}],
            }
        )
        clean = _clean(doc)
        return SourceIngestion.model_validate(clean) if clean else None

    async def get_ingestion_by_id(self, org_id: str, ingestion_id: str) -> SourceIngestion | None:
        await self._ensure_indexes()
        doc = await brain_store.get_db().source_ingestions.find_one(
            {
                "org_id": org_id,
                "ingestion_id": ingestion_id,
                "$or": [{"expires_at": None}, {"expires_at": {"$gt": utc_now()}}, {"expires_at": {"$exists": False}}],
            }
        )
        clean = _clean(doc)
        return SourceIngestion.model_validate(clean) if clean else None

    async def list_ingestions(self, org_id: str, limit: int = 50) -> list[SourceIngestion]:
        await self._ensure_indexes()
        cursor = (
            brain_store.get_db().source_ingestions.find(
                {"org_id": org_id, "$or": [{"expires_at": None}, {"expires_at": {"$gt": utc_now()}}, {"expires_at": {"$exists": False}}]}
            )
            .sort("received_at", DESCENDING)
            .limit(max(1, min(limit, 100)))
        )
        output: list[SourceIngestion] = []
        async for doc in cursor:
            output.append(SourceIngestion.model_validate(_clean(doc)))
        return output

    async def get_operational_note(self, org_id: str, note_id: str) -> OperationalNote | None:
        await self._ensure_indexes()
        doc = await brain_store.get_db().operational_notes.find_one(
            {"org_id": org_id, "note_id": note_id}
        )
        clean = _clean(doc)
        return OperationalNote.model_validate(clean) if clean else None

    async def save_operational_note(self, note: OperationalNote) -> OperationalNote:
        """Persist an idempotent note without allowing cross-org replacement."""
        await self._ensure_indexes()
        existing = await self.get_operational_note(note.org_id, note.note_id)
        if existing is not None:
            if (
                existing.agent_id != note.agent_id
                or existing.subject != note.subject
                or existing.scope != note.scope
                or existing.claim != note.claim
                or existing.evidence_refs != note.evidence_refs
            ):
                raise ValueError("Operational note ID already exists with different content.")
            return existing
        try:
            await brain_store.get_db().operational_notes.insert_one(note.model_dump(mode="python"))
        except DuplicateKeyError:
            # Two agents may publish the same id concurrently. Re-read the
            # winner and apply the same content-conflict guard as the fast path.
            existing = await self.get_operational_note(note.org_id, note.note_id)
            if existing is None:
                raise RuntimeError("Operational note claim conflicted without a stored note")
            if (
                existing.agent_id != note.agent_id
                or existing.subject != note.subject
                or existing.scope != note.scope
                or existing.claim != note.claim
                or existing.evidence_refs != note.evidence_refs
            ):
                raise ValueError("Operational note ID already exists with different content.")
            return existing
        return note

    async def list_operational_notes(
        self,
        org_id: str,
        *,
        subject: str | None = None,
        scope: str | None = None,
        limit: int = 20,
    ) -> list[OperationalNote]:
        await self._ensure_indexes()
        query: dict[str, Any] = {"org_id": org_id}
        if subject and subject.strip():
            query["$or"] = [
                {"subject": {"$regex": re.escape(subject.strip()), "$options": "i"}},
                {"claim": {"$regex": re.escape(subject.strip()), "$options": "i"}},
            ]
        if scope and scope.strip():
            query["scope"] = scope.strip()
        cursor = (
            brain_store.get_db().operational_notes.find(query)
            .sort("updated_at", DESCENDING)
            .limit(max(1, min(limit, 100)))
        )
        output: list[OperationalNote] = []
        async for doc in cursor:
            output.append(OperationalNote.model_validate(_clean(doc)))
        return output

    async def pending(self, limit: int = 20) -> list[SourceIngestion]:
        await self._ensure_indexes()
        cursor = (
            brain_store.get_db().source_ingestions.find(
                {"stage": {"$in": [IngestionStage.ACCEPTED.value, IngestionStage.FAILED.value]}}
            )
            .sort("received_at", ASCENDING)
            .limit(max(1, min(limit, 100)))
        )
        output: list[SourceIngestion] = []
        async for doc in cursor:
            output.append(SourceIngestion.model_validate(_clean(doc)))
        return output

    async def update_ingestion(
        self,
        ingestion: SourceIngestion,
        *,
        stage: IngestionStage,
        error: str | None = None,
        **fields: Any,
    ) -> SourceIngestion:
        await self._ensure_indexes()
        now = utc_now()
        update: dict[str, Any] = {"stage": stage.value, "updated_at": now, **fields}
        update["error"] = error[:500] if error else None
        if stage == IngestionStage.FAILED:
            update["attempts"] = ingestion.attempts + 1
        await brain_store.get_db().source_ingestions.update_one(
            {"org_id": ingestion.org_id, "ingestion_id": ingestion.ingestion_id},
            {"$set": update},
        )
        refreshed = await self.get_ingestion_by_id(ingestion.org_id, ingestion.ingestion_id)
        if refreshed is None:
            raise RuntimeError("source event disappeared during update")
        return refreshed

    async def upsert_connection(self, connection: SourceConnection) -> SourceConnection:
        await self._ensure_indexes()
        await brain_store.get_db().source_connections.replace_one(
            {"org_id": connection.org_id, "provider": connection.provider.value},
            connection.model_dump(mode="python"),
            upsert=True,
        )
        return connection

    async def stored_connections(self, org_id: str) -> dict[str, SourceConnection]:
        await self._ensure_indexes()
        cursor = brain_store.get_db().source_connections.find({"org_id": org_id})
        result: dict[str, SourceConnection] = {}
        async for doc in cursor:
            connection = SourceConnection.model_validate(_clean(doc))
            result[connection.provider.value] = connection
        return result

    async def reconcile_memory(self, memory: RealityMemory) -> RealityMemory:
        """Keep old claims auditable while making conflicting current claims explicit."""
        await self._ensure_indexes()
        db = brain_store.get_db()
        active_docs = await db.reality_memories.find(
            {
                "org_id": memory.org_id,
                "claim_key": memory.claim_key,
                "status": RealityMemoryStatus.ACTIVE.value,
            }
        ).to_list(length=20)
        active = [RealityMemory.model_validate(_clean(doc)) for doc in active_docs]

        # Replaying the same source-backed claim only adds provenance. It does
        # not create a new memory version or erase historical source links.
        same = next((item for item in active if item.claim.strip() == memory.claim.strip()), None)
        if same is not None:
            sources = list(dict.fromkeys([*same.source_ingestion_ids, *memory.source_ingestion_ids]))
            evidence = list(dict.fromkeys([*same.source_evidence_ids, *memory.source_evidence_ids]))
            await db.reality_memories.update_one(
                {"org_id": memory.org_id, "memory_id": same.memory_id},
                {"$set": {"source_ingestion_ids": sources, "source_evidence_ids": evidence, "updated_at": utc_now()}},
            )
            refreshed = await self.get_memory(memory.org_id, same.memory_id)
            if refreshed is None:
                raise RuntimeError("memory disappeared during reconciliation")
            return refreshed

        memory.supersedes = [item.memory_id for item in active]
        for prior in active:
            await db.reality_memories.update_one(
                {"org_id": memory.org_id, "memory_id": prior.memory_id},
                {
                    "$set": {
                        "status": RealityMemoryStatus.SUPERSEDED.value,
                        "superseded_by": memory.memory_id,
                        "valid_until": utc_now(),
                        "updated_at": utc_now(),
                    }
                },
            )
        await db.reality_memories.insert_one(memory.model_dump(mode="python"))
        return memory

    async def get_memory(self, org_id: str, memory_id: str) -> RealityMemory | None:
        await self._ensure_indexes()
        doc = await brain_store.get_db().reality_memories.find_one(
            {
                "org_id": org_id,
                "memory_id": memory_id,
                "$or": [{"expires_at": None}, {"expires_at": {"$gt": utc_now()}}, {"expires_at": {"$exists": False}}],
            }
        )
        clean = _clean(doc)
        return RealityMemory.model_validate(clean) if clean else None

    async def list_memories(
        self,
        org_id: str,
        *,
        query: str | None = None,
        include_superseded: bool = False,
        limit: int = 20,
    ) -> list[RealityMemory]:
        await self._ensure_indexes()
        filters: dict[str, Any] = {
            "org_id": org_id,
            "$and": [{"$or": [{"expires_at": None}, {"expires_at": {"$gt": utc_now()}}, {"expires_at": {"$exists": False}}]}],
        }
        if not include_superseded:
            filters["status"] = {"$ne": RealityMemoryStatus.SUPERSEDED.value}
        if query and query.strip():
            filters["$or"] = [
                {"claim": {"$regex": re.escape(query.strip()), "$options": "i"}},
                {"subject": {"$regex": re.escape(query.strip()), "$options": "i"}},
                {"scope": {"$regex": re.escape(query.strip()), "$options": "i"}},
            ]
        cursor = (
            brain_store.get_db().reality_memories.find(filters)
            .sort("updated_at", DESCENDING)
            .limit(max(1, min(limit, 100)))
        )
        output: list[RealityMemory] = []
        async for doc in cursor:
            output.append(RealityMemory.model_validate(_clean(doc)))
        return output


_repository = SourceRepository()


def get_source_repository() -> SourceRepository:
    return _repository
