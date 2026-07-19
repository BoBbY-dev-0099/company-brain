from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING, TEXT
from pymongo.errors import DuplicateKeyError, OperationFailure, ServerSelectionTimeoutError

from backend.config import settings
from backend.core.schema import (
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
    await db.events.create_index([("org_id", ASCENDING), ("ingestion_status", ASCENDING)])

    await db.sessions.create_index([("session_id", ASCENDING), ("org_id", ASCENDING)], unique=True)
    await db.sessions.create_index([("user_id", ASCENDING), ("last_updated", DESCENDING)])

    await db.intercept_log.create_index([("agent_id", ASCENDING), ("occurred_at", DESCENDING)])
    await db.intercept_log.create_index([("org_id", ASCENDING), ("occurred_at", DESCENDING)])

    await db["api_keys"].create_index([("key_id", ASCENDING)], unique=True)
    await db["api_keys"].create_index([("api_key", ASCENDING)], unique=True)
    await db["api_keys"].create_index([("org_id", ASCENDING)])
    await db["api_keys"].create_index("expires_at", expireAfterSeconds=0)

    await db.tdx_quotes.create_index([("org_id", ASCENDING), ("created_at", DESCENDING)])
    await db.tdx_quotes.create_index([("skill_id", ASCENDING), ("created_at", DESCENDING)])
    await db.audit_log.create_index([("org_id", ASCENDING), ("skill_id", ASCENDING), ("created_at", DESCENDING)])
    await db.skill_outcomes.create_index([("outcome_id", ASCENDING)], unique=True)
    await db.skill_outcomes.create_index([("org_id", ASCENDING), ("skill_id", ASCENDING), ("created_at", DESCENDING)])
    # Migrate the former sparse compound index. A compound sparse index still
    # indexes a document when ``org_id`` exists but ``source_run_id`` does not,
    # effectively allowing only one manual (no-run) outcome per org.
    try:
        await db.skill_outcomes.drop_index("org_id_1_source_run_id_1")
    except OperationFailure as exc:
        if exc.code != 27:  # IndexNotFound
            raise
    await db.skill_outcomes.create_index(
        [("org_id", ASCENDING), ("source_run_id", ASCENDING)],
        name="unique_source_run_per_org",
        unique=True,
        partialFilterExpression={"source_run_id": {"$type": "string"}},
    )


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
    # A compiled or manually seeded skill is never eligible to auto-execute
    # until its provenance contains at least one explicit human confirmation.
    # This also safely downgrades older documents that predate the field.
    if skill.provenance.human_confirmed_outcome_count < 1:
        skill.executable.auto_execute = False

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


async def _apply_human_confirmed_reinforcement(
    skill_id: str,
    org_id: str,
) -> CompanyBrainSkill | None:
    """Apply one already-persisted human confirmation atomically."""
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
                    "provenance.human_confirmed_outcome_count": {
                        "$add": [
                            {"$ifNull": ["$provenance.human_confirmed_outcome_count", 0]},
                            1,
                        ]
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
                        "$and": [
                            {"$gte": ["$provenance.confidence", settings.CONFIDENCE_AUTO_EXECUTE]},
                            {"$gte": ["$provenance.human_confirmed_outcome_count", 1]},
                            {"$eq": ["$is_active", True]},
                        ]
                    }
                }
            },
        ],
    )
    updated = await db.skills.find_one({"skill_id": skill_id, "org_id": org_id})
    return _doc_to_skill(updated) if updated else None


async def reinforce_skill(
    skill_id: str,
    org_id: str = "default",
    *,
    human_confirmed: bool = False,
    confirmation_id: str | None = None,
) -> CompanyBrainSkill | None:
    """Compatibility wrapper that rejects observation-only reinforcement.

    Use :func:`record_human_outcome` from an outcome route.  The explicit
    arguments make it hard for a future interceptor or demo click to raise
    confidence by accident.
    """
    if not human_confirmed or not confirmation_id:
        raise ValueError(
            "reinforcement requires a persisted human-confirmed outcome and confirmation_id"
        )
    return await _apply_human_confirmed_reinforcement(skill_id, org_id)


