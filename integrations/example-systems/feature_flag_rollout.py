"""W3 — LaunchDarkly-shaped product bot: rollout percent SAG flip."""
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
    fixture = load_fixture("feature_flag_rollout.json")
    text = fixture["description"]
    own = client is None
    client = client or httpx.Client()
    try:
        ok = True
        under = decisions_check(
            client,
            agent_id="product-01",
            decision_text=text,
            domain="product",
            metadata=fixture["under_threshold"],
        )
        print_check("W3 rollout 3%", under)
        ok = expect_not_suspended(under, "W3-3pct") and ok
        if under.get("result") == "clear":
            print("FAIL W3-3pct: result=clear (embeddings/seed may be missing)", file=sys.stderr)
            ok = False

        over = decisions_check(
            client,
            agent_id="product-01",
            decision_text=text,
            domain="product",
            metadata=fixture["over_threshold"],
        )
        print_check("W3 rollout 40%", over)
        ok = expect_suspended(over, "W3-40pct") and ok
        return ok
    finally:
        if own:
            client.close()


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
