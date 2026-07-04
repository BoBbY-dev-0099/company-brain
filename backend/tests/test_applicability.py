"""Tests for backend.core.applicability.evaluate_applicability."""

from __future__ import annotations

from backend.core.applicability import evaluate_applicability
from backend.core.schema import (
    ApplicabilityCondition,
    ApplicabilityOperator,
    ApplicabilityStatus,
    CompanyBrainSkill,
    SkillProvenance,
)


def _skill(
    applies_if: list[ApplicabilityCondition] | None = None,
    invalidated_if: list[ApplicabilityCondition] | None = None,
) -> CompanyBrainSkill:
    return CompanyBrainSkill(
        skill_id="test-skill",
        name="Test Skill",
        provenance=SkillProvenance(
            applies_if=applies_if or [],
            invalidated_if=invalidated_if or [],
        ),
    )


def test_no_conditions_returns_active():
    skill = _skill()
    result = evaluate_applicability(skill, {})

    assert result["status"] == ApplicabilityStatus.active
    assert result["reason"] is None
    assert result["evidence"]["skill_id"] == skill.skill_id
    assert isinstance(result["evidence"]["checked_at"], str)


def test_applies_if_satisfied_returns_active():
    skill = _skill(
        applies_if=[
            ApplicabilityCondition(
                key="priority", operator=ApplicabilityOperator.gt, value=5
            )
        ]
    )
    result = evaluate_applicability(skill, {"priority": 7})

    assert result["status"] == ApplicabilityStatus.active
    assert result["reason"] is None


def test_applies_if_failed_returns_suspended():
    skill = _skill(
        applies_if=[
            ApplicabilityCondition(
                key="priority", operator=ApplicabilityOperator.gt, value=5
            )
        ]
    )
    result = evaluate_applicability(skill, {"priority": 3})

    assert result["status"] == ApplicabilityStatus.suspended
    assert "applies_if conditions failed" in result["reason"]
    assert "priority" in result["reason"]
    failed = result["evidence"]["failed_conditions"]
    assert len(failed) == 1
    assert failed[0]["key"] == "priority"
    assert failed[0]["actual"] == 3


def test_invalidated_if_matched_returns_suspended():
    skill = _skill(
        invalidated_if=[
            ApplicabilityCondition(
                key="blocked", operator=ApplicabilityOperator.eq, value=True
            )
        ]
    )
    result = evaluate_applicability(skill, {"blocked": True})

    assert result["status"] == ApplicabilityStatus.suspended
    assert "invalidated_if condition matched" in result["reason"]
    assert result["evidence"]["triggered"]["key"] == "blocked"


def test_missing_key_is_skipped_and_active():
    skill = _skill(
        applies_if=[
            ApplicabilityCondition(
                key="required_key", operator=ApplicabilityOperator.eq, value="x"
            )
        ]
    )
    result = evaluate_applicability(skill, {})

    assert result["status"] == ApplicabilityStatus.active
    skipped = result["evidence"]["skipped_conditions"]
    assert len(skipped) == 1
    assert skipped[0]["key"] == "required_key"
    assert skipped[0]["reason"] == "missing_key_or_type_error"


def test_type_error_is_skipped_and_active():
    skill = _skill(
        applies_if=[
            ApplicabilityCondition(
                key="value", operator=ApplicabilityOperator.gt, value=10
            )
        ]
    )
    result = evaluate_applicability(skill, {"value": "not-a-number"})

    assert result["status"] == ApplicabilityStatus.active
    skipped = result["evidence"]["skipped_conditions"]
    assert len(skipped) == 1
    assert skipped[0]["key"] == "value"
    assert skipped[0]["reason"] == "missing_key_or_type_error"
