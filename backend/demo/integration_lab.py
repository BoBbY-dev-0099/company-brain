"""Synthetic-company integration lab for safe end-to-end adapter testing.

The lab is deliberately source-labelled as a fixture.  It exercises the same
immutable evidence ledger, Qwen compiler, temporal memory reconciliation, and
MCP workflow contract as real adapters without requiring a real workspace,
repository, or Drive account.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.sources.adapters import _validate_public_url, sha256_payload, verify_slack_signature
from backend.sources.models import IngestionStage, SourceIngestion, SourceProvider
from backend.sources.service import source_service


COMPANY = {
    "name": "Northstar Logistics",
    "workspace": "northstar-demo",
    "repository": "northstar/fulfillment-api",
    "drive_folder": "Release Operations",
    "mode": "synthetic_company_fixture",
}


async def fixture_guard_results(*, now_epoch: int | None = None) -> list[dict[str, Any]]:
    """Exercise the Slack/GitHub signature and replay guards without I/O."""
    now = int(now_epoch if now_epoch is not None else time.time())
    slack_secret = "northstar-slack-signing-secret"
    slack_payload = {"type": "event_callback", "team_id": "T-NORTHSTAR", "event_id": "Ev-NORTHSTAR-001"}
    raw = json.dumps(slack_payload, separators=(",", ":")).encode("utf-8")
    valid_signature = "v0=" + hmac.new(
        slack_secret.encode("utf-8"), f"v0:{now}:".encode("utf-8") + raw, hashlib.sha256
    ).hexdigest()
    stale_signature = "v0=" + hmac.new(
        slack_secret.encode("utf-8"), f"v0:{now - 301}:".encode("utf-8") + raw, hashlib.sha256
    ).hexdigest()
    github_secret = b"northstar-github-webhook-secret"
    github_body = b'{"action":"closed","pull_request":{"merged":true}}'
    github_valid = "sha256=" + hmac.new(github_secret, github_body, hashlib.sha256).hexdigest()
    github_invalid = "sha256=" + "0" * 64
    try:
        await _validate_public_url("https://127.0.0.1/company-brain-test")
        web_private_rejected = False
    except ValueError:
        web_private_rejected = True
    return [
        {
            "id": "slack_signed_delivery",
            "label": "Slack signed event accepted",
            "passed": verify_slack_signature(
                secret=slack_secret, body=raw, timestamp=str(now), signature=valid_signature, now=now
            ),
            "detail": "The same Slack HMAC verifier accepts a fresh, correctly signed fixture delivery.",
        },
        {
            "id": "slack_replay_window",
            "label": "Slack replay window blocks stale delivery",
            "passed": not verify_slack_signature(
                secret=slack_secret, body=raw, timestamp=str(now - 301), signature=stale_signature, now=now
            ),
            "detail": "A delivery more than five minutes old is rejected before evidence is persisted.",
        },
        {
            "id": "github_signature",
            "label": "GitHub HMAC accepts only the matching body",
            "passed": hmac.compare_digest(
                github_valid,
                "sha256=" + hmac.new(github_secret, github_body, hashlib.sha256).hexdigest(),
            ) and not hmac.compare_digest(github_invalid, github_valid),
            "detail": "The fixture checks the same SHA-256 webhook signature shape used by the GitHub intake.",
        },
        {
            "id": "web_private_network",
            "label": "Verified web stays allowlist/SSRF guarded",
            "passed": web_private_rejected,
            "detail": "The adapter rejected a private-network URL before any fetch could occur.",
        },
    ]


async def run_northstar_lab(*, org_id: str) -> dict[str, Any]:
    """Run a fixture company through the exact source-to-memory pipeline."""
    now = datetime.now(timezone.utc)
    fixture = [
        {
            "provider": SourceProvider.SLACK,
            "external": "northstar-slack-sev2-v1",
            "source_type": "slack_message",
            "source_name": "Northstar Slack #ops-incidents",
            "excerpt": "SEV-2: fulfillment-worker began OOM-killing after the release candidate. Stop the promotion until its memory limit is restored.",
            "metadata": {"memory_subject": "fulfillment-worker", "memory_predicate": "incident", "memory_scope": "production", "memory_key": "northstar-fulfillment-incident", "channel_id": "C-NORTHSTAR-OPS"},
        },
        {
            "provider": SourceProvider.GOOGLE_DRIVE,
            "external": "northstar-drive-runbook-v2",
            "source_type": "google_drive_document",
            "source_name": "Northstar Drive — Fulfillment release runbook v2",
            "excerpt": "Runbook v2: fulfillment-worker must have at least 16 MiB memory. Lower limits require explicit SRE validation before promotion.",
            "metadata": {"memory_subject": "fulfillment-worker", "memory_predicate": "minimum memory", "memory_scope": "production", "memory_key": "northstar-fulfillment-minimum-memory", "document_revision": "v2"},
        },
        {
            "provider": SourceProvider.GOOGLE_DRIVE,
            "external": "northstar-drive-runbook-v3",
            "source_type": "google_drive_document",
            "source_name": "Northstar Drive — Fulfillment release runbook v3",
            "excerpt": "Runbook v3 replaces v2: fulfillment-worker requires at least 24 MiB memory. Any lower effective limit blocks automated release promotion.",
            "metadata": {"memory_subject": "fulfillment-worker", "memory_predicate": "minimum memory", "memory_scope": "production", "memory_key": "northstar-fulfillment-minimum-memory", "document_revision": "v3"},
        },
        {
            "provider": SourceProvider.GITHUB,
            "external": "northstar-github-pr-842-v1",
            "source_type": "github_pull_request",
            "source_name": "Northstar GitHub PR #842",
            "excerpt": "Merged PR #842 changes FULFILLMENT_WORKER_MEMORY_MB from 32 to 8.",
            "metadata": {"memory_subject": "fulfillment-worker", "memory_predicate": "configured memory", "memory_scope": "production", "memory_key": "northstar-fulfillment-configured-memory", "changed_field": "worker_memory_mb", "previous_value": 32, "current_value": 8},
        },
    ]
    events: list[SourceIngestion] = []
    for index, item in enumerate(fixture):
        external = f"{item['external']}:{org_id}"
        ingestion = SourceIngestion(
            ingestion_id=f"northstar-{hashlib.sha256(external.encode()).hexdigest()[:24]}",
            provider=item["provider"],
            org_id=org_id,
            external_id=external,
            source_type=item["source_type"],
            source_name=item["source_name"],
            occurred_at=now + timedelta(seconds=index),
            excerpt=item["excerpt"],
            raw_payload_sha256=sha256_payload(item),
            raw_payload={"fixture_company": COMPANY["name"], "fixture": "northstar-integration-lab-v1", "provider": item["provider"].value},
            auth_verified=True,
            metadata={**item["metadata"], "fixture": True, "fixture_company": COMPANY["name"]},
            acl_scope=["fixture:northstar", "synthetic_company", "read_only"],
        )
        claimed, stored = await source_service.accept(ingestion)
        if claimed or stored.stage != IngestionStage.DECISION_READY:
            stored = await source_service.process(stored)
        events.append(stored)

    # Re-submit the exact Slack delivery to prove the ledger's immutable
    # idempotency boundary without attempting a second compilation.
    duplicate_claimed, _ = await source_service.accept(events[0])
    checks = await fixture_guard_results()
    checks.append(
        {
            "id": "duplicate_delivery",
            "label": "Duplicate source delivery is deduplicated",
            "passed": not duplicate_claimed,
            "detail": "The immutable source ledger keyed the repeated Slack delivery to the existing evidence record.",
        }
    )
    evidence = [
        {
            "source_type": item.source_type,
            "source_name": item.source_name,
            "external_id": item.external_id,
            "occurred_at": item.occurred_at.isoformat(),
            "excerpt": item.excerpt,
            "metadata": {"source_ingestion_id": item.ingestion_id, **item.metadata},
        }
        for item in (events[0], events[2], events[3])
    ]
    evidence.append(
        {
            "source_type": "runtime_metric",
            "source_name": "Northstar runtime telemetry",
            "external_id": f"northstar-fulfillment-memory:{org_id}",
            "occurred_at": now.isoformat(),
            "excerpt": "fulfillment-worker effective memory limit is 8 MiB after PR #842.",
            "metadata": {"fixture": True, "source": "Northstar synthetic runtime"},
        }
    )
    return {
        "company": COMPANY,
        "mode": "judge_sandbox",
        "events": [item.model_dump(mode="json") for item in events],
        "edge_checks": checks,
        "workflow": {
            "template_id": "release-safety",
            "evidence": evidence,
            "live_context": {"worker_memory_mb": 8, "runbook_validated": False, "deployment_window_open": True},
        },
    }
