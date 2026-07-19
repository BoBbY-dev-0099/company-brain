"""Evidence-backed NexaFlow Logistics scenarios for the public judge lab.

The lab deliberately implements the four source/memory scenarios that Company
Brain can prove today: conflicting policies, stale ownership, cross-agent
handoff, and absence-of-evidence.  Every record is a labelled fixture that
travels through the normal source ledger and Qwen compiler; the final answer is
deterministic and cites the evidence boundary rather than pretending a model
has established an unsupported fact.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from backend.sources.adapters import sha256_payload
from backend.sources.models import SourceIngestion, SourceProvider
from backend.sources.service import source_service


COMPANY = {
    "name": "NexaFlow Logistics",
    "workspace": "nexaflow-demo",
    "repository": "nexaflow/platform-api",
    "mode": "synthetic_company_fixture",
}


def _at(year: int, month: int, day: int, hour: int = 9, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


SCENARIOS: dict[str, dict[str, Any]] = {
    "sla-conflict": {
        "title": "Conflicting enterprise SLA",
        "question": "What is NexaFlow's standard SLA for enterprise clients?",
        "summary": "An old policy, a newer sales announcement, and an account note disagree. Company Brain must not silently select the old policy.",
        "agent_query": "enterprise SLA",
        "answer": {
            "status": "conflict_detected",
            "headline": "Do not treat the 48-hour wiki value as the current enterprise SLA.",
            "confidence": "low_for_48_hour_claim",
            "response": "The historical wiki says 48 hours, while a newer #sales announcement changes Tier 1 to 24 hours. A customer account note records a recent 24-hour miss but is not itself a policy source. Verify the currently approved SLA before responding.",
            "recommended_action": "Ask the sales or policy owner to confirm the current approved enterprise SLA and update the governed policy source.",
            "missing_evidence": ["A current, approved enterprise SLA policy after the March 2026 sales announcement."],
        },
        "sources": [
            {
                "provider": SourceProvider.GOOGLE_DRIVE,
                "external": "nexaflow-sla-wiki-2024",
                "source_type": "google_drive_document",
                "source_name": "NexaFlow SLA wiki — 2024 policy snapshot",
                "occurred_at": _at(2024, 6, 12),
                "excerpt": "Enterprise client response SLA: 48 hours.",
                "role": "historical_policy",
            },
            {
                "provider": SourceProvider.SLACK,
                "external": "nexaflow-sales-sla-march-2026",
                "source_type": "slack_message",
                "source_name": "NexaFlow Slack #sales — March 2026 announcement",
                "occurred_at": _at(2026, 3, 18, 14),
                "excerpt": "Tier 1 enterprise response target moved from 48 hours to 24 hours. Update customer-facing materials after policy approval.",
                "role": "newer_policy_signal",
            },
            {
                "provider": SourceProvider.WEB,
                "external": "nexaflow-crm-acme-sla-note-2026",
                "source_type": "fixture_crm_note",
                "source_name": "Fixture CRM account note — Acme (not a live CRM connector)",
                "occurred_at": _at(2026, 7, 11, 11),
                "excerpt": "Acme reported that the 24-hour response target was missed last week.",
                "role": "customer_outcome_not_policy",
            },
        ],
        "memory": {"subject": "Enterprise SLA", "predicate": "response target", "scope": "Tier 1 enterprise", "key": "nexaflow-enterprise-sla"},
    },
    "stale-owner": {
        "title": "Stale decision-maker",
        "question": "Who is the decision-maker at Acme Corp?",
        "summary": "A stale contact record conflicts with newer departure and ownership evidence. The prior contact must remain auditable but cannot be treated as current.",
        "agent_query": "Acme Corp",
        "answer": {
            "status": "superseded",
            "headline": "Sarah Chen is the current working owner; John Smith is a historical contact only.",
            "confidence": "medium",
            "response": "The January account record lists John Smith. A later public-profile fixture says he left in April, and a May Slack handoff assigns Sarah Chen as Acme's operations owner. Company Brain superseded the old contact record and preserves its lineage for audit.",
            "recommended_action": "Route the account question to Sarah Chen and verify the customer-facing contact record before sending an external message.",
            "missing_evidence": ["A customer-confirmed contact update or an executed account-plan change."],
        },
        "sources": [
            {
                "provider": SourceProvider.WEB,
                "external": "nexaflow-crm-acme-owner-jan-2026",
                "source_type": "fixture_crm_note",
                "source_name": "Fixture CRM account owner — January 2026 (not a live CRM connector)",
                "occurred_at": _at(2026, 1, 9),
                "excerpt": "Acme decision-maker: John Smith, VP Operations.",
                "role": "stale_account_record",
            },
            {
                "provider": SourceProvider.WEB,
                "external": "nexaflow-public-profile-acme-apr-2026",
                "source_type": "verified_public_profile_fixture",
                "source_name": "Verified public-profile snapshot — fixture",
                "occurred_at": _at(2026, 4, 16),
                "excerpt": "John Smith left Acme Corp in April 2026.",
                "role": "departure_signal",
            },
            {
                "provider": SourceProvider.SLACK,
                "external": "nexaflow-slack-acme-owner-may-2026",
                "source_type": "slack_message",
                "source_name": "NexaFlow Slack #sales — Acme handoff",
                "occurred_at": _at(2026, 5, 7, 15),
                "excerpt": "Sarah Chen took over Acme's operations account after John Smith left. Confirm with Acme before external commitments.",
                "role": "newer_owner_assignment",
            },
        ],
        "memory": {"subject": "Acme Corp", "predicate": "decision-maker", "scope": "customer account", "key": "nexaflow-acme-decision-maker"},
    },
    "agent-handoff": {
        "title": "Sales to Customer Success handoff",
        "question": "Should Customer Success mention the API latency fix to Acme?",
        "summary": "A Sales agent records a customer concern; a later GitHub change revises the operational context. MCP lets the next agent read the same governed memory.",
        "agent_query": "Acme Corp",
        "answer": {
            "status": "context_updated",
            "headline": "Mention the deployed latency fix, but state that customer validation is still pending.",
            "confidence": "medium",
            "response": "The Sales handoff records API latency as Acme's top concern. A newer merged GitHub PR says the deployed change reduced latency by 40%. The concern may be resolved, but no client validation evidence is present, so Company Brain keeps the confidence calibrated.",
            "recommended_action": "Customer Success should mention the fix, ask Acme to validate it, and record the outcome before treating the concern as resolved.",
            "missing_evidence": ["Acme confirmation that the observed API latency is acceptable after the deployment."],
        },
        "sources": [
            {
                "provider": SourceProvider.SLACK,
                "external": "nexaflow-sales-to-cs-handoff",
                "source_type": "agent_handoff",
                "source_name": "Sales agent handoff — fixture",
                "occurred_at": _at(2026, 7, 19, 7),
                "excerpt": "Acme Corp signed a $50K contract. Their key concern is API latency; Customer Success should track it during onboarding.",
                "role": "sales_agent_handoff",
            },
            {
                "provider": SourceProvider.GITHUB,
                "external": "nexaflow-github-api-latency-fix-556",
                "source_type": "github_pull_request",
                "source_name": "NexaFlow GitHub PR #556",
                "occurred_at": _at(2026, 7, 19, 8, 30),
                "excerpt": "Merged PR #556 deployed the API queue fix. Benchmark: p95 API latency reduced 40%. Customer validation is not yet recorded.",
                "role": "engineering_context_update",
            },
        ],
        "memory": {"subject": "Acme Corp", "predicate": "API latency concern", "scope": "customer handoff", "key": "nexaflow-acme-api-latency"},
    },
    "absence-of-evidence": {
        "title": "No confirmed commitment",
        "question": "Did NexaFlow promise Acme a dedicated account manager?",
        "summary": "Generic marketing and an unsigned template are not evidence of a customer-specific promise. Company Brain must say what is missing rather than invent a commitment.",
        "agent_query": "Acme Corp",
        "answer": {
            "status": "review_required",
            "headline": "No confirmed Acme-specific dedicated account-manager promise was found.",
            "confidence": "low",
            "response": "A generic sales deck mentions dedicated account managers for enterprise customers, and an unsigned contract template contains a similar clause. Neither proves a commitment to Acme. There is no executed contract or client-specific confirmation in this fixture set.",
            "recommended_action": "Ask the sales owner to verify the executed Acme contract or written client commitment before making a promise.",
            "missing_evidence": ["An executed Acme contract with the dedicated-account-manager clause.", "A customer-specific written commitment from an authorized NexaFlow owner."],
        },
        "sources": [
            {
                "provider": SourceProvider.GOOGLE_DRIVE,
                "external": "nexaflow-enterprise-sales-deck",
                "source_type": "google_drive_document",
                "source_name": "NexaFlow enterprise sales deck — generic",
                "occurred_at": _at(2026, 6, 1),
                "excerpt": "Enterprise plans may include a dedicated account manager depending on the signed service package.",
                "role": "generic_marketing_material",
            },
            {
                "provider": SourceProvider.GOOGLE_DRIVE,
                "external": "nexaflow-contract-template-am",
                "source_type": "google_drive_document",
                "source_name": "NexaFlow enterprise contract template — unsigned",
                "occurred_at": _at(2026, 6, 3),
                "excerpt": "Template clause: a dedicated account manager may be assigned when specified in an executed order form.",
                "role": "unsigned_template_not_commitment",
            },
        ],
        "memory": {"subject": "Acme Corp", "predicate": "dedicated account manager commitment", "scope": "customer contract", "key": "nexaflow-acme-dedicated-am"},
    },
}


def scenario_catalog() -> list[dict[str, str]]:
    """Return only server-owned labels for the judge-facing scenario selector."""
    return [
        {
            "id": scenario_id,
            "title": item["title"],
            "question": item["question"],
            "summary": item["summary"],
        }
        for scenario_id, item in SCENARIOS.items()
    ]


async def run_nexaflow_scenario(*, scenario_id: str, org_id: str) -> dict[str, Any]:
    """Process one labelled fixture scenario through evidence and Reality Memory."""
    scenario = SCENARIOS.get(scenario_id)
    if scenario is None:
        raise KeyError(scenario_id)

    memory_meta = scenario["memory"]
    events: list[SourceIngestion] = []
    for source in scenario["sources"]:
        external_id = f"{source['external']}:{org_id}"
        stable = hashlib.sha256(external_id.encode("utf-8")).hexdigest()[:24]
        payload = {
            "fixture_company": COMPANY["name"],
            "fixture": "nexaflow-reality-lab-v1",
            "scenario": scenario_id,
            "source": source["external"],
            "role": source["role"],
        }
        ingestion = SourceIngestion(
            ingestion_id=f"nexaflow-{stable}",
            provider=source["provider"],
            org_id=org_id,
            external_id=external_id,
            source_type=source["source_type"],
            source_name=source["source_name"],
            occurred_at=source["occurred_at"],
            excerpt=source["excerpt"],
            raw_payload_sha256=sha256_payload(payload),
            raw_payload=payload,
            auth_verified=True,
            metadata={
                "fixture": True,
                "fixture_company": COMPANY["name"],
                "fixture_scenario": scenario_id,
                "evidence_role": source["role"],
                "memory_subject": memory_meta["subject"],
                "memory_predicate": memory_meta["predicate"],
                "memory_scope": memory_meta["scope"],
                "memory_key": memory_meta["key"],
            },
            acl_scope=["fixture:nexaflow", "synthetic_company", "read_only"],
        )
        claimed, stored = await source_service.accept(ingestion)
        if claimed or stored.stage.value != "decision_ready":
            stored = await source_service.process(stored)
        events.append(stored)

    memories = []
    for event in events:
        if event.memory_id:
            memory = await source_service.repository.get_memory(org_id, event.memory_id)
            if memory:
                memories.append(memory)

    answer = scenario["answer"]
    return {
        "company": COMPANY,
        "mode": "judge_sandbox",
        "scenario": {
            "id": scenario_id,
            "title": scenario["title"],
            "question": scenario["question"],
            "summary": scenario["summary"],
            "agent_query": scenario["agent_query"],
        },
        "events": [event.model_dump(mode="json") for event in events],
        "memories": [memory.model_dump(mode="json") for memory in memories],
        "answer": {
            **answer,
            "generated_by": "deterministic evidence policy",
            "qwen_boundary": "Qwen compiles each source into Reality Memory. This conclusion is deterministic and cites what is missing; it is not a fabricated model answer.",
        },
    }
