from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from backend.core.schema import (
    ApplicabilityCondition,
    ApplicabilityOperator,
    ApplicabilityStatus,
    CompanyBrainSkill,
)

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _condition_holds(cond: ApplicabilityCondition, live_context: dict[str, Any]) -> bool | None:
    """Evaluate a single applicability condition against a live context dict.

    Returns:
        - True / False when the condition can be evaluated.
        - None when the required key is missing (for non-existence operators)
          or a type error prevents comparison. Type errors are logged.
    """
    key = cond.key
    op = cond.operator
    expected = cond.value

    if op == ApplicabilityOperator.exists:
        return key in live_context

    if op == ApplicabilityOperator.not_exists:
        return key not in live_context

    if key not in live_context:
        return None

    actual = live_context[key]

    try:
        if op == ApplicabilityOperator.eq:
            return actual == expected
        if op == ApplicabilityOperator.neq:
            return actual != expected
        if op == ApplicabilityOperator.gt:
            return actual > expected
        if op == ApplicabilityOperator.gte:
            return actual >= expected
        if op == ApplicabilityOperator.lt:
            return actual < expected
        if op == ApplicabilityOperator.lte:
            return actual <= expected
        if op == ApplicabilityOperator.in_:
            return actual in expected
        if op == ApplicabilityOperator.not_in:
            return actual not in expected
    except TypeError as exc:
        logger.warning(
            "Applicability type error for key '%s' with operator '%s': %s",
            key,
            op,
            exc,
        )
        return None

    logger.warning("Unsupported applicability operator: %s", op)
    return None


def evaluate_applicability(
    skill: CompanyBrainSkill,
    live_context: dict[str, Any],
) -> dict[str, Any]:
    """Determine whether a skill is currently applicable given live context.

    Rules:
      - No conditions -> active.
      - Any ``invalidated_if`` condition evaluates to True -> suspended.
      - Any ``applies_if`` condition evaluates to False -> suspended.
      - Conditions whose keys are missing (for non-existence operators) or
        that hit a type error are skipped.
      - No LLM or external calls are made.

    Returns:
        A dict with keys ``status`` (ApplicabilityStatus), ``reason``
        (str | None), and ``evidence`` (dict | None).
    """
    provenance = skill.provenance
    invalidated_if = provenance.invalidated_if
    applies_if = provenance.applies_if

    evidence: dict[str, Any] = {
        "skill_id": skill.skill_id,
        "checked_at": _utc_now().isoformat(),
    }

    # Check invalidated_if conditions first.
    for cond in invalidated_if:
        result = _condition_holds(cond, live_context)
        if result is True:
            evidence["triggered"] = {
                "section": "invalidated_if",
                "key": cond.key,
                "operator": cond.operator,
                "value": cond.value,
                "actual": live_context.get(cond.key),
            }
            return {
                "status": ApplicabilityStatus.suspended,
                "reason": (
                    f"invalidated_if condition matched: {cond.key} {cond.operator} {cond.value!r}"
                ),
                "evidence": evidence,
            }

    # Check applies_if conditions.
    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for cond in applies_if:
        result = _condition_holds(cond, live_context)
        if result is None:
            skipped.append(
                {
                    "key": cond.key,
                    "operator": cond.operator,
                    "value": cond.value,
                    "reason": "missing_key_or_type_error",
                }
            )
            continue
        if result is False:
            failed.append(
                {
                    "key": cond.key,
                    "operator": cond.operator,
                    "expected": cond.value,
                    "actual": live_context.get(cond.key),
                }
            )

    if skipped:
        evidence["skipped_conditions"] = skipped
    if failed:
        evidence["failed_conditions"] = failed
        return {
            "status": ApplicabilityStatus.suspended,
            "reason": "applies_if conditions failed: " + "; ".join(
                f"{item['key']} {item['operator']} {item['expected']!r}"
                for item in failed
            ),
            "evidence": evidence,
        }

    return {
        "status": ApplicabilityStatus.active,
        "reason": None,
        "evidence": evidence,
    }
