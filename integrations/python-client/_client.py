"""Shared HTTP client for production-shaped connectors."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def base_url() -> str:
    return os.environ.get("BRAIN_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def api_key() -> str:
    key = os.environ.get("BRAIN_API_KEY", "").strip()
    if not key:
        print(
            "BRAIN_API_KEY is required. Run:\n"
            "  python integrations/python-client/bootstrap_api_key.py",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return key


def headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Brain-Api-Key": api_key(),
    }


def load_fixture(name: str) -> dict[str, Any]:
    path = FIXTURES / name
    return json.loads(path.read_text(encoding="utf-8"))


def decisions_check(
    client: httpx.Client,
    *,
    agent_id: str,
    decision_text: str,
    domain: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "agent_id": agent_id,
        "decision_text": decision_text,
        "metadata": metadata,
    }
    if domain:
        body["domain"] = domain
    r = client.post(f"{base_url()}/decisions/check", headers=headers(), json=body, timeout=120.0)
    r.raise_for_status()
    return r.json()


def print_check(label: str, resp: dict[str, Any]) -> None:
    matched = (resp.get("matched_skill") or {}).get("skill_id")
    print(f"[{label}] result={resp.get('result')} "
          f"applicability={resp.get('applicability_status')} "
          f"skill={matched}")
    if resp.get("suspension_reason"):
        print(f"  reason: {resp['suspension_reason']}")


def expect_result(resp: dict[str, Any], allowed: set[str], label: str) -> bool:
    got = str(resp.get("result") or "")
    if got not in allowed:
        print(f"FAIL {label}: expected result in {sorted(allowed)}, got {got!r}", file=sys.stderr)
        return False
    return True


def expect_suspended(resp: dict[str, Any], label: str) -> bool:
    ok = str(resp.get("result")) == "suspended" or str(resp.get("applicability_status")) == "suspended"
    if not ok:
        print(f"FAIL {label}: expected suspended, got result={resp.get('result')!r} "
              f"applicability={resp.get('applicability_status')!r}", file=sys.stderr)
    return ok


def expect_not_suspended(resp: dict[str, Any], label: str) -> bool:
    if str(resp.get("result")) == "suspended" or str(resp.get("applicability_status")) == "suspended":
        print(f"FAIL {label}: expected active/non-suspended, got suspended", file=sys.stderr)
        return False
    return True
