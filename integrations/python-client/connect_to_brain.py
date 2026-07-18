"""Run production-shaped workflows W1–W5 against a live Company Brain.

Usage:
  export BRAIN_BASE_URL=http://127.0.0.1:8000
  export BRAIN_API_KEY=cb_live_...
  python integrations/python-client/connect_to_brain.py

Exit 0 only if W1–W3 SAG expectations pass. W4–W5 skip cleanly without Qwen.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "example-systems"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _client import api_key, base_url, headers  # noqa: E402


def _load(name: str):
    path = EXAMPLES / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    key = api_key()
    url = base_url()
    print(f"BRAIN_BASE_URL={url}")
    print(f"BRAIN_API_KEY={key[:16]}...")

    with httpx.Client() as client:
        health = client.get(f"{url}/health", timeout=30.0)
        health.raise_for_status()
        h = health.json()
        print(f"[health] status={h.get('status')} embedding_healthy={h.get('embedding_healthy')} "
              f"skills_compiled={h.get('skills_compiled')}")
        if h.get("status") != "ok":
            print("FAIL health not ok", file=sys.stderr)
            return 1

        # Confirm auth works
        skills = client.get(f"{url}/brain/skills", headers=headers(), timeout=60.0)
        if skills.status_code != 200:
            print(f"FAIL auth: GET /brain/skills → {skills.status_code}", file=sys.stderr)
            return 1
        print(f"[auth] skills_count={skills.json().get('count')}")

        results: list[tuple[str, bool]] = []
        for name in (
            "github_pr_export",
            "billing_refund",
            "feature_flag_rollout",
            "zendesk_resolve",
            "product_session",
        ):
            print(f"\n=== {name} ===")
            mod = _load(name)
            ok = bool(mod.run(client))
            results.append((name, ok))
            print(f"-> {'PASS' if ok else 'FAIL'}")

    print("\n=== SUMMARY ===")
    hard = ("github_pr_export", "billing_refund", "feature_flag_rollout")
    failed_hard = False
    for name, ok in results:
        mark = "PASS" if ok else "FAIL"
        print(f"  {mark}  {name}")
        if name in hard and not ok:
            failed_hard = True

    if failed_hard:
        print("\nW1–W3 must pass for demo readiness.", file=sys.stderr)
        return 1
    print("\nAll required workflows passed (W1–W3).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
