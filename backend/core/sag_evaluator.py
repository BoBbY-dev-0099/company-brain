"""Deterministic SAG AST evaluator with per-node evaluation traces."""

from __future__ import annotations

import re
import time
from typing import Any

MAX_RULE_DEPTH = 10


class SagRuleError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


def _resolve_path(metadata: dict[str, Any], path: str) -> tuple[bool, Any]:
    cur: Any = metadata
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _leaf(
    operator: str,
    args: list[Any],
    result: bool,
    ms: float,
    note: str | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "node": operator,
        "args": args,
        "result": result,
        "ms": round(ms, 6),
    }
    if note:
        node["note"] = note
    return node


def evaluate_rule(
    rule: Any,
    metadata: dict[str, Any],
    *,
    _depth: int = 0,
) -> dict[str, Any]:
    """Evaluate an AST rule. Returns ``{result, trace, evaluated_in_ms}``."""
    started = time.perf_counter()
    if _depth > MAX_RULE_DEPTH:
        raise SagRuleError("RULE_DEPTH_EXCEEDED", f"Nested depth > {MAX_RULE_DEPTH}")

    if not isinstance(rule, dict) or len(rule) != 1:
        raise SagRuleError("INVALID_RULE", "Rule must be a single-key object")

    op, raw_args = next(iter(rule.items()))
    t0 = time.perf_counter()

    if op == "lit":
        result = bool(raw_args)
        trace = _leaf("lit", [raw_args], result, (time.perf_counter() - t0) * 1000)
    elif op == "and":
        if not isinstance(raw_args, list):
            raise SagRuleError("INVALID_RULE", "'and' expects a list")
        children = [evaluate_rule(child, metadata, _depth=_depth + 1) for child in raw_args]
        result = all(c["result"] for c in children)
        trace = {
            "node": "and",
            "args": [c["trace"] for c in children],
            "result": result,
            "ms": round((time.perf_counter() - t0) * 1000, 6),
        }
    elif op == "or":
        if not isinstance(raw_args, list):
            raise SagRuleError("INVALID_RULE", "'or' expects a list")
        children = [evaluate_rule(child, metadata, _depth=_depth + 1) for child in raw_args]
        result = any(c["result"] for c in children)
        trace = {
            "node": "or",
            "args": [c["trace"] for c in children],
            "result": result,
            "ms": round((time.perf_counter() - t0) * 1000, 6),
        }
    elif op == "not":
        child = evaluate_rule(raw_args, metadata, _depth=_depth + 1)
        result = not child["result"]
        trace = {
            "node": "not",
            "args": [child["trace"]],
            "result": result,
            "ms": round((time.perf_counter() - t0) * 1000, 6),
        }
    elif op in {"eq", "neq", "gt", "gte", "lt", "lte", "regex", "in", "in_", "exists"}:
        if not isinstance(raw_args, list) or not raw_args:
            raise SagRuleError("INVALID_RULE", f"'{op}' expects a list of args")
        path = raw_args[0]
        if not isinstance(path, str):
            raise SagRuleError("INVALID_RULE", f"'{op}' path must be a string")

        if op == "exists":
            found, _ = _resolve_path(metadata, path)
            result = found
            trace = _leaf(op, [path], result, (time.perf_counter() - t0) * 1000)
        else:
            if len(raw_args) < 2:
                raise SagRuleError("INVALID_RULE", f"'{op}' expects [path, value]")
            expected = raw_args[1]
            found, actual = _resolve_path(metadata, path)
            if not found:
                result = False
                trace = _leaf(
                    op,
                    [path, expected],
                    result,
                    (time.perf_counter() - t0) * 1000,
                    note="MISSING_FIELD",
                )
            else:
                try:
                    if op == "eq":
                        result = actual == expected
                    elif op == "neq":
                        result = actual != expected
                    elif op == "gt":
                        result = actual > expected
                    elif op == "gte":
                        result = actual >= expected
                    elif op == "lt":
                        result = actual < expected
                    elif op == "lte":
                        result = actual <= expected
                    elif op == "regex":
                        result = bool(re.match(str(expected), str(actual)))
                    elif op in {"in", "in_"}:
                        result = actual in expected
                    else:
                        result = False
                except TypeError:
                    result = False
                    trace = _leaf(
                        op,
                        [path, expected, actual],
                        result,
                        (time.perf_counter() - t0) * 1000,
                        note="TYPE_ERROR",
                    )
                else:
                    trace = _leaf(
                        op,
                        [path, expected, actual],
                        result,
                        (time.perf_counter() - t0) * 1000,
                    )
    else:
        raise SagRuleError("INVALID_RULE", f"Unsupported operator: {op}")

    return {
        "result": result,
        "trace": trace,
        "evaluated_in_ms": round((time.perf_counter() - started) * 1000, 6),
    }


def condition_to_ast(key: str, operator: str, value: Any) -> dict[str, Any]:
    op = "in" if operator == "in_" else operator
    if op in {"exists", "not_exists"}:
        if op == "exists":
            return {"exists": [key]}
        return {"not": {"exists": [key]}}
    if op == "not_in":
        return {"not": {"in": [key, value]}}
    return {op: [key, value]}


def provenance_to_rule(
    applies_if: list[Any],
    invalidated_if: list[Any],
) -> dict[str, Any]:
    """Build an AST that is True when the skill should remain active."""
    parts: list[dict[str, Any]] = []

    inv_leaves = [
        condition_to_ast(c.key, c.operator.value if hasattr(c.operator, "value") else str(c.operator), c.value)
        for c in invalidated_if
    ]
    if inv_leaves:
        parts.append({"not": {"or": inv_leaves}})

    app_leaves = [
        condition_to_ast(c.key, c.operator.value if hasattr(c.operator, "value") else str(c.operator), c.value)
        for c in applies_if
    ]
    if app_leaves:
        parts.append({"and": app_leaves})

    if not parts:
        return {"lit": True}
    if len(parts) == 1:
        return parts[0]
    return {"and": parts}
