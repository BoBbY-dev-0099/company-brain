"""SAG performance benchmark."""

from __future__ import annotations

import asyncio
import random
import statistics
from typing import Any

from fastapi import APIRouter

from backend.core.sag_evaluator import evaluate_rule

router = APIRouter(prefix="/benchmark", tags=["benchmark"])

_DEMO_RULE = {
    "and": [
        {"gte": ["export_chunk_size_mb", 10]},
        {"eq": ["region", "us-east-1"]},
        {"regex": ["version", r"^2\."]},
    ]
}


@router.get("/sag")
async def benchmark_sag(runs: int = 1000) -> dict[str, Any]:
    runs = max(100, min(runs, 5000))

    async def _one(_: int) -> float:
        meta = {
            "export_chunk_size_mb": random.choice([8, 12, 25, 32]),
            "region": random.choice(["us-east-1", "ap-southeast-1"]),
            "version": random.choice(["2.1.0", "1.9.0", "2.0.0-rc1"]),
        }
        out = await asyncio.to_thread(evaluate_rule, _DEMO_RULE, meta)
        return float(out["evaluated_in_ms"])

    samples = await asyncio.gather(*[_one(i) for i in range(runs)])
    samples_sorted = sorted(samples)

    def pct(p: float) -> float:
        idx = min(len(samples_sorted) - 1, int(round((p / 100) * (len(samples_sorted) - 1))))
        return round(samples_sorted[idx], 6)

    p50, p95, p99 = pct(50), pct(95), pct(99)
    llm_ms = 180.0
    return {
        "p50_ms": p50,
        "p95_ms": p95,
        "p99_ms": p99,
        "mean_ms": round(statistics.fmean(samples), 6),
        "total_runs": runs,
        "comparison": {
            "llm_equivalent_ms": llm_ms,
            "speedup_factor": round(llm_ms / max(p50, 1e-9), 1),
        },
    }
