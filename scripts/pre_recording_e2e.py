"""Pre-recording E2E verification (local). Run: python scripts/pre_recording_e2e.py"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8000")
CLERK_SECRET = os.environ.get("CLERK_SECRET_KEY", "")
TS = int(time.time())
EMAIL1 = f"cb.fresh1.{TS}@example.com"
EMAIL2 = f"cb.fresh2.{TS}@example.com"
PASSWORD = f"E2eTest-{TS}!Aa"


async def clerk_create_user(email: str, first: str, last: str) -> dict:
    if not CLERK_SECRET:
        raise RuntimeError("CLERK_SECRET_KEY not set in .env")
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.clerk.com/v1/users",
            headers={"Authorization": f"Bearer {CLERK_SECRET}"},
            json={
                "email_address": [email],
                "password": PASSWORD,
                "first_name": first,
                "last_name": last,
                "skip_password_requirement": True,
                "skip_password_checks": True,
            },
        )
        r.raise_for_status()
        return r.json()


async def clerk_session_token(user_id: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.clerk.com/v1/sessions",
            headers={"Authorization": f"Bearer {CLERK_SECRET}"},
            json={"user_id": user_id},
        )
        r.raise_for_status()
        session_id = r.json()["id"]
        t = await client.post(
            f"https://api.clerk.com/v1/sessions/{session_id}/tokens",
            headers={"Authorization": f"Bearer {CLERK_SECRET}"},
            json={"expires_in_seconds": 3600},
        )
        t.raise_for_status()
        return t.json()["jwt"]


async def main() -> int:
    report: dict = {
        "base_url": BASE_URL,
        "frontend_url": "http://localhost:5174",
        "email1": EMAIL1,
        "email2": EMAIL2,
        "password": PASSWORD,
        "step0": {},
        "step1": {},
        "step2": {},
        "step3": {},
    }

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=120.0) as client:
        # STEP 0
        h = await client.get("/health")
        report["step0"] = {"status": h.status_code, "body": h.json()}

        # STEP 1 — create fresh user 1 via Clerk
        u1 = await clerk_create_user(EMAIL1, "Fresh", "One")
        user1_id = u1["id"]
        jwt1 = await clerk_session_token(user1_id)
        auth1 = {"Authorization": f"Bearer {jwt1}"}

        s1 = {}
        # 1.4 seed
        seed = await client.post("/settings/seed-demo-data", headers=auth1)
        s1["1.4_seed"] = {"status": seed.status_code, "body": seed.json()}

        # 1.5 skills
        skills = await client.get("/brain/skills", headers=auth1)
        skill_body = skills.json()
        s1["1.5_skills"] = {
            "status": skills.status_code,
            "count": skill_body.get("count"),
            "has_export_skill": any(
                s.get("skill_id") == "data-export-large-file-timeout"
                for s in skill_body.get("skills", [])
            ),
        }
        export = next(
            (s for s in skill_body.get("skills", []) if s.get("skill_id") == "data-export-large-file-timeout"),
            None,
        )
        s1["1.5_export_preconditions"] = {
            "applies_if": (export or {}).get("applicability", {}).get("applies_if"),
            "invalidated_if": (export or {}).get("applicability", {}).get("invalidated_if"),
        }

        # 1.6 small chunk
        small = await client.post(
            "/decisions/check",
            headers=auth1,
            json={
                "agent_id": "eng-01",
                "decision_text": "Increase data export chunk size to improve throughput",
                "metadata": {"export_chunk_size_mb": 8},
            },
        )
        s1["1.6_small"] = {"status": small.status_code, "body": small.json()}

        # 1.7 large chunk
        large = await client.post(
            "/decisions/check",
            headers=auth1,
            json={
                "agent_id": "eng-01",
                "decision_text": "Increase data export chunk size to improve throughput",
                "metadata": {"export_chunk_size_mb": 25},
            },
        )
        s1["1.7_large"] = {"status": large.status_code, "body": large.json()}

        # 1.8 intercepts
        intercepts = await client.get("/brain/intercepts?limit=10", headers=auth1)
        s1["1.8_intercepts"] = {"status": intercepts.status_code, "body": intercepts.json()}

        # 1.9 settings metrics
        metrics = await client.get("/settings/metrics", headers=auth1)
        s1["1.9_metrics"] = {"status": metrics.status_code, "body": metrics.json()}

        # API key for step 2
        key_resp = await client.post(
            "/settings/api-keys",
            headers=auth1,
            json={"name": "pre-record-e2e", "permissions": "read:skills read:events"},
        )
        api_key = key_resp.json().get("api_key", "")
        s1["1.3_api_key_prefix"] = api_key[:20] + "..." if api_key else None
        report["step1"] = s1
        report["api_key"] = api_key

        # STEP 2 — engineering agent
        key_auth = {"Authorization": f"Bearer {api_key}"}
        eng8 = await client.post(
            "/agents/engineering/run",
            headers=key_auth,
            json={
                "agent_id": "eng-fresh-test",
                "user_message": "Increase data export chunk size to improve throughput",
                "metadata": {"export_chunk_size_mb": 8},
            },
        )
        eng25 = await client.post(
            "/agents/engineering/run",
            headers=key_auth,
            json={
                "agent_id": "eng-fresh-test",
                "user_message": "Increase data export chunk size to improve throughput",
                "metadata": {"export_chunk_size_mb": 25},
            },
        )
        report["step2"] = {
            "eng_8mb": {"status": eng8.status_code, "body": eng8.json() if eng8.status_code == 200 else eng8.text},
            "eng_25mb": {"status": eng25.status_code, "body": eng25.json() if eng25.status_code == 200 else eng25.text},
        }

        # MCP check_intercept direct (in-process, same code path as /mcp/sse tool)
        from backend.brain.store import close as db_close, init_db
        from backend.mcp import tools as brain_tools

        await init_db()
        try:
            mcp8 = await brain_tools.check_intercept(
                agent_id="eng-fresh-test",
                decision_text="Increase data export chunk size to improve throughput",
                metadata={"export_chunk_size_mb": 8},
                org_id=user1_id,
            )
            mcp25 = await brain_tools.check_intercept(
                agent_id="eng-fresh-test",
                decision_text="Increase data export chunk size to improve throughput",
                metadata={"export_chunk_size_mb": 25},
                org_id=user1_id,
            )
        finally:
            await db_close()
        report["step2"]["mcp_check_8mb"] = mcp8
        report["step2"]["mcp_check_25mb"] = mcp25

        # STEP 3 — second org empty
        u2 = await clerk_create_user(EMAIL2, "Fresh", "Two")
        jwt2 = await clerk_session_token(u2["id"])
        auth2 = {"Authorization": f"Bearer {jwt2}"}
        skills2 = await client.get("/brain/skills", headers=auth2)
        report["step3"] = {
            "user2_id": u2["id"],
            "skills_status": skills2.status_code,
            "skills_body": skills2.json(),
        }

    out = ROOT / "PRE_RECORDING_E2E_REPORT.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
