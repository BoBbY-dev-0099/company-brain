"""Unit tests for the interceptor scoring math.

These tests do NOT hit Mongo or Qwen. They construct CompanyBrainSkill objects
directly and call _keyword_score / _cosine / _classify in isolation.
"""

from __future__ import annotations

from unittest.mock import patch

from backend.config import settings
from backend.core.interceptor import (
    _anti_condition_penalty,
    _classify,
    _cosine,
    _keyword_score,
    check_decision,
)
from backend.core.schema import (
    ApplicabilityCondition,
    ApplicabilityOperator,
    ApplicabilityStatus,
    CompanyBrainSkill,
    DecisionCheckRequest,
    InterceptResult,
    SkillExecutable,
    SkillKnowledge,
    SkillPattern,
    SkillProvenance,
)


def _skill(
    keywords: list[str] | None = None,
    entity_types: list[str] | None = None,
    context_signals: list[str] | None = None,
    anti: list[str] | None = None,
    confidence: float = 0.9,
    auto: bool = False,
    applies_if: list[ApplicabilityCondition] | None = None,
    invalidated_if: list[ApplicabilityCondition] | None = None,
) -> CompanyBrainSkill:
    return CompanyBrainSkill(
        skill_id="test-skill",
        name="Test",
        domain="engineering",
        pattern=SkillPattern(
            keywords=keywords or [],
            entity_types=entity_types or [],
            context_signals=context_signals or [],
        ),
        knowledge=SkillKnowledge(anti_conditions=anti or []),
        executable=SkillExecutable(auto_execute=auto),
        provenance=SkillProvenance(
            confidence=confidence,
            applies_if=applies_if or [],
            invalidated_if=invalidated_if or [],
        ),
    )


def test_keyword_score_full_match():
    s = _skill(keywords=["data export", "timeout"], entity_types=["api_endpoint"], context_signals=["sync_request"])
    score = _keyword_score(s, "We are seeing a data export timeout on the api_endpoint with sync_request")
    # 0.5*1.0 + 0.3*1.0 + 0.2*1.0 = 1.0
    assert score == 1.0


def test_keyword_score_partial():
    s = _skill(keywords=["data export", "timeout"])
    score = _keyword_score(s, "data export issue")  # 1/2 keywords
    assert abs(score - 0.5 * 0.5) < 1e-6  # 0.5 weight, 0.5 hit


def test_keyword_score_zero_lengths_safe():
    s = _skill()  # no patterns at all
    assert _keyword_score(s, "anything") == 0.0


def test_anti_condition_penalty_applied():
    s = _skill(keywords=["export"], anti=["streaming endpoint"])
    pen = _anti_condition_penalty(s, "this is for the streaming endpoint specifically")
    assert pen == 0.3


def test_anti_condition_no_match():
    s = _skill(anti=["streaming endpoint"])
    pen = _anti_condition_penalty(s, "no streaming here")
    assert pen == 1.0


def test_cosine_handles_none_and_zero_vectors():
    assert _cosine(None, [1.0, 2.0]) == 0.0
    assert _cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_cosine_self_is_one_after_rescale():
    v = [0.5, 0.5, 0.5]
    # cos(v,v) = 1; rescaled (1+1)/2 = 1
    assert abs(_cosine(v, v) - 1.0) < 1e-6


def test_classify_thresholds():
    # below relevance floor -> clear
    assert _classify(0.3, False) == InterceptResult.CLEAR
    # relevance floor <= conf < intercept -> warn
    assert _classify(0.5, False) == InterceptResult.WARN
    # intercept <= conf < auto -> block
    assert _classify(0.75, False) == InterceptResult.BLOCK
    # above auto, no auto flag = block
    assert _classify(0.9, False) == InterceptResult.BLOCK
    # above auto with flag = auto_execute
    assert _classify(0.9, True) == InterceptResult.AUTO_EXECUTE


def test_classify_uses_settings_thresholds():
    below_relevance = settings.RELEVANCE_FLOOR - 0.001
    above_relevance = settings.RELEVANCE_FLOOR + 0.001
    just_below_intercept = settings.CONFIDENCE_INTERCEPT - 0.001
    just_above_intercept = settings.CONFIDENCE_INTERCEPT + 0.001
    assert _classify(below_relevance, False) == InterceptResult.CLEAR
    assert _classify(above_relevance, False) == InterceptResult.WARN
    assert _classify(just_below_intercept, False) == InterceptResult.WARN
    assert _classify(just_above_intercept, False) == InterceptResult.BLOCK


