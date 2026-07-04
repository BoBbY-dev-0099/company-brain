"""Qwen-powered compiler: raw event -> CompanyBrainSkill.

DashScope international compatible-mode notes:
- Endpoint accepts OpenAI-format chat completions; we use openai.AsyncOpenAI.
- Structured output: only `response_format={"type": "json_object"}` is supported.
  Strict json_schema is not. Pydantic validates instead; we retry once on failure.
- Caching: Qwen has automatic Context Cache on stable >1024-token system prefixes.
  No `cache_control` marker is needed (and it would be ignored).
- Thinking: Qwen 3 hybrid models default thinking ON. Disable via
  `extra_body={"enable_thinking": False}` on every call.
- Embeddings: text-embedding-v3 returns 1024-dim by default; pass `dimensions`
  to request a different size.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from backend.brain import store
from backend.config import settings
from backend.core.brain_cache import build_frozen_prefix
from backend.core.schema import (
    CompanyBrainSkill,
    DecayRate,
    RawEvent,
    SkillExecutable,
    SkillKnowledge,
    SkillPattern,
    SkillProvenance,
    utc_now,
)

logger = logging.getLogger(__name__)


SKILL_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "skill_id": {"type": "string"},
        "name": {"type": "string"},
        "domain": {"type": "string"},
        "summary": {"type": "string"},
        "pattern": {
            "type": "object",
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"}},
                "entity_types": {"type": "array", "items": {"type": "string"}},
                "context_signals": {"type": "array", "items": {"type": "string"}},
                "domains": {"type": "array", "items": {"type": "string"}},
            },
        },
        "knowledge": {
            "type": "object",
            "properties": {
                "what_happened": {"type": "string"},
                "failure_mode": {"type": "string"},
                "what_worked": {"type": "string"},
                "conditions": {"type": "array", "items": {"type": "string"}},
                "anti_conditions": {"type": "array", "items": {"type": "string"}},
            },
        },
        "executable": {
            "type": "object",
            "properties": {
                "intercept_message": {"type": "string"},
                "recommended_action": {"type": "string"},
                "avoid_actions": {"type": "array", "items": {"type": "string"}},
                "escalate_if": {"type": "array", "items": {"type": "string"}},
            },
        },
        "decay_rate": {"type": "string", "enum": ["slow", "medium", "fast", "never"]},
    },
    "required": ["name"],
}

def _client() -> AsyncOpenAI:
    if not settings.QWEN_API_KEY:
        raise RuntimeError("QWEN_API_KEY missing — compiler cannot run")
    return AsyncOpenAI(api_key=settings.QWEN_API_KEY, base_url=settings.QWEN_BASE_URL)


def _embedding_client() -> AsyncOpenAI:
    """Separate client for embeddings; endpoint may differ from chat completions."""
    if not settings.QWEN_API_KEY:
        raise RuntimeError("QWEN_API_KEY missing — embeddings cannot run")
    return AsyncOpenAI(
        api_key=settings.QWEN_API_KEY,
        base_url=settings.QWEN_EMBEDDING_BASE_URL,
    )


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _slugify(name: str, max_len: int = 64) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:max_len] or "untitled-skill"


def _coerce_to_skill(parsed: dict[str, Any], event: RawEvent) -> CompanyBrainSkill:
    """Turn the model's parsed JSON dict into a validated CompanyBrainSkill.

    The model owns: skill_id, name, domain, summary, pattern, knowledge,
    executable (minus auto_execute), decay_rate.
    The system owns: confidence (always 0.60), auto_execute (always False),
    reinforcement_count, version, embedding, provenance.source_event_id.
    """
    skill_id = _slugify(parsed.get("skill_id") or parsed.get("name") or "")
    if not skill_id:
        raise ValueError("compiler returned no skill_id or name")

    pattern_raw = parsed.get("pattern") or {}
    knowledge_raw = parsed.get("knowledge") or {}
    executable_raw = parsed.get("executable") or {}

    decay_str = (parsed.get("decay_rate") or "medium").lower()
    try:
        decay = DecayRate(decay_str)
    except ValueError:
        decay = DecayRate.MEDIUM

    return CompanyBrainSkill(
        skill_id=skill_id,
        name=str(parsed.get("name", skill_id))[:80],
        version=1,
        domain=str(parsed.get("domain", "general")),
        summary=str(parsed.get("summary", ""))[:300],
        pattern=SkillPattern(
            keywords=[str(k).lower() for k in pattern_raw.get("keywords", [])][:8],
            entity_types=[str(k) for k in pattern_raw.get("entity_types", [])][:4],
            context_signals=[str(k) for k in pattern_raw.get("context_signals", [])][:4],
            domains=[str(k) for k in pattern_raw.get("domains", [])] or [str(parsed.get("domain", "general"))],
        ),
        knowledge=SkillKnowledge(
            what_happened=str(knowledge_raw.get("what_happened", "")),
            failure_mode=str(knowledge_raw.get("failure_mode", "")),
            what_worked=str(knowledge_raw.get("what_worked", "")),
            conditions=[str(k) for k in knowledge_raw.get("conditions", [])],
            anti_conditions=[str(k) for k in knowledge_raw.get("anti_conditions", [])],
        ),
        executable=SkillExecutable(
            intercept_message=str(executable_raw.get("intercept_message", "")),
            recommended_action=str(executable_raw.get("recommended_action", "")),
            avoid_actions=[str(k) for k in executable_raw.get("avoid_actions", [])],
            auto_execute=False,
            escalate_if=[str(k) for k in executable_raw.get("escalate_if", [])],
        ),
        provenance=SkillProvenance(
            source_event_id=event.event_id,
            compiled_at=utc_now(),
            confidence=settings.INITIAL_CONFIDENCE,
            reinforcement_count=0,
            last_validated=utc_now(),
            decay_rate=decay,
        ),
        user_id=event.user_id,
        org_id=event.org_id,
    )


def _user_prompt_for_event(event: RawEvent) -> str:
    return (
        "Compile the following raw event into one skill. Output VALID JSON only.\n\n"
        f"event_id: {event.event_id}\n"
        f"agent_id: {event.agent_id}\n"
        f"event_type: {event.event_type}\n"
        f"outcome: {event.outcome or '(not specified)'}\n"
        f"metadata: {json.dumps(event.metadata, default=str)[:1500]}\n\n"
        f"content:\n{event.content}\n"
    )


async def _call_qwen_json(system_prefix: str, user_prompt: str) -> dict[str, Any]:
    client = _client()
    resp = await client.chat.completions.create(
        model=settings.QWEN_COMPILER_MODEL,
        messages=[
            {"role": "system", "content": system_prefix},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
        "type": "json_schema",
        "json_schema": {
            "name": "company_brain_skill",
            "description": "A typed executable skill compiled from an organizational event",
            "schema": SKILL_JSON_SCHEMA,
            "strict": True,
        },
    },
        temperature=0.2,
        extra_body={"enable_thinking": False},
    )
    raw = resp.choices[0].message.content or ""
    return json.loads(_strip_fences(raw))


async def compile_event_to_skill(event: RawEvent) -> CompanyBrainSkill:
    existing = await store.get_skills_for_brain_prefix()
    system_prefix = build_frozen_prefix(existing)
    user_prompt = _user_prompt_for_event(event)

    parsed: dict[str, Any] | None = None
    last_err: Exception | None = None
    for attempt in (1, 2):
        try:
            parsed = await _call_qwen_json(system_prefix, user_prompt)
            break
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            last_err = exc
            logger.warning("compile attempt %d failed: %s", attempt, exc)

    if parsed is None:
        raise RuntimeError(f"compile_event_to_skill failed after retries: {last_err}")

    skill = _coerce_to_skill(parsed, event)

    embedding_text = _skill_embedding_text(skill)
    skill.embedding = await generate_embedding(embedding_text)

    return skill


def _skill_embedding_text(skill: CompanyBrainSkill) -> str:
    parts = [
        skill.name,
        skill.summary,
        " ".join(skill.pattern.keywords),
        " ".join(skill.pattern.entity_types),
        skill.knowledge.failure_mode,
        skill.knowledge.what_worked,
        skill.executable.intercept_message,
    ]
    return " | ".join(p for p in parts if p)


async def generate_embedding(text: str) -> list[float] | None:
    if not text:
        return None
    if not settings.QWEN_API_KEY:
        logger.warning("QWEN_API_KEY missing — skipping embedding")
        return None
    try:
        client = _embedding_client()
        resp = await client.embeddings.create(
            model=settings.QWEN_EMBEDDING_MODEL,
            input=text[:8000],
            dimensions=settings.EMBEDDING_DIMENSIONS,
            encoding_format="float",
        )
        return list(resp.data[0].embedding)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embedding generation failed: %s", exc)
        return None


async def backfill_seed_embeddings(org_id: str = "default") -> int:
    """Fill embeddings for any seeded skills in the given org that don't have them yet."""
    skills = await store.get_all_active_skills(org_id=org_id)
    filled = 0
    for s in skills:
        if s.embedding:
            continue
        emb = await generate_embedding(_skill_embedding_text(s))
        if emb is None:
            continue
        s.embedding = emb
        # Save without bumping version on a pure-embedding fill: do a direct field update.
        db = store.get_db()
        await db.skills.update_one(
            {"skill_id": s.skill_id, "org_id": org_id},
            {"$set": {"embedding": emb, "updated_at": utc_now()}},
        )
        filled += 1
        await asyncio.sleep(0)  # cooperative yield
    return filled

async def check_embedding_health() -> dict:
    """
    Verify the embedding endpoint is reachable and returns the right dimensions.
    Returns {"healthy": bool, "dimensions": int|None, "error": str|None}
    """
    try:
        result = await generate_embedding("health check test")
        if result is None:
            return {"healthy": False, "dimensions": None,
                    "error": "embedding returned None"}
        return {"healthy": True, "dimensions": len(result), "error": None}
    except Exception as e:
        return {"healthy": False, "dimensions": None, "error": str(e)}

