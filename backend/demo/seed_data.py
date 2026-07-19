"""Idempotent demo seed: 8 pre-compiled skills + 3 sessions.

Embeddings are intentionally NOT generated here — the compiler module owns
embedding generation. If `regenerate_embeddings=True` is passed at startup,
main.py calls compiler.generate_embedding() for each seeded skill that lacks one.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import timedelta
from typing import Any

from backend.brain import store
from backend.config import settings
from backend.core.schema import (
    ApplicabilityCondition,
    ApplicabilityOperator,
    CompanyBrainSkill,
    DecayRate,
    SessionMemory,
    SkillExecutable,
    SkillKnowledge,
    SkillPattern,
    SkillProvenance,
    utc_now,
)

logger = logging.getLogger(__name__)


def _skill(
    skill_id: str,
    name: str,
    domain: str,
    summary: str,
    keywords: list[str],
    entity_types: list[str],
    context_signals: list[str],
    what_happened: str,
    failure_mode: str,
    what_worked: str,
    conditions: list[str],
    anti_conditions: list[str],
    intercept_message: str,
    recommended_action: str,
    avoid_actions: list[str],
    confidence: float,
    reinforcement_count: int,
    decay_rate: DecayRate,
    auto_execute: bool = False,
    applies_if: list[ApplicabilityCondition] | None = None,
    invalidated_if: list[ApplicabilityCondition] | None = None,
) -> CompanyBrainSkill:
    return CompanyBrainSkill(
        skill_id=skill_id,
        name=name,
        version=1,
        domain=domain,
        summary=summary,
        pattern=SkillPattern(
            keywords=keywords,
            entity_types=entity_types,
            context_signals=context_signals,
            domains=[domain],
        ),
        knowledge=SkillKnowledge(
            what_happened=what_happened,
            failure_mode=failure_mode,
            what_worked=what_worked,
            conditions=conditions,
            anti_conditions=anti_conditions,
        ),
        executable=SkillExecutable(
            intercept_message=intercept_message,
            recommended_action=recommended_action,
            avoid_actions=avoid_actions,
            auto_execute=auto_execute,
            escalate_if=[],
        ),
        provenance=SkillProvenance(
            source_event_id=f"seed-{skill_id}",
            compiled_at=utc_now() - timedelta(days=2),
            confidence=confidence,
            reinforcement_count=reinforcement_count,
            # Curated fixture confidence represents historical, manually
            # reviewed outcomes. It is not produced by a demo click.
            human_confirmed_outcome_count=reinforcement_count,
            last_validated=utc_now(),
            decay_rate=decay_rate,
            applies_if=applies_if or [],
            invalidated_if=invalidated_if or [],
        ),
    )


def _seed_skills() -> list[CompanyBrainSkill]:
    return [
        _skill(
            skill_id="data-export-large-file-timeout",
            name="Large data export timeout",
            domain="engineering",
            summary="Synchronous data exports >100MB time out at the gateway; use async job queue instead.",
            keywords=["data export", "csv export", "download", "timeout", "504", "large file"],
            entity_types=["api_endpoint", "export_job"],
            context_signals=["file_size>100mb", "synchronous_request", "export_endpoint"],
            what_happened=(
                "Customer report: large CSV exports of >100MB returned 504 gateway timeouts. "
                "Synchronous export endpoint blocked nginx worker for >60s."
            ),
            failure_mode="Gateway timeout at 60s for synchronous exports above 100MB",
            what_worked=(
                "Switched to async job queue (Redis + worker). Endpoint returns job_id, "
                "client polls /jobs/{id}. Eliminated all timeouts."
            ),
            conditions=["export_size > 100MB", "endpoint is /export/* family"],
            anti_conditions=["streaming endpoint already in use", "export_size < 10MB"],
            intercept_message="This PR adds a synchronous export path. Large exports will 504. Use the async job queue.",
            recommended_action="Use existing /jobs/* async pattern. See workers/export_worker.py.",
            avoid_actions=["adding synchronous export endpoint", "increasing nginx timeout to mask the issue"],
            confidence=0.94,
            reinforcement_count=4,
            decay_rate=DecayRate.SLOW,
            auto_execute=True,
            applies_if=[
                ApplicabilityCondition(
                    key="export_chunk_size_mb",
                    operator=ApplicabilityOperator.gt,
                    value=10,
                )
            ],
            invalidated_if=[
                ApplicabilityCondition(
                    key="export_chunk_size_mb",
                    operator=ApplicabilityOperator.lte,
                    value=10,
                )
            ],
        ),
        _skill(
            skill_id="auth-token-refresh-mobile-clock-skew",
            name="Mobile auth token refresh fails on clock skew",
            domain="support",
            summary="Mobile clients with >5min clock skew silently fail token refresh; show clock-sync hint.",
            keywords=["auth", "token", "refresh", "401", "mobile", "clock", "session expired"],
            entity_types=["mobile_session", "auth_token"],
            context_signals=["mobile_client", "repeated_401", "session_age<token_ttl"],
            what_happened="Multiple mobile users hit unrecoverable 401 loops; root cause: device clock off by 5+ minutes invalidating JWT exp claim.",
            failure_mode="Silent token refresh failure due to clock skew",
            what_worked="Added clock-skew detection and prompt to enable network time. Resolved 95% of mobile 401 reports.",
            conditions=["mobile platform", "401 with valid token format"],
            anti_conditions=["desktop/web client", "actual session expiry"],
            intercept_message="Mobile 401 reports often look like auth bugs but are clock skew. Check device time first.",
            recommended_action="Run clock-skew check before issuing new credentials.",
            avoid_actions=["forcing logout", "rotating tokens server-side without diagnosis"],
            confidence=0.88,
            reinforcement_count=3,
            decay_rate=DecayRate.MEDIUM,
            auto_execute=True,
        ),
        _skill(
            skill_id="db-migration-add-not-null-column",
            name="Adding NOT NULL column to large tables",
            domain="engineering",
            summary="NOT NULL column adds on tables >10M rows lock writes; use multi-step nullable+backfill+constrain pattern.",
            keywords=["migration", "alter table", "not null", "lock", "deadlock", "schema"],
            entity_types=["database_migration", "table"],
            context_signals=["table_rowcount>10M", "production_db"],
            what_happened="Single-statement ALTER TABLE ADD COLUMN ... NOT NULL DEFAULT '...' locked writes for 8 minutes on a 50M-row table during deploy.",
            failure_mode="Long write lock during single-statement NOT NULL add",
            what_worked="Three-step migration: (1) add nullable, (2) backfill in batches, (3) ALTER COLUMN SET NOT NULL.",
            conditions=["table > 10M rows", "production write traffic active"],
            anti_conditions=["dev/staging db", "small reference tables"],
            intercept_message="Single-statement NOT NULL add will lock writes on this table size. Use the three-step pattern.",
            recommended_action="Split into nullable + backfill + constrain migrations.",
            avoid_actions=["single ALTER TABLE", "running during peak traffic"],
            confidence=0.91,
            reinforcement_count=3,
            decay_rate=DecayRate.SLOW,
            auto_execute=False,
        ),
        _skill(
            skill_id="webhook-retry-idempotency-key",
            name="Webhook retries require idempotency keys",
            domain="engineering",
            summary="Outbound webhooks must include idempotency-key header; receivers double-process retries otherwise.",
            keywords=["webhook", "retry", "idempotency", "duplicate", "double charge"],
            entity_types=["webhook", "http_handler"],
            context_signals=["outbound_webhook", "retry_logic"],
            what_happened="A flaky receiver caused our retry policy to fire 3x; receiver processed each retry as a new event, causing duplicate charges.",
            failure_mode="Duplicate processing on the receiver side during webhook retries",
            what_worked="Added X-Idempotency-Key header on every outbound webhook + 24h dedup window on the receiver.",
            conditions=["outbound webhook with side effects", "retry policy enabled"],
            anti_conditions=["pure-read webhooks", "no retry"],
            intercept_message="This webhook handler has retries but no idempotency key. Receivers will double-process.",
            recommended_action="Add X-Idempotency-Key header sourced from event_id.",
            avoid_actions=["disabling retries to mask the issue"],
            confidence=0.86,
            reinforcement_count=2,
            decay_rate=DecayRate.MEDIUM,
            auto_execute=True,
        ),
        _skill(
            skill_id="enterprise-onboarding-sso-first",
            name="Enterprise onboarding requires SSO before seat provisioning",
            domain="product",
            summary="Enterprise tenants must configure SSO/SAML before bulk seat provisioning to avoid downstream auth conflicts.",
            keywords=["enterprise", "onboarding", "sso", "saml", "seats", "tenant"],
            entity_types=["tenant", "onboarding_flow"],
            context_signals=["enterprise_plan", "tenant_size>50"],
            what_happened="Three enterprise rollouts had to roll back seat provisioning because SSO got configured second; users locked out.",
            failure_mode="Seat provisioning before SSO causes auth lockouts on first SSO config",
            what_worked="Onboarding wizard now blocks seat upload until SSO is fully tested.",
            conditions=["enterprise plan", "seat count > 50"],
            anti_conditions=["SMB/individual plans", "bring-your-own-IDP already validated"],
            intercept_message="Don't recommend bulk seat provisioning before SSO is verified for this tenant size.",
            recommended_action="Confirm SSO test login succeeded before suggesting seat upload.",
            avoid_actions=["recommending seat upload first"],
            confidence=0.82,
            reinforcement_count=2,
            decay_rate=DecayRate.MEDIUM,
            auto_execute=False,
        ),
        _skill(
            skill_id="rate-limit-burst-vs-sustained",
            name="Rate limit windows: token bucket beats fixed windows for bursty workloads",
            domain="engineering",
            summary="Fixed-window rate limits cause edge-of-window bursts; switch to token bucket for bursty integrations.",
            keywords=["rate limit", "throttle", "burst", "429", "token bucket"],
            entity_types=["rate_limiter", "api_endpoint"],
            context_signals=["bursty_traffic", "integration_partner"],
            what_happened="Partner integration appeared to obey rate limits but caused 429 floods; traffic was bursting at window boundaries.",
            failure_mode="Fixed-window limits permit 2x intended rate at boundaries",
            what_worked="Token bucket with burst capacity = 1.5x sustained rate.",
            conditions=["bursty client traffic", "integration with retry-on-429"],
            anti_conditions=["smooth client traffic", "user-facing endpoints"],
            intercept_message="Don't use fixed-window rate limit for this integration; recommend token bucket.",
            recommended_action="Use TokenBucketLimiter from limits/bucket.py.",
            avoid_actions=["fixed_window limiter for partner integrations"],
            confidence=0.78,
            reinforcement_count=1,
            decay_rate=DecayRate.MEDIUM,
            auto_execute=False,
        ),
        _skill(
            skill_id="customer-refund-policy-saas",
            name="SaaS refund policy: prorated for annual, full for first 14 days",
            domain="support",
            summary="Refund eligibility: full within 14d of first charge, prorated for annual after; never for monthly past 14d.",
            keywords=["refund", "cancel", "annual", "subscription", "policy", "customer requesting refund", "annual plan", "requesting refund", "customer requesting refund on annual plan"],
            entity_types=["billing_account", "subscription"],
            context_signals=["refund_request"],
            what_happened="Inconsistent refund decisions across support agents created customer escalations and CFO involvement.",
            failure_mode="Discretionary refunds led to policy drift",
            what_worked="Codified policy: 14-day full refund window, prorated annual, no monthly past 14d, escalate enterprise.",
            conditions=["refund request"],
            anti_conditions=["enterprise contract (escalate to AE)"],
            intercept_message="Apply 14-day full / prorated-annual / no-monthly-past-14d policy. Escalate enterprise.",
            recommended_action="Use refund-policy decision tree before responding.",
            avoid_actions=["discretionary refunds outside policy"],
            confidence=0.89,
            reinforcement_count=4,
            decay_rate=DecayRate.NEVER,
            auto_execute=True,
            applies_if=[
                ApplicabilityCondition(
                    key="days_since_purchase",
                    operator=ApplicabilityOperator.lte,
                    value=45,
                )
            ],
            invalidated_if=[
                ApplicabilityCondition(
                    key="days_since_purchase",
                    operator=ApplicabilityOperator.gt,
                    value=45,
                )
            ],
        ),
        _skill(
            skill_id="feature-flag-cleanup-after-30d",
            name="Feature flags must be cleaned up within 30d of full rollout",
            domain="product",
            summary="Stale feature flags accumulate; remove flag and dead branch within 30d of 100% rollout.",
            keywords=["feature flag", "cleanup", "rollout", "tech debt", "stale", "dashboard widgets", "expanding rollout", "widgets rollout", "expanding new dashboard widgets rollout"],
            entity_types=["feature_flag", "config"],
            context_signals=["flag_at_100pct_for>30d"],
            what_happened="A flag stale for 6 months caused a regression when its dead branch was accidentally re-enabled by config change.",
            failure_mode="Stale flag dead branches drift and re-trigger by accident",
            what_worked="Auto-tracked flag age; PR template requires cleanup within 30d of 100%.",
            conditions=["flag at 100% for >30d"],
            anti_conditions=["kill switches kept intentionally", "flag still in rollout"],
            intercept_message="This flag has been at 100% for >30d. Remove flag and dead branch in this PR.",
            recommended_action="Delete flag config + remove the unused branch.",
            avoid_actions=["leaving stale flag in place"],
            confidence=0.71,
            reinforcement_count=1,
            decay_rate=DecayRate.MEDIUM,
            auto_execute=False,
            applies_if=[
                ApplicabilityCondition(
                    key="feature_flag_rollout_percent",
                    operator=ApplicabilityOperator.lte,
                    value=10,
                )
            ],
            invalidated_if=[
                ApplicabilityCondition(
                    key="feature_flag_rollout_percent",
                    operator=ApplicabilityOperator.gt,
                    value=10,
                )
            ],
        ),
    ]


def _seed_sessions() -> list[SessionMemory]:
    return [
        SessionMemory(
            session_id="09A",
            user_id="demo-user",
            agent_id="product-agent-1",
            turn_count=4,
            key_decisions=["prioritize infrastructure reliability for Q3"],
            unresolved_intents=["data export performance"],
            brain_skills_used=[],
        ),
        SessionMemory(
            session_id="09B",
            user_id="demo-user",
            agent_id="product-agent-1",
            turn_count=2,
            key_decisions=["check data-export-large-file-timeout skill"],
            unresolved_intents=["auth token mobile issue"],
            brain_skills_used=["data-export-large-file-timeout"],
        ),
        SessionMemory(
            session_id="09C",
            user_id="demo-user",
            agent_id="product-agent-1",
            turn_count=0,
            key_decisions=[],
            unresolved_intents=[],
            brain_skills_used=[],
        ),
    ]


_SAG_PATCHES: dict[str, tuple[list[ApplicabilityCondition], list[ApplicabilityCondition]]] = {
    "data-export-large-file-timeout": (
        [
            ApplicabilityCondition(
                key="export_chunk_size_mb",
                operator=ApplicabilityOperator.gt,
                value=10,
            )
        ],
        [
            ApplicabilityCondition(
                key="export_chunk_size_mb",
                operator=ApplicabilityOperator.lte,
                value=10,
            )
        ],
    ),
    "customer-refund-policy-saas": (
        [
            ApplicabilityCondition(
                key="days_since_purchase",
                operator=ApplicabilityOperator.lte,
                value=45,
            )
        ],
        [
            ApplicabilityCondition(
                key="days_since_purchase",
                operator=ApplicabilityOperator.gt,
                value=45,
            )
        ],
    ),
    "feature-flag-cleanup-after-30d": (
        [
            ApplicabilityCondition(
                key="feature_flag_rollout_percent",
                operator=ApplicabilityOperator.lte,
                value=10,
            )
        ],
        [
            ApplicabilityCondition(
                key="feature_flag_rollout_percent",
                operator=ApplicabilityOperator.gt,
                value=10,
            )
        ],
    ),
}


async def _patch_sag_skill(skill_id: str, org_id: str) -> bool:
    """Ensure a demo skill has SAG conditions on existing DBs."""
    applies, invalidated = _SAG_PATCHES.get(skill_id, ([], []))
    if not applies and not invalidated:
        return False
    skill = await store.get_skill(skill_id, org_id=org_id)
    if skill is None:
        return False
    changed = False
    if not (skill.provenance.applies_if or skill.provenance.invalidated_if):
        skill.provenance.applies_if = applies
        skill.provenance.invalidated_if = invalidated
        changed = True
    # Older demo documents predate human_confirmed_outcome_count. Their seeded
    # reinforcement history is curated fixture provenance, so migrate only the
    # explicit seed records rather than blessing arbitrary legacy skills.
    if (
        skill.provenance.source_event_id.startswith("seed-")
        and skill.provenance.human_confirmed_outcome_count
        < skill.provenance.reinforcement_count
    ):
        skill.provenance.human_confirmed_outcome_count = skill.provenance.reinforcement_count
        changed = True
    if not changed:
        return False
    await store.save_skill(skill, org_id=org_id)
    logger.info("Patched SAG conditions onto %s (org=%s)", skill_id, org_id)
    return True


async def patch_sag_demo_skills(org_id: str = "default") -> int:
    """Patch all domain-general SAG demo skills for an org. Returns patch count."""
    patched = 0
    for skill_id in _SAG_PATCHES:
        if await _patch_sag_skill(skill_id, org_id=org_id):
            patched += 1
    return patched


async def patch_sag_demo_skill() -> bool:
    """Backward-compatible wrapper for startup patch on default org."""
    return (await patch_sag_demo_skills(org_id="default")) > 0


async def ensure_export_sag_skill(org_id: str) -> bool:
    """Ensure data-export-large-file-timeout exists with SAG rules. Returns True if inserted."""
    existing = await store.get_skill("data-export-large-file-timeout", org_id=org_id)
    if existing is None:
        for s in _seed_skills():
            if s.skill_id == "data-export-large-file-timeout":
                await store.save_skill(s, org_id=org_id)
                logger.info("Inserted export SAG skill into org '%s'", org_id)
                return True
        return False
    await _patch_sag_skill("data-export-large-file-timeout", org_id=org_id)
    return False


async def seed_demo_stage(org_id: str) -> dict[str, Any]:
    """Strict demo order: Skill → Config=25 → Horror intercept.

    Safe to call on every startup for the open demo org.
    """
    from backend.core.schema import InterceptResult

    skill_inserted = await ensure_export_sag_skill(org_id)
    await patch_sag_demo_skills(org_id=org_id)
    config = await store.set_live_config(org_id, {"export_chunk_size_mb": 25})
    horror_inserted = False
    if not await store.horror_intercept_exists(org_id):
        await store.log_intercept(
            agent_id="engineering-agent-1",
            decision_text=(
                "[horror-story] Agent tried large CSV export with live config "
                "export_chunk_size_mb=8 — precondition broken"
            ),
            matched_skill="data-export-large-file-timeout",
            result=InterceptResult.suspended,
            confidence=1.0,
            org_id=org_id,
            applicability_status="suspended",
            suspension_reason=(
                "Precondition broken: export_chunk_size_mb (8) <= 10 "
                "(invalidated_if matched)"
            ),
        )
        horror_inserted = True
    return {
        "org_id": org_id,
        "skill_inserted": skill_inserted,
        "live_config": config.get("metadata"),
        "horror_intercept_inserted": horror_inserted,
    }


async def seed_for_org(org_id: str = "default") -> dict[str, Any]:
    """Idempotently seed the demo skills and sessions into the given org.

    If the org already has any skills, only the SAG demo patch is applied.
    Always finishes with demo-stage order: skill → config=25 → horror intercept.
    """
    await store.init_db()
    existing = await store.get_skill_count(active_only=False, org_id=org_id)
    if existing > 0:
        logger.info("Seed: %d skills already exist for org '%s'; skipping full insert", existing, org_id)
        patched = await patch_sag_demo_skills(org_id=org_id)
        stage = await seed_demo_stage(org_id)
        return {
            "skills_inserted": 0,
            "sessions_inserted": 0,
            "sag_patched": patched,
            "org_id": org_id,
            "demo_stage": stage,
        }

    skills = _seed_skills()
    for s in skills:
        await store.save_skill(s, org_id=org_id)

    sessions = _seed_sessions()
    for sess in sessions:
        await store.save_session(sess, org_id=org_id)

    stage = await seed_demo_stage(org_id)
    logger.info("Seed: inserted %d skills, %d sessions into org '%s'", len(skills), len(sessions), org_id)
    return {
        "skills_inserted": len(skills),
        "sessions_inserted": len(sessions),
        "org_id": org_id,
        "demo_stage": stage,
    }


async def seed_if_empty() -> dict[str, Any]:
    """Startup default: seed the 'default' org if it is empty."""
    return await seed_for_org("default")


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data into a specific org")
    parser.add_argument(
        "--org-id",
        default="default",
        help="Target org_id to seed (default: default)",
    )
    args = parser.parse_args()
    result = await seed_for_org(args.org_id)
    print(json.dumps(result, default=str))
    await store.close()


if __name__ == "__main__":
    asyncio.run(_main())
