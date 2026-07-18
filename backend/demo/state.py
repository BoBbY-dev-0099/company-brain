"""Canonical demo-state policy and readiness helpers.

The judge fixture is evidence for a repeatable story, not a shared sandbox.
Callers that accept exploratory writes should use ``SANDBOX_ORG_ID`` and call
``assert_demo_org_mutable`` before changing fixture-backed data.
"""

from __future__ import annotations

from typing import Any

from backend.config import settings


def is_canonical_demo_org(org_id: str) -> bool:
    """Whether an org is the immutable, versioned judge fixture."""
    return org_id == settings.JUDGE_DEMO_ORG_ID


def is_sandbox_org(org_id: str) -> bool:
    """Whether an org is the disposable interactive demo sandbox."""
    return org_id == settings.SANDBOX_ORG_ID


def assert_demo_org_mutable(org_id: str) -> None:
    """Reject writes that would pollute the canonical judge fixture.

    Seeding/versioning code is the only exception and should write its fixture
    through an explicit controlled bootstrap path instead of a public action.
    """
    if is_canonical_demo_org(org_id):
        raise ValueError(
            "judge-demo-v1 is immutable; send exploratory actions to the sandbox org"
        )


def demo_org_policy() -> dict[str, dict[str, Any]]:
    """Small, API-safe description of the demo data boundary."""
    return {
        "judge_demo": {
            "org_id": settings.JUDGE_DEMO_ORG_ID,
            "scenario_version": settings.DEMO_SCENARIO_VERSION,
            "immutable": True,
            "purpose": "canonical judge fixture",
        },
        "sandbox": {
            "org_id": settings.SANDBOX_ORG_ID,
            "scenario_version": None,
            "immutable": False,
            "purpose": "disposable exploration and demo clicks",
        },
    }


async def build_demo_readiness(
    *,
    qwen_configured: bool,
    embedding_healthy: bool | None,
    build_sha: str | None = None,
) -> dict[str, Any]:
    """Return only verifiable deployment/demo readiness facts.

    This intentionally distinguishes fixture state from a live sandbox and
    avoids presenting estimates as measured deployment proof.  The HTTP route
    is registered by the application layer so this module remains usable in
    tests and scripts without importing FastAPI.
    """
    from backend.brain import store

    policy = demo_org_policy()
    for key, details in policy.items():
        org_id = str(details["org_id"])
        try:
            details["skill_count"] = await store.get_skill_count(
                active_only=False,
                org_id=org_id,
            )
            details["event_count"] = len(await store.get_recent_events(org_id=org_id, limit=1_000))
            details["state_available"] = True
        except Exception as exc:  # noqa: BLE001
            details["skill_count"] = None
            details["event_count"] = None
            details["state_available"] = False
            details["state_error"] = str(exc)[:200]

    canonical_state_available = bool(policy["judge_demo"].get("state_available"))
    return {
        "ready": bool(
            qwen_configured
            and embedding_healthy is not False
            and canonical_state_available
        ),
        "build_sha": build_sha or settings.BUILD_SHA,
        "scenario_version": settings.DEMO_SCENARIO_VERSION,
        "qwen_configured": qwen_configured,
        "embedding_healthy": embedding_healthy,
        "canonical_skill_count": policy["judge_demo"].get("skill_count"),
        "canonical_event_count": policy["judge_demo"].get("event_count"),
        "canonical_state_available": canonical_state_available,
        "sandbox_skill_count": policy["sandbox"].get("skill_count"),
        "canonical_fixture_immutable": True,
        "demo_orgs": policy,
        "human_approval_required": True,
        "metrics_note": (
            "Operational counters are observed counts. Any token-savings field is an "
            "estimate and not a measured production result."
        ),
    }
