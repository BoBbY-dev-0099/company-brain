"""Hybrid keyword + semantic interceptor.

Scoring:
  match_score = 0.6 * keyword_score + 0.4 * semantic_score
  match_score is multiplied by the anti-condition penalty (0.3) when
  anti-conditions appear in the decision text.

Decision stages:
  1. RELEVANCE GATE: if match_score < RELEVANCE_FLOOR the skill is not
     relevant enough → CLEAR.
  2. TRUST TIERING: once relevant, use skill.provenance.confidence directly:
     - confidence >= 0.85 and auto_execute → AUTO_EXECUTE
     - confidence >= 0.70                 → BLOCK
     - confidence >= RELEVANCE_FLOOR      → WARN
     - else                               → CLEAR (defensive)

Reinforcement fires on every non-clear hit.
"""

from __future__ import annotations

import logging
import re

import numpy as np

from backend.brain import store
from backend.config import settings
from backend.core.applicability import ApplicabilityStatus, evaluate_applicability
from backend.core.compiler import generate_embedding
from backend.core import propagator
from backend.core.schema import (
    CompanyBrainSkill,
    DecisionCheckRequest,
    DecisionCheckResponse,
    InterceptResult,
    SSEEvent,
    SSEEventType,
    utc_now,
)

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_\-]*")