async def test_high_confidence_skill_clears_relevance_gate():
    """
    Regression test for the multiplicative-scoring bug found in
    E2E verification. A high-confidence skill (0.94) with a
    realistic, moderate keyword match (not perfect) must still
    trigger a non-clear result once match_score clears the
    relevance floor. Previously this incorrectly returned 'clear'
    because confidence * match_score collapsed below threshold.
    """
    skill = _skill(
        keywords=["data export", "timeout", "chunk",
                   "file size", "csv", "large"],
        entity_types=["api_endpoint"],
        context_signals=["sync_request"],
        confidence=0.94,
        auto=True,
    )
    # Deliberately partial keyword match (2/6) plus entity/signal hits.
    # The combined match_score clears RELEVANCE_FLOOR so trust tiering applies.
    with patch("backend.core.interceptor.store.get_all_active_skills",
               return_value=[skill]), \
         patch("backend.core.interceptor.store.log_intercept"), \
          patch("backend.core.interceptor.store.reinforce_skill",
                return_value=None) as mock_reinforce:
        req = DecisionCheckRequest(
            agent_id="eng-01",
            decision_text=("Increase data export chunk size to improve throughput "
                           "on the api_endpoint during a sync_request"),
            decision_type="pr_review"
        )
        result = await check_decision(req)
        assert result.result != InterceptResult.CLEAR
        assert result.confidence is not None
        mock_reinforce.assert_not_called()


async def test_sag_conditioned_skill_beats_text_only_lookalike():
    """When live metadata keys match a skill's SAG conditions, prefer that skill
    over a higher text-score skill with empty applies_if / invalidated_if.
    """
    sag_skill = _skill(
        keywords=["data export", "timeout", "chunk"],
        entity_types=["api_endpoint"],
        context_signals=["sync_request"],
        confidence=0.94,
        auto=True,
        invalidated_if=[
            ApplicabilityCondition(
                key="export_chunk_size_mb",
                operator=ApplicabilityOperator.lte,
                value=10,
            )
        ],
    )
    sag_skill.skill_id = "data-export-large-file-timeout"

    # Stronger text match, but no SAG conditions — must lose when metadata binds.
    shadow = _skill(
        keywords=["data export", "timeout", "chunk", "sync export", "gateway", "large file"],
        entity_types=["api_endpoint"],
        context_signals=["sync_request"],
        confidence=1.0,
        auto=True,
    )
    shadow.skill_id = "block-sync-export-chunk-size-over-5mb"

    with patch("backend.core.interceptor.store.get_all_active_skills",
               return_value=[shadow, sag_skill]), \
         patch("backend.core.interceptor.store.log_intercept"), \
         patch("backend.core.interceptor.store.save_skill",
               return_value=sag_skill), \
         patch("backend.core.interceptor.store.reinforce_skill",
               return_value=None), \
         patch("backend.core.interceptor.propagator.broadcast"), \
         patch("backend.core.interceptor.generate_embedding",
               return_value=None):
        req = DecisionCheckRequest(
            agent_id="eng-01",
            decision_text=(
                "Increase data export chunk size to improve throughput "
                "on the api_endpoint during a sync_request gateway timeout"
            ),
            decision_type="pr_review",
            metadata={"export_chunk_size_mb": 8},
        )
        result = await check_decision(req)
        assert result.matched_skill is not None
        assert result.matched_skill.skill_id == "data-export-large-file-timeout"
        assert result.result == InterceptResult.suspended


async def test_suspended_skill_does_not_reinforce_or_auto_execute():
    """
    When a matched skill's invalidated_if condition holds, the interceptor
    must return SUSPENDED, persist the provenance status, and skip
    reinforcement / auto-execution.
    """
    skill = _skill(
        keywords=["data export", "timeout", "chunk",
                   "file size", "csv", "large"],
        entity_types=["api_endpoint"],
        context_signals=["sync_request"],
        confidence=0.94,
        auto=True,
        invalidated_if=[
            ApplicabilityCondition(
                key="export_chunk_size_mb",
                operator=ApplicabilityOperator.lte,
                value=10,
            )
        ],
    )
    with patch("backend.core.interceptor.store.get_all_active_skills",
               return_value=[skill]), \
         patch("backend.core.interceptor.store.log_intercept") as mock_log, \
         patch("backend.core.interceptor.store.save_skill",
               return_value=skill) as mock_save, \
         patch("backend.core.interceptor.store.reinforce_skill",
               return_value=None) as mock_reinforce, \
         patch("backend.core.interceptor.propagator.broadcast"):
        req = DecisionCheckRequest(
            agent_id="eng-01",
            decision_text=("Increase data export chunk size to improve throughput "
                           "on the api_endpoint during a sync_request"),
            decision_type="pr_review",
            metadata={"export_chunk_size_mb": 5},
        )
        result = await check_decision(req)
        assert result.result == InterceptResult.suspended
        assert result.applicability_status == ApplicabilityStatus.suspended
        assert result.suspension_reason is not None
        assert "export_chunk_size_mb" in result.suspension_reason
        assert result.suspension_evidence is not None
        mock_save.assert_awaited_once()
        mock_reinforce.assert_not_called()
        mock_log.assert_awaited_once()