async def save_event(event: RawEvent, skill_compiled: str | None = None, org_id: str = "default") -> None:
    db = get_db()
    doc = event.model_dump(mode="python")
    doc["skill_compiled"] = skill_compiled
    doc["org_id"] = org_id
    try:
        await db.events.insert_one(doc)
    except DuplicateKeyError:
        await db.events.replace_one({"event_id": event.event_id, "org_id": org_id}, doc)


async def get_event(event_id: str, org_id: str = "default") -> dict[str, Any] | None:
    """Fetch one normalized raw event, including its ingestion state."""
    db = get_db()
    doc = await db.events.find_one({"event_id": event_id, "org_id": org_id})
    if doc is None:
        return None
    doc.pop("_id", None)
    return doc


async def claim_event(event: RawEvent, org_id: str = "default") -> tuple[bool, dict[str, Any]]:
    """Durably claim an inbound event before compiling it.

    The unique event index makes GitHub delivery retries idempotent.  A caller
    that did not claim the event receives the persisted record and can either
    return its completed result or resume a failed processing stage.
    """
    db = get_db()
    now = utc_now()
    doc = event.model_dump(mode="python")
    doc.update(
        {
            "org_id": org_id,
            "skill_compiled": None,
            "ingestion_status": "received",
            "ingestion_received_at": now,
            "ingestion_updated_at": now,
        }
    )
    try:
        await db.events.insert_one(doc)
        return True, doc
    except DuplicateKeyError:
        existing = await get_event(event.event_id, org_id=org_id)
        if existing is None:  # defensive: a concurrent delete after duplicate
            raise RuntimeError("event claim conflicted but persisted event was unavailable")
        return False, existing


async def update_event_ingestion(
    event_id: str,
    org_id: str,
    status: str,
    *,
    skill_compiled: str | None = None,
    audit_id: str | None = None,
    workflow_run_id: str | None = None,
    workflow_status: str | None = None,
    error: str | None = None,
) -> dict[str, Any] | None:
    """Advance an event's durable intake state without replacing raw evidence."""
    db = get_db()
    update: dict[str, Any] = {
        "ingestion_status": status,
        "ingestion_updated_at": utc_now(),
    }
    if skill_compiled is not None:
        update["skill_compiled"] = skill_compiled
    if audit_id is not None:
        update["audit_id"] = audit_id
    if workflow_run_id is not None:
        update["workflow_run_id"] = workflow_run_id
    if workflow_status is not None:
        update["workflow_status"] = workflow_status
    if error is not None:
        update["ingestion_error"] = error[:500]
    else:
        update["ingestion_error"] = None
    await db.events.update_one(
        {"event_id": event_id, "org_id": org_id},
        {"$set": update},
    )
    return await get_event(event_id, org_id=org_id)


_HUMAN_OUTCOME_STATES = frozenset({"confirmed_effective", "rejected", "needs_review"})


