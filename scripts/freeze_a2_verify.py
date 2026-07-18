"""One-off freeze pass: simulate A2 domain-general SAG curls (no Mongo)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.core.interceptor import check_decision
from backend.core.schema import DecisionCheckRequest
from backend.demo.seed_data import _seed_skills


async def run_case(label: str, payload: dict) -> None:
    active = list(_seed_skills())
    vec = [1.0] + [0.0] * 1023
    for s in active:
        s.embedding = vec

    async def fake_get_all(domain: str | None = None, org_id: str = "default"):
        if domain:
            return [s for s in active if s.domain == domain]
        return active

    async def fake_reinforce(skill_id: str, org_id: str = "default"):
        return next(s for s in active if s.skill_id == skill_id)

    patches = [
        patch("backend.core.interceptor.store.get_all_active_skills", fake_get_all),
        patch("backend.core.interceptor.generate_embedding", AsyncMock(return_value=vec)),
        patch("backend.core.interceptor.store.reinforce_skill", fake_reinforce),
        patch(
            "backend.core.interceptor.store.save_skill",
            AsyncMock(side_effect=lambda sk, org_id="default": sk),
        ),
        patch("backend.core.interceptor.store.log_intercept", AsyncMock(return_value=None)),
        patch("backend.core.interceptor.propagator.broadcast", AsyncMock(return_value=None)),
    ]

    for p in patches:
        p.start()
    try:
        req = DecisionCheckRequest(**payload, org_id="default")
        resp = await check_decision(req)
        print(f"--- {label} ---")
        print(
            json.dumps(
                {
                    "result": resp.result.value,
                    "confidence": round(resp.confidence, 2),
                    "applicability_status": getattr(
                        resp.applicability_status, "value", resp.applicability_status
                    ),
                    "suspension_reason": resp.suspension_reason,
                    "matched_skill_id": resp.matched_skill.skill_id if resp.matched_skill else None,
                },
                indent=2,
            )
        )
    finally:
        for p in reversed(patches):
            p.stop()


async def main() -> None:
    cases = [
        (
            "refund-20",
            {
                "agent_id": "support-01",
                "decision_text": "Customer requesting refund on annual plan",
                "domain": "support",
                "metadata": {"days_since_purchase": 20},
            },
        ),
        (
            "refund-60",
            {
                "agent_id": "support-01",
                "decision_text": "Customer requesting refund on annual plan",
                "domain": "support",
                "metadata": {"days_since_purchase": 60},
            },
        ),
        (
            "rollout-3",
            {
                "agent_id": "product-01",
                "decision_text": "Expanding new dashboard widgets rollout",
                "domain": "product",
                "metadata": {"feature_flag_rollout_percent": 3},
            },
        ),
        (
            "rollout-40",
            {
                "agent_id": "product-01",
                "decision_text": "Expanding new dashboard widgets rollout",
                "domain": "product",
                "metadata": {"feature_flag_rollout_percent": 40},
            },
        ),
    ]
    for label, payload in cases:
        await run_case(label, payload)


if __name__ == "__main__":
    asyncio.run(main())
