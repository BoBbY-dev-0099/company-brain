"""W2 — Billing-shaped support bot: refund window SAG flip."""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-client"))
from _client import (  # noqa: E402
    decisions_check,
    expect_not_suspended,
    expect_suspended,
    load_fixture,
    print_check,
)


def run(client: httpx.Client | None = None) -> bool:
    fixture = load_fixture("billing_refund.json")
    text = fixture["request"]["message"]
    own = client is None
    client = client or httpx.Client()
    try:
        ok = True
        within = decisions_check(
            client,
            agent_id="support-01",
            decision_text=text,
            domain="support",
            metadata=fixture["within_window"],
        )
        print_check("W2 refund day=20", within)
        ok = expect_not_suspended(within, "W2-20d") and ok
        if within.get("result") == "clear":
            print("FAIL W2-20d: result=clear (embeddings/seed may be missing)", file=sys.stderr)
            ok = False

        outside = decisions_check(
            client,
            agent_id="support-01",
            decision_text=text,
            domain="support",
            metadata=fixture["outside_window"],
        )
        print_check("W2 refund day=60", outside)
        ok = expect_suspended(outside, "W2-60d") and ok
        return ok
    finally:
        if own:
            client.close()


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