def _tokens(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def _phrase_hits(text_lower: str, phrases: list[str]) -> int:
    return sum(1 for p in phrases if p and p.lower() in text_lower)


def _keyword_score(skill: CompanyBrainSkill, decision_text: str) -> float:
    text_lower = decision_text.lower()

    kw = skill.pattern.keywords or []
    kw_score = (_phrase_hits(text_lower, kw) / len(kw)) if kw else 0.0

    et = skill.pattern.entity_types or []
    et_score = (_phrase_hits(text_lower, et) / len(et)) if et else 0.0

    cs = skill.pattern.context_signals or []
    cs_score = (_phrase_hits(text_lower, cs) / len(cs)) if cs else 0.0

    return 0.5 * kw_score + 0.3 * et_score + 0.2 * cs_score


def _cosine(a: list[float] | None, b: list[float] | None) -> float:
    if not a or not b:
        return 0.0
    va = np.asarray(a, dtype=np.float32)
    vb = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    sim = float(np.dot(va, vb) / (na * nb))
    return max(0.0, min(1.0, (sim + 1.0) / 2.0))  # rescale [-1,1] -> [0,1]


def _anti_condition_penalty(skill: CompanyBrainSkill, decision_text: str) -> float:
    if not skill.knowledge.anti_conditions:
        return 1.0
    text_lower = decision_text.lower()
    if _phrase_hits(text_lower, skill.knowledge.anti_conditions) > 0:
        return 0.3
    return 1.0


def _classify(skill_confidence: float, auto_execute: bool) -> InterceptResult:
    if skill_confidence < settings.RELEVANCE_FLOOR:
        return InterceptResult.CLEAR
    if skill_confidence < settings.CONFIDENCE_INTERCEPT:
        return InterceptResult.WARN
    if skill_confidence < settings.CONFIDENCE_AUTO_EXECUTE:
        return InterceptResult.BLOCK
    return InterceptResult.AUTO_EXECUTE if auto_execute else InterceptResult.BLOCK


def _sag_condition_keys(skill: CompanyBrainSkill) -> set[str]:
    provenance = skill.provenance
    keys: set[str] = set()
    for cond in list(provenance.applies_if or []) + list(provenance.invalidated_if or []):
        if cond.key:
            keys.add(cond.key)
    return keys


def _sag_metadata_overlap(skill: CompanyBrainSkill, live_context: dict) -> int:
    """Count how many live metadata keys this skill's SAG conditions care about."""
    if not live_context:
        return 0
    return len(_sag_condition_keys(skill) & set(live_context.keys()))


def _pick_top_skill(
    scored: list[tuple[float, float, CompanyBrainSkill]],
    live_context: dict,
) -> tuple[float, float, CompanyBrainSkill]:
    """Prefer skills whose SAG conditions bind live metadata over text-only winners.

    When the request carries live context keys (e.g. export_chunk_size_mb), a
    skill that declares applies_if / invalidated_if on those keys should win
    over a higher text-match skill with empty SAG conditions — otherwise the
    demo flip is shadowed by compiled lookalikes.
    """
    above_floor = [row for row in scored if row[0] >= settings.RELEVANCE_FLOOR]
    pool = above_floor or scored
    if live_context:
        sag_pool = [row for row in pool if _sag_metadata_overlap(row[2], live_context) > 0]
        if sag_pool:
            pool = sag_pool
    return max(pool, key=lambda row: (row[0], _sag_metadata_overlap(row[2], live_context)))


async def check_decision(req: DecisionCheckRequest) -> DecisionCheckResponse:
    skills = await store.get_all_active_skills(domain=req.domain, org_id=req.org_id)
    if not skills:
        return DecisionCheckResponse(
            result=InterceptResult.CLEAR,
            confidence=0.0,
            rationale="brain is empty",
        )

    # Generate the query embedding ONCE; if it fails we degrade to keyword-only.
    query_emb: list[float] | None = None
    if any(s.embedding for s in skills):
        query_emb = await generate_embedding(req.decision_text)

    live_context = getattr(req, "metadata", None) or {}
    scored: list[tuple[float, float, CompanyBrainSkill]] = []
    for skill in skills:
        kw = _keyword_score(skill, req.decision_text)
        sem = _cosine(query_emb, skill.embedding) if query_emb and skill.embedding else 0.0
        final = (0.6 * kw + 0.4 * sem) * _anti_condition_penalty(skill, req.decision_text)
        scored.append((final, sem, skill))

    final, _sem, top_skill = _pick_top_skill(scored, live_context)

    if final < settings.RELEVANCE_FLOOR:
        return DecisionCheckResponse(
            result=InterceptResult.CLEAR,
            confidence=final,
            rationale=f"top match {top_skill.skill_id} below relevance floor (final={final:.2f})",
        )

    skill_conf = top_skill.provenance.confidence
    result = _classify(skill_conf, top_skill.executable.auto_execute)

    if result == InterceptResult.CLEAR:
        return DecisionCheckResponse(
            result=result,
            confidence=skill_conf,
            matched_skill=top_skill,
            rationale=(
                f"top match {top_skill.skill_id} confidence={skill_conf:.2f} "
                f"below relevance threshold {settings.RELEVANCE_FLOOR}"
            ),
        )

    # Semantic Applicability Gate (SAG): deterministic context checks.
    # No LLM calls are made in this path.
    sag_result = evaluate_applicability(top_skill, live_context)
    sag_status = sag_result["status"]
    sag_reason = sag_result["reason"]
    sag_evidence = sag_result["evidence"]
    sag_trace = sag_result.get("trace")
    sag_ms = sag_result.get("evaluated_in_ms")

    async def _integrity(decision: str) -> dict | None:
        try:
            from backend.services import decision_integrity

            return await decision_integrity.attest_decision(
                org_id=req.org_id,
                skill_id=top_skill.skill_id,
                metadata=live_context,
                decision=decision,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("decision integrity attach failed: %s", exc)
            return None

    if sag_status == ApplicabilityStatus.suspended:
        top_skill.provenance.applicability_status = ApplicabilityStatus.suspended
        top_skill.provenance.last_applicability_check_at = utc_now()
        top_skill.provenance.last_invalid_reason = sag_reason
        await store.save_skill(top_skill, org_id=req.org_id)

        integrity = await _integrity("suspended")
        await store.log_intercept(
            agent_id=req.agent_id,
            decision_text=req.decision_text,
            matched_skill=top_skill.skill_id,
            result=InterceptResult.suspended,
            confidence=skill_conf,
            org_id=req.org_id,
            applicability_status=ApplicabilityStatus.suspended.value,
            suspension_reason=sag_reason,
        )

        await propagator.broadcast(
            SSEEvent(
                type=SSEEventType.SKILL_SUSPENDED,
                payload={
                    "skill_id": top_skill.skill_id,
                    "reason": sag_reason,
                    "evidence": sag_evidence,
                    "trace": sag_trace,
                    "integrity": integrity,
                },
            ),
            org_id=req.org_id,
        )

        return DecisionCheckResponse(
            result=InterceptResult.suspended,
            confidence=skill_conf,
            matched_skill=top_skill,
            intercept_message=top_skill.executable.intercept_message,
            recommended_action=top_skill.executable.recommended_action,
            auto_execute=top_skill.executable.auto_execute,
            rationale=(
                f"matched {top_skill.skill_id} | suspended by applicability gate: {sag_reason}"
            ),
            applicability_status=ApplicabilityStatus.suspended.value,
            suspension_reason=sag_reason,
            suspension_evidence=sag_evidence,
            sag_trace=sag_trace,
            sag_evaluated_in_ms=sag_ms,
            integrity=integrity,
        )

    # Reactivate a skill that was previously suspended but is now applicable.
    if top_skill.provenance.applicability_status == ApplicabilityStatus.suspended:
        top_skill.provenance.applicability_status = ApplicabilityStatus.active
        top_skill.provenance.last_invalid_reason = None
        top_skill.provenance.last_applicability_check_at = utc_now()
        top_skill = await store.save_skill(top_skill, org_id=req.org_id)
        await propagator.broadcast(
            SSEEvent(
                type=SSEEventType.SKILL_REINFORCED,
                payload={
                    "skill_id": top_skill.skill_id,
                    "applicability_status": ApplicabilityStatus.active.value,
                },
            ),
            org_id=req.org_id,
        )

    # Reinforce on every non-clear hit.
    reinforced = await store.reinforce_skill(top_skill.skill_id, org_id=req.org_id)
    if reinforced is not None:
        top_skill = reinforced
        skill_conf = top_skill.provenance.confidence

    decision_label = (
        "auto_execute" if result == InterceptResult.AUTO_EXECUTE else "intercepted"
    )
    integrity = await _integrity(decision_label)

    await store.log_intercept(
        agent_id=req.agent_id,
        decision_text=req.decision_text,
        matched_skill=top_skill.skill_id,
        result=result,
        confidence=skill_conf,
        org_id=req.org_id,
        applicability_status=ApplicabilityStatus.active.value,
    )

    return DecisionCheckResponse(
        result=result,
        confidence=skill_conf,
        matched_skill=top_skill,
        intercept_message=top_skill.executable.intercept_message,
        recommended_action=top_skill.executable.recommended_action,
        auto_execute=top_skill.executable.auto_execute,
        rationale=(
            f"matched {top_skill.skill_id} | final_score={final:.2f} | "
            f"skill_conf={skill_conf:.2f}"
        ),
        applicability_status=ApplicabilityStatus.active.value,
        sag_trace=sag_trace,
        sag_evaluated_in_ms=sag_ms,
        integrity=integrity,
    )


async def recall_skills_for_context(context: str, top_k: int = 5, org_id: str = "default") -> list[CompanyBrainSkill]:
    """Used by the recall_skills MCP tool. Pure keyword + cosine ranking, no
    intercept side-effects (no reinforcement, no logging)."""
    skills = await store.get_all_active_skills(org_id=org_id)
    if not skills:
        return []

    query_emb = await generate_embedding(context) if any(s.embedding for s in skills) else None

    scored: list[tuple[float, CompanyBrainSkill]] = []
    for s in skills:
        kw = _keyword_score(s, context)
        sem = _cosine(query_emb, s.embedding) if query_emb and s.embedding else 0.0
        score = (0.6 * kw + 0.4 * sem) * _anti_condition_penalty(s, context)
        if score > 0.0:
            scored.append((score, s))

    scored.sort(key=lambda t: t[0], reverse=True)
    return [s for _, s in scored[:top_k]]
