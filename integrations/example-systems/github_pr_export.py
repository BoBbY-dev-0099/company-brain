"""W1 — GitHub-shaped PR bot: export chunk SAG flip."""
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
    fixture = load_fixture("github_pr_export.json")
    text = fixture["pull_request"]["title"]
    own = client is None
    client = client or httpx.Client()
    try:
        ok = True
        active = decisions_check(
            client,
            agent_id="github-pr-bot",
            decision_text=text,
            domain="engineering",
            metadata=fixture["live_config"],
        )
        print_check("W1 export 25MB", active)
        ok = expect_not_suspended(active, "W1-25MB") and ok
        # Prefer auto_execute when embeddings match; allow block if confidence tier differs
        if active.get("result") not in ("auto_execute", "block", "warn"):
            # clear means relevance failed — hard fail for demo readiness
            if active.get("result") == "clear":
                print("FAIL W1-25MB: result=clear (embeddings/seed may be missing)", file=sys.stderr)
                ok = False

        suspended = decisions_check(
            client,
            agent_id="github-pr-bot",
            decision_text=text,
            domain="engineering",
            metadata=fixture["edge_config"],
        )
        print_check("W1 export 8MB", suspended)
        ok = expect_suspended(suspended, "W1-8MB") and ok

        # Edge: missing metadata should not false-suspend on empty key eval
        missing = decisions_check(
            client,
            agent_id="github-pr-bot",
            decision_text=text,
            domain="engineering",
            metadata={},
        )
        print_check("W1 export no metadata", missing)
        if str(missing.get("result")) == "suspended":
            print("FAIL W1-no-meta: unexpected suspend without metadata", file=sys.stderr)
            ok = False
        return ok
    finally:
        if own:
            client.close()


if __name__ == "__main__":
    raise SystemExit(0 if run() else 1)
