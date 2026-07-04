from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.errors import DuplicateKeyError, ServerSelectionTimeoutError

from backend.config import settings
from backend.core.schema import (
    AgentRegistration,
    CompanyBrainSkill,
    InterceptLogEntry,
    InterceptResult,
    RawEvent,
    SessionMemory,
    utc_now,
)

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None

_DECAY_DAYS = {
    "slow": 180,
    "medium": 60,
    "fast": 14,
    "never": None,
}


def get_db() -> AsyncIOMotorDatabase:
    if _db is None:
        raise RuntimeError("Mongo not initialised — call init_db() first")
    return _db


async def init_db(retries: int = 3, delay_sec: float = 2.0) -> AsyncIOMotorDatabase:
    global _client, _db

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            _client = AsyncIOMotorClient(
                settings.MONGODB_URI,
                maxPoolSize=50,
                retryWrites=True,
                serverSelectionTimeoutMS=5000,
            )
            await _client.admin.command("ping")
            _db = _client[settings.MONGODB_DB_NAME]
            await _ensure_indexes(_db)
            logger.info("MongoDB connected (attempt %d)", attempt)
            return _db
        except ServerSelectionTimeoutError as exc:
            last_err = exc
            logger.warning("MongoDB connect attempt %d/%d failed: %s", attempt, retries, exc)
            await asyncio.sleep(delay_sec)

    raise RuntimeError(
        f"Could not connect to MongoDB at {settings.MONGODB_URI} after {retries} attempts: {last_err}"
    )


async def _ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    await db.skills.create_index([("skill_id", ASCENDING), ("org_id", ASCENDING)], unique=True)
    await db.skills.create_index([("is_active", ASCENDING), ("domain", ASCENDING), ("org_id", ASCENDING)])
    await db.skills.create_index([("provenance.confidence", DESCENDING)])
    await db.skills.create_index([("pattern.keywords", TEXT)])
    await db.skills.create_index(
        [("provenance.expires_at", ASCENDING)],
        expireAfterSeconds=0,
        sparse=True,
    )

    await db.events.create_index([("event_id", ASCENDING), ("org_id", ASCENDING)], unique=True)
    await db.events.create_index([("agent_id", ASCENDING), ("occurred_at", DESCENDING)])

    await db.agents.create_index([("agent_id", ASCENDING), ("org_id", ASCENDING)], unique=True)

    await db.sessions.create_index([("session_id", ASCENDING), ("org_id", ASCENDING)], unique=True)
    await db.sessions.create_index([("user_id", ASCENDING), ("last_updated", DESCENDING)])

    await db.intercept_log.create_index([("agent_id", ASCENDING), ("occurred_at", DESCENDING)])

    await db["api_keys"].create_index([("key_id", ASCENDING)], unique=True)
    await db["api_keys"].create_index([("api_key", ASCENDING)], unique=True)
    await db["api_keys"].create_index([("org_id", ASCENDING)])


def _compute_expires_at(decay_rate: str) -> datetime | None:
    days = _DECAY_DAYS.get(decay_rate)
    if days is None:
        return None
    return utc_now() + timedelta(days=days)


def _skill_to_doc(skill: CompanyBrainSkill) -> dict[str, Any]:
    doc = skill.model_dump(mode="python")
    if doc.get("provenance", {}).get("expires_at") is None:
        decay = doc.get("provenance", {}).get("decay_rate", "medium")
        doc["provenance"]["expires_at"] = _compute_expires_at(decay)
    return doc


def _doc_to_skill(doc: dict[str, Any]) -> CompanyBrainSkill:
    doc = dict(doc)
    doc.pop("_id", None)
    return CompanyBrainSkill.model_validate(doc)


async def save_skill(skill: CompanyBrainSkill, org_id: str = "default") -> CompanyBrainSkill:
    db = get_db()
    existing = await db.skills.find_one({"skill_id": skill.skill_id, "org_id": org_id})

    if existing:
        new_version = min(existing.get("version", 1) + 1, 999)
        if new_version >= 999:
            logger.warning("Skill %s version capped at 999", skill.skill_id)
        skill.version = new_version
        skill.created_at = existing.get("created_at", skill.created_at)
    skill.updated_at = utc_now()
    skill.org_id = org_id

    doc = _skill_to_doc(skill)
    await db.skills.replace_one({"skill_id": skill.skill_id, "org_id": org_id}, doc, upsert=True)
    return skill


