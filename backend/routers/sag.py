"""Explicit SAG evaluate endpoint with full traces."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from backend.brain import store
from backend.config import settings
from backend.core.applicability import evaluate_applicability
from backend.core.sag_evaluator import SagRuleError, evaluate_rule
from backend.core.schema import ApplicabilityStatus
from backend.services import decision_integrity

router = APIRouter(prefix="/sag", tags=["sag"])


class SagEvaluateRequest(BaseModel):
    skill_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    rule: dict[str, Any] | None = None
    attest: bool = True


def _org(request: Request) -> str:
    return getattr(request.state, "org_id", None) or settings.DEMO_ORG_ID


@router.post("/evaluate")
async def evaluate_sag(body: SagEvaluateRequest, request: Request) -> dict[str, Any]:
    org_id = _org(request)

    if body.rule is not None:
        try:
            out = evaluate_rule(body.rule, body.metadata)
        except SagRuleError as exc:
            raise HTTPException(
                status_code=400,
                detail={"error": exc.code, "detail": exc.detail},
            ) from exc
        decision = "auto_execute" if out["result"] else "suspended"
        integrity = None
        if body.attest and body.skill_id:
            integrity = await decision_integrity.attest_decision(
                org_id=org_id,
                skill_id=body.skill_id,
                metadata=body.metadata,
                decision=decision,
            )
        return {
            "skill_id": body.skill_id,
            "decision": decision,
            "evaluated_in_ms": out["evaluated_in_ms"],
            "trace": out["trace"],
            "rule": body.rule,
            "metadata": body.metadata,
            "integrity": integrity,
        }

    skill_id = body.skill_id or "data-export-large-file-timeout"
    skill = await store.get_skill(skill_id, org_id=org_id)
    if skill is None:
        raise HTTPException(status_code=404, detail={"error": "SKILL_NOT_FOUND"})

    sag = evaluate_applicability(skill, body.metadata)
    decision = (
        "auto_execute"
        if sag["status"] == ApplicabilityStatus.active
        else "suspended"
    )
    integrity = None
    if body.attest:
        integrity = await decision_integrity.attest_decision(
            org_id=org_id,
            skill_id=skill_id,
            metadata=body.metadata,
            decision=decision,
        )
    return {
        "skill_id": skill_id,
        "decision": decision,
        "evaluated_in_ms": sag.get("evaluated_in_ms"),
        "trace": sag.get("trace"),
        "rule": sag.get("rule"),
        "metadata": body.metadata,
        "reason": sag.get("reason"),
        "status": sag["status"].value if hasattr(sag["status"], "value") else sag["status"],
        "integrity": integrity,
    }
