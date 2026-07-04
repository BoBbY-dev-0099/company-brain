"""End-to-end smoke test against a running backend.

Usage:
    # in one terminal
    docker compose up -d
    uvicorn backend.main:app --port 8000

    # in another
    python -m backend.tests.smoke_e2e

Exits 0 on success, non-zero on any failure. The demo script in the README
runs essentially the same flow.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time

import httpx

BASE = "http://localhost:8000"
TEST_API_KEY = "test-api-key-placeholder"


def _headers() -> dict[str, str]:
    return {"X-Brain-Api-Key": TEST_API_KEY}


async def _check_health(client: httpx.AsyncClient) -> dict:
    r = await client.get(f"{BASE}/health", timeout=5.0)
    r.raise_for_status()
    payload = r.json()
    print(f"  health: {payload['status']} | skills={payload['skills_compiled']} | "
          f"qwen={payload['qwen_configured']} | db={payload['db']['connected']}")
    if not payload["db"]["connected"]:
        raise RuntimeError("Mongo not reachable from server")
    if payload["skills_compiled"] < 8:
        raise RuntimeError(f"Expected seed >=8 skills; got {payload['skills_compiled']}")
    return payload


async def _check_brain_list(client: httpx.AsyncClient) -> int:
    r = await client.get(f"{BASE}/brain/skills", headers=_headers(), timeout=5.0)
    r.raise_for_status()
    payload = r.json()
    print(f"  GET /brain/skills returned {payload['count']} skills")
    return payload["count"]


async def _check_decision_intercept(client: httpx.AsyncClient) -> None:
    body = {
        "agent_id": "engineering-agent-1",
        "decision_text": (
            "Adding a synchronous CSV export endpoint at /export/csv that returns "
            "the file inline. Customers want large data exports."
        ),
        "domain": "engineering",
    }
    r = await client.post(f"{BASE}/decisions/check", json=body, headers=_headers(), timeout=10.0)
    r.raise_for_status()
    payload = r.json()
    print(f"  POST /decisions/check -> result={payload['result']} "
          f"effective_conf={payload.get('confidence', 0):.2f} "
          f"matched={payload.get('matched_skill', {}).get('skill_id') if payload.get('matched_skill') else None}")
    if payload["result"] == "clear":
        raise RuntimeError("Expected non-clear intercept on a known seed pattern")


async def _check_attestation(client: httpx.AsyncClient) -> None:
    r = await client.get(f"{BASE}/mcp/attestation", headers=_headers(), timeout=5.0)
    r.raise_for_status()
    payload = r.json()
    print(f"  GET /mcp/attestation -> tee_capable={payload['tee_capable']} "
          f"platform={payload['platform']!r}")
    assert payload["tee_capable"] is True


async def _check_sse_hello(client: httpx.AsyncClient) -> None:
    async with client.stream("GET", f"{BASE}/stream", headers=_headers(), timeout=10.0) as resp:
        resp.raise_for_status()
        deadline = time.time() + 5.0
        async for chunk in resp.aiter_text():
            if "hello" in chunk or "keepalive" in chunk or "skills_compiled" in chunk:
                print(f"  SSE handshake OK ({len(chunk)} bytes received)")
                return
            if time.time() > deadline:
                raise RuntimeError("No SSE hello in 5s")


async def main() -> int:
    print("Company Brain E2E smoke test")
    print(f"  base: {BASE}")
    async with httpx.AsyncClient() as client:
        try:
            await _check_health(client)
            await _check_brain_list(client)
            await _check_decision_intercept(client)
            await _check_attestation(client)
            await _check_sse_hello(client)
        except (httpx.HTTPError, RuntimeError, AssertionError) as exc:
            print(f"\nFAIL: {exc}", file=sys.stderr)
            return 1
    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