async def get_skill(skill_id: str, org_id: str = "default") -> CompanyBrainSkill | None:
    db = get_db()
    doc = await db.skills.find_one({"skill_id": skill_id, "org_id": org_id})
    return _doc_to_skill(doc) if doc else None


async def get_all_active_skills(domain: str | None = None, org_id: str = "default") -> list[CompanyBrainSkill]:
    db = get_db()
    query: dict[str, Any] = {"is_active": True, "org_id": org_id}
    if domain:
        query["domain"] = domain
    cursor = db.skills.find(query).sort("provenance.confidence", DESCENDING)
    return [_doc_to_skill(d) async for d in cursor]


async def get_skills_for_brain_prefix(limit: int = 20, org_id: str = "default") -> list[CompanyBrainSkill]:
    db = get_db()
    cursor = (
        db.skills.find({"is_active": True, "org_id": org_id})
        .sort("provenance.confidence", DESCENDING)
        .limit(limit)
    )
    return [_doc_to_skill(d) async for d in cursor]


async def get_skill_count(active_only: bool = True, org_id: str = "default") -> int:
    db = get_db()
    query: dict[str, Any] = {"org_id": org_id}
    if active_only:
        query["is_active"] = True
    return await db.skills.count_documents(query)


async def invalidate_skill(skill_id: str, superseded_by: str | None = None, org_id: str = "default") -> None:
    db = get_db()
    update: dict[str, Any] = {
        "$set": {
            "is_active": False,
            "provenance.invalidated": True,
            "updated_at": utc_now(),
        }
    }
    if superseded_by:
        update["$set"]["provenance.superseded_by"] = superseded_by
    await db.skills.update_one({"skill_id": skill_id, "org_id": org_id}, update)


async def reinforce_skill(skill_id: str, org_id: str = "default") -> CompanyBrainSkill | None:
    """Atomically reinforce a skill's confidence and counter.

    Uses an aggregation-pipeline update so concurrent intercepts on the same
    skill do not race on the read-modify-write path.
    """
    db = get_db()
    now = utc_now()
    await db["skills"].update_one(
        {"skill_id": skill_id, "org_id": org_id},
        [
            {
                "$set": {
                    "provenance.reinforcement_count": {
                        "$add": [{"$ifNull": ["$provenance.reinforcement_count", 0]}, 1]
                    },
                    "provenance.confidence": {
                        "$min": [
                            {
                                "$add": [
                                    {"$ifNull": ["$provenance.confidence", 0.0]},
                                    settings.CONFIDENCE_INCREMENT,
                                ]
                            },
                            1.0,
                        ]
                    },
                    "provenance.last_validated": {"$literal": now},
                    "updated_at": {"$literal": now},
                }
            },
            {
                "$set": {
                    "executable.auto_execute": {
                        "$cond": [
                            {"$gte": ["$provenance.confidence", settings.CONFIDENCE_AUTO_EXECUTE]},
                            True,
                            {"$ifNull": ["$executable.auto_execute", False]},
                        ]
                    }
                }
            },
        ],
    )
    updated = await db.skills.find_one({"skill_id": skill_id, "org_id": org_id})
    return _doc_to_skill(updated) if updated else None


async def save_event(event: RawEvent, skill_compiled: str | None = None, org_id: str = "default") -> None:
    db = get_db()
    doc = event.model_dump(mode="python")
    doc["skill_compiled"] = skill_compiled
    doc["org_id"] = org_id
    try:
        await db.events.insert_one(doc)
    except DuplicateKeyError:
        await db.events.replace_one({"event_id": event.event_id, "org_id": org_id}, doc)


async def get_recent_events(org_id: str = "default", limit: int = 50) -> list[dict[str, Any]]:
    db = get_db()
    cursor = (
        db.events.find({"org_id": org_id})
        .sort("occurred_at", DESCENDING)
        .limit(limit)
    )
    out: list[dict[str, Any]] = []
    async for d in cursor:
        d.pop("_id", None)
        out.append(d)
    return out


async def get_recent_intercepts(org_id: str = "default", limit: int = 50) -> list[dict[str, Any]]:
    db = get_db()
    cursor = (
        db.intercept_log.find({"org_id": org_id})
        .sort("occurred_at", DESCENDING)
        .limit(limit)
    )
    out: list[dict[str, Any]] = []
    async for d in cursor:
        d.pop("_id", None)
        out.append(d)
    return out


