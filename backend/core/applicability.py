from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from backend.core.sag_evaluator import provenance_to_rule, evaluate_rule, SagRuleError
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


def _build_flat_trace(
    applies_if: list[ApplicabilityCondition],
    invalidated_if: list[ApplicabilityCondition],
    live_context: dict[str, Any],
    active: bool,
    elapsed_ms: float,
) -> dict[str, Any]:
    children: list[dict[str, Any]] = []
    for section, conds in (("invalidated_if", invalidated_if), ("applies_if", applies_if)):
        for cond in conds:
            held = _condition_holds(cond, live_context)
            children.append(
                {
                    "node": str(cond.operator.value if hasattr(cond.operator, "value") else cond.operator),
                    "args": [cond.key, cond.value, live_context.get(cond.key)],
                    "result": bool(held) if held is not None else False,
                    "ms": 0.0,
                    "note": None if held is not None else "SKIPPED_MISSING_OR_TYPE",
                    "section": section,
                }
            )
    return {
        "node": "and",
        "args": children,
        "result": active,
        "ms": round(elapsed_ms, 6),
    }


def evaluate_applicability(
    skill: CompanyBrainSkill,
    live_context: dict[str, Any],
) -> dict[str, Any]:
    """Determine whether a skill is currently applicable given live context.

    Rules (backward-compatible):
      - No conditions -> active.
      - Any ``invalidated_if`` condition evaluates to True -> suspended.
      - Any ``applies_if`` condition evaluates to False -> suspended.
      - Conditions whose keys are missing or hit a type error are skipped.
      - No LLM or external calls are made.

    Also attaches an evaluation ``trace`` (AST when possible, else flat).
    """
    started = time.perf_counter()
    provenance = skill.provenance
    invalidated_if = provenance.invalidated_if
    applies_if = provenance.applies_if
    meta = dict(live_context or {})

    evidence: dict[str, Any] = {
        "skill_id": skill.skill_id,
        "checked_at": _utc_now().isoformat(),
    }

    status = ApplicabilityStatus.active
    reason: str | None = None

    for cond in invalidated_if:
        result = _condition_holds(cond, meta)
        if result is True:
            evidence["triggered"] = {
                "section": "invalidated_if",
                "key": cond.key,
                "operator": cond.operator,
                "value": cond.value,
                "actual": meta.get(cond.key),
            }
            status = ApplicabilityStatus.suspended
            reason = (
                f"invalidated_if condition matched: {cond.key} {cond.operator} {cond.value!r}"
            )
            break

    failed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    if status == ApplicabilityStatus.active:
        for cond in applies_if:
            result = _condition_holds(cond, meta)
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
                        "actual": meta.get(cond.key),
                    }
                )

        if skipped:
            evidence["skipped_conditions"] = skipped
        if failed:
            evidence["failed_conditions"] = failed
            status = ApplicabilityStatus.suspended
            reason = "applies_if conditions failed: " + "; ".join(
                f"{item['key']} {item['operator']} {item['expected']!r}"
                for item in failed
            )

    elapsed_ms = (time.perf_counter() - started) * 1000
    active = status == ApplicabilityStatus.active

    rule = provenance_to_rule(applies_if, invalidated_if)
    trace: dict[str, Any]
    try:
        # AST trace is supplemental; status above remains source of truth for
        # missing-key skip semantics used by existing skills/tests.
        ast_out = evaluate_rule(rule, meta) if rule != {"lit": True} else {
            "trace": {"node": "lit", "args": [True], "result": True, "ms": 0.0},
            "evaluated_in_ms": 0.0,
        }
        trace = ast_out["trace"]
        # Prefer wall time of the authoritative flat eval for reported ms.
        eval_ms = round(elapsed_ms, 6)
    except SagRuleError:
        trace = _build_flat_trace(applies_if, invalidated_if, meta, active, elapsed_ms)
        eval_ms = round(elapsed_ms, 6)

    # If AST disagrees because of MISSING_FIELD strictness, keep flat status
    # but annotate the trace.
    if isinstance(trace, dict):
        trace = {**trace, "authoritative_result": active}

    return {
        "status": status,
        "reason": reason,
        "evidence": evidence,
        "evaluated_in_ms": eval_ms,
        "trace": trace,
        "rule": rule,
    }
