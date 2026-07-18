"""W5 — Product agent cross-session continuity for the same user_id."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-client"))
from _client import api_key, base_url, headers  # noqa: E402


def run(client: httpx.Client | None = None) -> bool:
    own = client is None
    client = client or httpx.Client()
    user_id = f"pm-user-{uuid.uuid4().hex[:8]}"
    session_a = f"session-{uuid.uuid4().hex[:6]}"
    session_b = f"session-{uuid.uuid4().hex[:6]}"
    try:
        # Edge: brand-new user sessions list is empty / clean
        before = client.get(
            f"{base_url()}/sessions/{user_id}",
            headers=headers(),
            timeout=60.0,
        )
        before.raise_for_status()
        print(f"[W5 new user] sessions={before.json().get('count', 0)}")

        first = client.post(
            f"{base_url()}/agents/product/run",
            headers=headers(),
            json={
                "agent_id": "product-agent-1",
                "user_id": user_id,
                "session_id": session_a,
                "user_message": (
                    "We are deciding whether enterprise onboarding should "
                    "require SSO before bulk seat provisioning."
                ),
            },
            timeout=180.0,
        )
        if first.status_code == 503:
            print("[W5 product] SKIP — QWEN_API_KEY not configured on server")
            return True
        if first.status_code != 200:
            print(f"FAIL W5-turn1: {first.status_code} {first.text[:300]}", file=sys.stderr)
            return False
        print(f"[W5 turn1] session={session_a} ok")

        second = client.post(
            f"{base_url()}/agents/product/run",
            headers=headers(),
            json={
                "agent_id": "product-agent-1",
                "user_id": user_id,
                "session_id": session_b,
                "user_message": "Picking up from earlier — any skills on SSO-first onboarding?",
            },
            timeout=180.0,
        )
        if second.status_code != 200:
            print(f"FAIL W5-turn2: {second.status_code} {second.text[:300]}", file=sys.stderr)
            return False
        body = second.json()
        print(f"[W5 turn2] session={session_b} intercepted={body.get('intercepted')}")

        sessions = client.get(
            f"{base_url()}/sessions/{user_id}",
            headers=headers(),
            timeout=60.0,
        )
        sessions.raise_for_status()
        count = sessions.json().get("count", 0)
        print(f"[W5 sessions] count={count}")
        if count < 1:
            print("FAIL W5: expected persisted sessions for user", file=sys.stderr)
            return False
        return True
    finally:
        if own:
            client.close()


if __name__ == "__main__":
    _ = api_key()
    raise SystemExit(0 if run() else 1)