def _outcome_public(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    if "_id" in out:
        out["outcome_id"] = str(out.pop("_id"))
    return out


async def record_human_outcome(
    skill_id: str,
    org_id: str,
    outcome: str,
    confirmed_by: str,
    *,
    note: str = "",
    source_run_id: str | None = None,
) -> dict[str, Any]:
    """Persist a human outcome and reinforce only a confirmed-effective skill.

    ``confirmed_effective`` is the sole outcome allowed to change confidence or
    auto-execute eligibility.  ``rejected`` and ``needs_review`` remain useful
    auditable outcomes, but do not change the skill.  ``source_run_id`` makes a
    workflow outcome retry idempotent when supplied.
    """
    normalized_outcome = outcome.strip().lower()
    if normalized_outcome not in _HUMAN_OUTCOME_STATES:
        allowed = ", ".join(sorted(_HUMAN_OUTCOME_STATES))
        raise ValueError(f"outcome must be one of: {allowed}")
    if not confirmed_by or not confirmed_by.strip():
        raise ValueError("confirmed_by is required for a human outcome")

    db = get_db()
    if source_run_id:
        existing = await db.skill_outcomes.find_one(
            {"org_id": org_id, "source_run_id": source_run_id}
        )
        if existing is not None:
            existing_skill = await get_skill(skill_id, org_id=org_id)
            return {
                "record": _outcome_public(existing),
                "skill": existing_skill,
                "reinforced": bool(existing.get("reinforcement_applied", False)),
            }

    skill = await get_skill(skill_id, org_id=org_id)
    if skill is None:
        return {"record": None, "skill": None, "reinforced": False}

    now = utc_now()
    record = {
        "outcome_id": uuid.uuid4().hex,
        "org_id": org_id,
        "skill_id": skill_id,
        "outcome": normalized_outcome,
        "confirmed_by": confirmed_by.strip(),
        "note": note.strip()[:2_000],
        "created_at": now,
        "reinforcement_applied": False,
    }
    # Omit absent run IDs so the sparse unique index does not treat every
    # manual outcome as the same null value.
    if source_run_id:
        record["source_run_id"] = source_run_id
    try:
        await db.skill_outcomes.insert_one(record)
    except DuplicateKeyError:
        # A concurrent retry with the same workflow run has already become the
        # source of truth.  Never double-increment confidence for that retry.
        if source_run_id:
            existing = await db.skill_outcomes.find_one(
                {"org_id": org_id, "source_run_id": source_run_id}
            )
            if existing is not None:
                return {
                    "record": _outcome_public(existing),
                    "skill": await get_skill(skill_id, org_id=org_id),
                    "reinforced": bool(existing.get("reinforcement_applied", False)),
                }
        raise

    if normalized_outcome != "confirmed_effective":
        return {"record": record, "skill": skill, "reinforced": False}

    try:
        updated_skill = await _apply_human_confirmed_reinforcement(skill_id, org_id)
        if updated_skill is None:
            raise RuntimeError(f"skill {skill_id} disappeared before reinforcement")
        await db.skill_outcomes.update_one(
            {"outcome_id": record["outcome_id"]},
            {"$set": {"reinforcement_applied": True, "reinforced_at": utc_now()}},
        )
        record["reinforcement_applied"] = True
        return {"record": record, "skill": updated_skill, "reinforced": True}
    except Exception as exc:
        await db.skill_outcomes.update_one(
            {"outcome_id": record["outcome_id"]},
            {"$set": {"reinforcement_error": str(exc)[:500]}},
        )
        raise


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


_DEFAULT_LIVE_METADATA: dict[str, Any] = {"export_chunk_size_mb": 25}


async def get_live_config(org_id: str = "default") -> dict[str, Any]:
    """Return org live metadata (demo system state). Creates default if missing."""
    db = get_db()
    doc = await db.org_configs.find_one({"org_id": org_id})
    if not doc:
        now = utc_now()
        metadata = dict(_DEFAULT_LIVE_METADATA)
        await db.org_configs.insert_one({
            "org_id": org_id,
            "metadata": metadata,
            "updated_at": now,
            "created_at": now,
        })
        return {"org_id": org_id, "metadata": metadata, "updated_at": now}
    return {
        "org_id": org_id,
        "metadata": dict(doc.get("metadata") or _DEFAULT_LIVE_METADATA),
        "updated_at": doc.get("updated_at"),
    }


async def set_live_config(org_id: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Merge metadata into org live config and return the full document view."""
    db = get_db()
    now = utc_now()
    existing = await get_live_config(org_id)
    merged = {**(existing.get("metadata") or {}), **metadata}
    await db.org_configs.update_one(
        {"org_id": org_id},
        {
            "$set": {"metadata": merged, "updated_at": now, "org_id": org_id},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    return {"org_id": org_id, "metadata": merged, "updated_at": now}


async def horror_intercept_exists(org_id: str) -> bool:
    db = get_db()
    doc = await db.intercept_log.find_one({
        "org_id": org_id,
        "matched_skill": "data-export-large-file-timeout",
        "result": "suspended",
        "decision_text": {"$regex": "horror-story", "$options": "i"},
    })
    return doc is not None


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


async def get_intercept_stats(org_id: str = "default") -> dict[str, Any]:
    """Aggregate intercept counts by result for efficiency / governance metrics."""
    db = get_db()
    pipeline = [
        {"$match": {"org_id": org_id}},
        {"$group": {"_id": "$result", "count": {"$sum": 1}}},
    ]
    by_result: dict[str, int] = {}
    async for row in db.intercept_log.aggregate(pipeline):
        key = row.get("_id") or "unknown"
        by_result[str(key)] = int(row.get("count", 0))

    total = sum(by_result.values())
    governance_hits = sum(
        by_result.get(k, 0)
        for k in ("block", "warn", "auto_execute", "suspended")
    )
    # This is deliberately a labelled estimate, not observed provider usage.
    # A real deployment may have a materially different token profile.
    est_tokens_saved = governance_hits * 2000

    return {
        "total_intercepts": total,
        "by_result": by_result,
        "governance_hits": governance_hits,
        "est_llm_tokens_saved": est_tokens_saved,
        "est_llm_tokens_saved_is_estimate": True,
        "est_llm_tokens_saved_assumption": (
            "governance_hits multiplied by 2,000 tokens; not measured provider usage"
        ),
    }


async def seed_demo_data(org_id: str = "default") -> dict[str, Any]:
    """Idempotent org-scoped demo seed used by the API endpoint.

    Returns a clean result dict. Callers should backfill embeddings after seed.
    """
    from backend.demo import seed_data

    return await seed_data.seed_for_org(org_id)


async def backfill_embeddings_for_org(org_id: str = "default") -> int:
    """Backfill embeddings for all active skills in an org that lack them."""
    from backend.core import compiler

    return await compiler.backfill_seed_embeddings(org_id=org_id)


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
    expires_at: datetime | None = None,
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
        "expires_at": expires_at,
    }
    await db["api_keys"].insert_one(doc)
    return {
        "key_id": key_id,
        "name": name,
        "api_key": api_key,
        "permissions": permissions,
        "created_at": doc["created_at"].isoformat() if isinstance(doc["created_at"], datetime) else doc["created_at"],
        "expires_at": expires_at.isoformat() if isinstance(expires_at, datetime) else None,
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


async def save_tdx_quote(doc: dict[str, Any]) -> str:
    db = get_db()
    result = await db.tdx_quotes.insert_one(doc)
    return str(result.inserted_id)


async def get_tdx_quote(quote_id: str, org_id: str | None = None) -> dict[str, Any] | None:
    from bson import ObjectId

    db = get_db()
    query: dict[str, Any] = {"_id": ObjectId(quote_id)}
    if org_id:
        query["org_id"] = org_id
    doc = await db.tdx_quotes.find_one(query)
    if not doc:
        return None
    doc["quote_id"] = str(doc.pop("_id"))
    return doc


async def save_audit_log(doc: dict[str, Any]) -> str:
    db = get_db()
    result = await db.audit_log.insert_one(doc)
    return str(result.inserted_id)


async def list_audit_chain(skill_id: str, org_id: str, limit: int = 50) -> list[dict[str, Any]]:
    db = get_db()
    cursor = (
        db.audit_log.find({"skill_id": skill_id, "org_id": org_id})
        .sort("created_at", DESCENDING)
        .limit(limit)
    )
    out: list[dict[str, Any]] = []
    async for d in cursor:
        d["audit_id"] = str(d.pop("_id"))
        out.append(d)
    return out


async def upsert_public_audit_key(org_id: str, fingerprint: str, pem: str) -> None:
    db = get_db()
    await db.config.update_one(
        {"org_id": org_id, "key": "audit_public_key"},
        {
            "$set": {
                "org_id": org_id,
                "key": "audit_public_key",
                "fingerprint": fingerprint,
                "pem": pem,
                "updated_at": utc_now(),
            }
        },
        upsert=True,
    )


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
