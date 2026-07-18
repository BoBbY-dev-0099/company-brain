"""W4 — Zendesk-shaped ticket resolve → compile experience into a skill."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-client"))
from _client import api_key, base_url, headers, load_fixture  # noqa: E402


def run(client: httpx.Client | None = None) -> bool:
    fixture = load_fixture("zendesk_ticket_resolved.json")
    own = client is None
    client = client or httpx.Client()
    try:
        # Edge: empty content → 422
        empty = client.post(
            f"{base_url()}/events",
            headers=headers(),
            json={
                "event_id": f"zd-empty-{uuid.uuid4().hex[:8]}",
                "agent_id": fixture["agent_id"],
                "event_type": fixture["event_type"],
                "content": "   ",
            },
            timeout=60.0,
        )
        if empty.status_code != 422:
            print(f"FAIL W4-empty: expected 422, got {empty.status_code}", file=sys.stderr)
            return False
        print("[W4 empty content] 422 as expected")

        body = {
            "event_id": f"zd-{fixture['ticket_id']}-{uuid.uuid4().hex[:6]}",
            "agent_id": fixture["agent_id"],
            "event_type": fixture["event_type"],
            "content": fixture["content"],
            "outcome": fixture["outcome"],
        }
        compiled = client.post(
            f"{base_url()}/events",
            headers=headers(),
            json=body,
            timeout=180.0,
        )
        if compiled.status_code == 503:
            print("[W4 compile] SKIP — QWEN_API_KEY not configured on server")
            return True
        if compiled.status_code != 200:
            print(f"FAIL W4-compile: {compiled.status_code} {compiled.text[:300]}", file=sys.stderr)
            return False
        data = compiled.json()
        skill_id = data.get("skill_id") or data.get("skill_compiled")
        print(f"[W4 compile] skill={skill_id} status=ok")

        skills = client.get(f"{base_url()}/brain/skills", headers=headers(), timeout=60.0)
        skills.raise_for_status()
        count = skills.json().get("count", 0)
        print(f"[W4 skills] count={count}")
        if count < 1:
            print("FAIL W4: brain has zero skills after compile", file=sys.stderr)
            return False
        return True
    finally:
        if own:
            client.close()


if __name__ == "__main__":
    _ = api_key()  # validate env early
    raise SystemExit(0 if run() else 1)