async def register_agent(agent_id: str, agent_type: str, org_id: str = "default") -> None:
    db = get_db()
    now = utc_now()
    await db.agents.update_one(
        {"agent_id": agent_id, "org_id": org_id},
        {
            "$set": {
                "agent_id": agent_id,
                "agent_type": agent_type,
                "org_id": org_id,
                "last_seen_at": now,
            },
            "$setOnInsert": {"registered_at": now, "last_brain_version": 0},
        },
        upsert=True,
    )


async def seed_demo_data(org_id: str = "default") -> dict[str, Any]:
    """Idempotent org-scoped demo seed used by the API endpoint.

    Returns a clean result dict; does not backfill embeddings (same as CLI).
    """
    from backend.demo import seed_data

    return await seed_data.seed_for_org(org_id)


async def backfill_embeddings_for_org(org_id: str = "default") -> int:
    """Backfill embeddings for all active skills in an org that lack them."""
    from backend.core import compiler

    return await compiler.backfill_seed_embeddings(org_id=org_id)


async def get_all_agent_ids(org_id: str = "default") -> list[str]:
    db = get_db()
    cursor = db.agents.find({"org_id": org_id}, {"agent_id": 1})
    return [d["agent_id"] async for d in cursor]


async def log_intercept(
    agent_id: str,
    decision_text: str,
    matched_skill: str | None,
    result: InterceptResult,
    confidence: float,
    org_id: str = "default",
    applicability_status: str | None = None,
    suspension_reason: str | None = None,
) -> None:
    db = get_db()
    entry = InterceptLogEntry(
        agent_id=agent_id,
        decision_text=decision_text,
        matched_skill=matched_skill,
        result=result,
        confidence=confidence,
        org_id=org_id,
        applicability_status=applicability_status,
        suspension_reason=suspension_reason,
    )
    await db.intercept_log.insert_one(entry.model_dump(mode="python"))


async def save_session(session: SessionMemory, org_id: str = "default") -> SessionMemory:
    db = get_db()
    session.last_updated = utc_now()
    session.org_id = org_id
    await db.sessions.replace_one(
        {"session_id": session.session_id, "org_id": org_id},
        session.model_dump(mode="python"),
        upsert=True,
    )
    return session


async def get_session(session_id: str, org_id: str = "default") -> SessionMemory | None:
    db = get_db()
    doc = await db.sessions.find_one({"session_id": session_id, "org_id": org_id})
    if not doc:
        return None
    doc.pop("_id", None)
    return SessionMemory.model_validate(doc)


async def get_sessions_for_user(user_id: str, limit: int = 50, org_id: str = "default") -> list[SessionMemory]:
    db = get_db()
    cursor = (
        db.sessions.find({"user_id": user_id, "org_id": org_id})
        .sort("last_updated", DESCENDING)
        .limit(limit)
    )
    out: list[SessionMemory] = []
    async for d in cursor:
        d.pop("_id", None)
        out.append(SessionMemory.model_validate(d))
    return out


async def create_api_key(
    org_id: str,
    name: str,
    permissions: str = "read:skills read:events",
) -> dict[str, Any]:
    db = get_db()
    key_id = uuid.uuid4().hex[:12]
    secret = secrets.token_hex(24)
    api_key = f"cb_live_{secret}"
    doc = {
        "key_id": key_id,
        "name": name,
        "api_key": api_key,
        "org_id": org_id,
        "permissions": permissions,
        "created_at": utc_now(),
        "revoked_at": None,
    }
    await db["api_keys"].insert_one(doc)
    return {
        "key_id": key_id,
        "name": name,
        "api_key": api_key,
        "permissions": permissions,
        "created_at": doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else doc["created_at"],
    }


async def list_api_keys(org_id: str) -> list[dict[str, Any]]:
    db = get_db()
    cursor = db["api_keys"].find({
        "org_id": org_id,
        "revoked_at": None,
    }).sort("created_at", DESCENDING)
    out: list[dict[str, Any]] = []
    async for d in cursor:
        d.pop("_id", None)
        d.pop("api_key", None)
        out.append(d)
    return out


async def revoke_api_key(key_id: str, org_id: str) -> bool:
    db = get_db()
    result = await db["api_keys"].update_one(
        {"key_id": key_id, "org_id": org_id},
        {"$set": {"revoked_at": utc_now()}},
    )
    return result.modified_count > 0


async def db_health() -> dict[str, Any]:
    try:
        db = get_db()
        await db.command("ping")
        return {"connected": True, "db": settings.MONGODB_DB_NAME}
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": str(exc)}


async def close() -> None:
    global _client, _db
    if _client is not None:
        _client.close()
    _client = None
    _db = None
