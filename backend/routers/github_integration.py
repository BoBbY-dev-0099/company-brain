"""GitHub PR webhook intake with durable evidence, audit, and SSE delivery."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, Response

from backend.brain import store
from backend.config import settings
from backend.core import compiler, propagator
from backend.core.schema import RawEvent
from backend.demo.state import assert_demo_org_mutable
from backend.services import rsa_audit

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/github", tags=["integrations"])


def _allowed_repo(full_name: str) -> bool:
    allow = [r.strip() for r in settings.GITHUB_REPOS.split(",") if r.strip()]
    if not allow:
        return True
    return full_name in allow


def _verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    if not secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature_header)


def _event_id(
    delivery_id: str | None,
    repo: str,
    pr_number: Any,
    merge_commit: str | None,
) -> str:
    """Stable delivery identity prevents GitHub retries from compiling twice."""
    identity = delivery_id or f"{repo}:{pr_number}:{merge_commit or ''}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:32]
    return f"github-pr-{digest}"


def _files_changed(pr: dict[str, Any]) -> int | None:
    value = pr.get("changed_files")
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple, set)):
        return len(value)
    return None


def _response_from_event(event: dict[str, Any], *, duplicate: bool) -> dict[str, Any]:
    metadata = event.get("metadata") or {}
    return {
        "ok": True,
        "duplicate": duplicate,
        "event_id": event.get("event_id"),
        "skill_id": event.get("skill_compiled"),
        "audit_id": event.get("audit_id"),
        "workflow_run_id": event.get("workflow_run_id"),
        "workflow_status": event.get("workflow_status"),
        "repo": metadata.get("repo"),
        "pr_number": metadata.get("pr_number"),
        "commit_sha": metadata.get("commit_sha"),
        "html_url": metadata.get("html_url"),
        "source": "github_pr",
        "ingestion_status": event.get("ingestion_status", "completed"),
    }


async def _mark_failed(event: RawEvent, org_id: str, status: str, exc: Exception) -> None:
    try:
        await store.update_event_ingestion(
            event.event_id,
            org_id,
            status,
            error=str(exc),
        )
    except Exception as update_exc:  # noqa: BLE001
        logger.error(
            "could not record GitHub intake failure event=%s: %s",
            event.event_id,
            update_exc,
        )


async def _create_release_safety_workflow(
    event: RawEvent,
    org_id: str,
    saved_skill: Any,
) -> tuple[str, str]:
    """Send a real GitHub intake through the same workflow contract as the UI.

    A PR alone deliberately yields ``review_required`` unless it carries the
    live runtime evidence required by Release Safety.  That is the safe,
    honest behavior: a source connection must not invent telemetry.
    """
    from backend.workflows.models import EvidenceInput, WorkflowRunRequest
    from backend.workflows.service import WorkflowService

    metadata = event.metadata or {}
    context_keys = (
        "worker_memory_mb",
        "runbook_validated",
        "deployment_window_open",
    )
    live_context = {key: metadata[key] for key in context_keys if key in metadata}
    run = await WorkflowService(enable_qwen_compilation=False).run_workflow(
        WorkflowRunRequest(
            template_id="release-safety",
            fixture=False,
            evidence=[
                EvidenceInput(
                    source_type="github_pull_request",
                    source_name="GitHub",
                    external_id=str(metadata.get("github_delivery_id") or event.event_id),
                    url=metadata.get("html_url"),
                    occurred_at=event.occurred_at,
                    excerpt=event.content[:6_000],
                    metadata={
                        "event_id": event.event_id,
                        "repo": metadata.get("repo"),
                        "pr_number": metadata.get("pr_number"),
                        "commit_sha": metadata.get("commit_sha"),
                        "source_payload_sha256": metadata.get("source_payload_sha256"),
                    },
                )
            ],
            live_context=live_context,
            # The intake has already compiled and durably stored this exact PR.
            # The workflow service attaches its source-linked provenance rather
            # than calling Qwen a second time or creating a duplicate skill.
            compiled_skill_id=saved_skill.skill_id,
        ),
        org_id=org_id,
    )
    return run.run_id, run.decision_brief.status.value


async def _complete_intake(
    event: RawEvent,
    event_doc: dict[str, Any],
    org_id: str,
) -> dict[str, Any]:
    """Finish every durable stage before acknowledging a GitHub delivery."""
    saved_skill = None
    saved_skill_id = event_doc.get("skill_compiled")
    if saved_skill_id:
        saved_skill = await store.get_skill(str(saved_skill_id), org_id=org_id)

    if saved_skill is None:
        try:
            skill = await compiler.compile_event_to_skill(event)
            saved_skill = await store.save_skill(skill, org_id=org_id)
            event_doc = await store.update_event_ingestion(
                event.event_id,
                org_id,
                "skill_persisted",
                skill_compiled=saved_skill.skill_id,
            ) or event_doc
        except Exception as exc:  # noqa: BLE001
            logger.exception("GitHub PR skill compile/persist failed")
            await _mark_failed(event, org_id, "compile_failed", exc)
            raise HTTPException(
                status_code=500,
                detail={"error": "QWEN_COMPILE_FAILED", "detail": str(exc)[:400]},
            ) from exc

    if not event_doc.get("audit_id"):
        audit_metadata = {
            "event_id": event.event_id,
            "source": "github_pr",
            "repo": event.metadata.get("repo"),
            "pr_number": event.metadata.get("pr_number"),
            "commit_sha": event.metadata.get("commit_sha"),
            "source_payload_sha256": event.metadata.get("source_payload_sha256"),
        }
        try:
            signed = rsa_audit.sign_decision(
                saved_skill.skill_id,
                audit_metadata,
                decision="github_pr_compiled",
            )
            audit_id = await store.save_audit_log(
                {
                    "org_id": org_id,
                    "skill_id": saved_skill.skill_id,
                    "event_id": event.event_id,
                    "decision": "github_pr_compiled",
                    "metadata": audit_metadata,
                    "signature": signed["signature"],
                    "payload": signed["payload"],
                    "public_key_fingerprint": signed["public_key_fingerprint"],
                    "algorithm": signed["algorithm"],
                    "created_at": signed["timestamp"],
                    "tdx_fallback": True,
                }
            )
            await store.upsert_public_audit_key(
                org_id,
                signed["public_key_fingerprint"],
                rsa_audit.public_key_pem(),
            )
            event_doc = await store.update_event_ingestion(
                event.event_id,
                org_id,
                "audited",
                skill_compiled=saved_skill.skill_id,
                audit_id=audit_id,
            ) or event_doc
        except Exception as exc:  # noqa: BLE001
            logger.exception("GitHub PR audit persistence failed")
            await _mark_failed(event, org_id, "audit_failed", exc)
            raise HTTPException(
                status_code=500,
                detail={"error": "GITHUB_AUDIT_FAILED", "detail": str(exc)[:400]},
            ) from exc

    try:
        await propagator.propagate_skill(
            saved_skill,
            is_new=(saved_skill.version == 1),
            org_id=org_id,
        )
        event_doc = await store.update_event_ingestion(
            event.event_id,
            org_id,
            "sse_propagated",
            skill_compiled=saved_skill.skill_id,
            audit_id=event_doc.get("audit_id"),
        ) or event_doc
    except Exception as exc:  # noqa: BLE001
        logger.exception("GitHub PR SSE propagation failed")
        await _mark_failed(event, org_id, "sse_failed", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "GITHUB_SSE_FAILED", "detail": str(exc)[:400]},
        ) from exc

    if not event_doc.get("workflow_run_id"):
        try:
            workflow_run_id, workflow_status = await _create_release_safety_workflow(
                event,
                org_id,
                saved_skill,
            )
            event_doc = await store.update_event_ingestion(
                event.event_id,
                org_id,
                "workflow_persisted",
                skill_compiled=saved_skill.skill_id,
                audit_id=event_doc.get("audit_id"),
                workflow_run_id=workflow_run_id,
                workflow_status=workflow_status,
            ) or event_doc
        except Exception as exc:  # noqa: BLE001
            logger.exception("GitHub PR workflow persistence failed")
            await _mark_failed(event, org_id, "workflow_failed", exc)
            raise HTTPException(
                status_code=500,
                detail={"error": "GITHUB_WORKFLOW_FAILED", "detail": str(exc)[:400]},
            ) from exc

    event_doc = await store.update_event_ingestion(
        event.event_id,
        org_id,
        "completed",
        skill_compiled=saved_skill.skill_id,
        audit_id=event_doc.get("audit_id"),
        workflow_run_id=event_doc.get("workflow_run_id"),
        workflow_status=event_doc.get("workflow_status"),
    ) or event_doc

    # Mirror the already compiled/audited GitHub event into the shared source
    # ledger.  This adds provenance and Reality Memory without another Qwen
    # call or a second confidence mutation.
    try:
        from backend.sources.service import source_service

        metadata = event.metadata or {}
        await source_service.record_completed_github(
            org_id=org_id,
            external_id=str(metadata.get("github_delivery_id") or event.event_id),
            excerpt=event.content,
            occurred_at=event.occurred_at,
            source_url=metadata.get("html_url"),
            raw_payload_sha256=str(metadata.get("source_payload_sha256") or ""),
            metadata=metadata,
            compiled_skill_id=event_doc.get("skill_compiled"),
            workflow_run_id=event_doc.get("workflow_run_id"),
            workflow_status=event_doc.get("workflow_status"),
        )
    except Exception as exc:  # noqa: BLE001
        # Unit-level intake tests deliberately replace the legacy store without
        # starting Mongo.  A running API always has Mongo from its lifespan;
        # keep that test seam from changing the established GitHub contract.
        if isinstance(exc, RuntimeError) and "Mongo not initialised" in str(exc):
            logger.debug("Skipping source-ledger mirror before Mongo startup")
            return _response_from_event(event_doc, duplicate=False)
        logger.exception("GitHub source-ledger persistence failed")
        await _mark_failed(event, org_id, "source_ledger_failed", exc)
        raise HTTPException(
            status_code=500,
            detail={"error": "GITHUB_SOURCE_LEDGER_FAILED", "detail": str(exc)[:400]},
        ) from exc

    return _response_from_event(event_doc, duplicate=False)


@router.post("/pr")
async def github_pr_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
    x_github_delivery: str | None = Header(default=None),
) -> Any:
    raw = await request.body()
    secret = settings.GITHUB_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(
            status_code=503,
            detail={"error": "GITHUB_WEBHOOK_NOT_CONFIGURED"},
        )
    if not _verify_signature(secret, raw, x_hub_signature_256):
        raise HTTPException(status_code=401, detail={"error": "INVALID_SIGNATURE"})

    if x_github_event != "pull_request":
        return Response(status_code=204)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail={"error": "INVALID_GITHUB_PAYLOAD"}) from exc

    action = payload.get("action")
    pr = payload.get("pull_request") or {}
    if action != "closed" or not pr.get("merged"):
        return Response(status_code=204)

    repo = (payload.get("repository") or {}).get("full_name") or ""
    if not _allowed_repo(repo):
        return Response(status_code=204)

    # Real source adapters share the explicitly configured source org.  The
    # public judge UI and its immutable fixture remain separate from real
    # connector evidence.
    org_id = getattr(request.state, "org_id", None) or settings.SOURCE_ORG_ID
    try:
        assert_demo_org_mutable(org_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "CANONICAL_DEMO_IMMUTABLE", "detail": str(exc)},
        ) from exc

    pr_number = pr.get("number")
    title = pr.get("title") or ""
    body = pr.get("body") or ""
    diff_url = pr.get("diff_url")
    html_url = pr.get("html_url")
    merge_commit = pr.get("merge_commit_sha")
    event_id = _event_id(x_github_delivery, repo, pr_number, merge_commit)

    # A successful GitHub redelivery is acknowledged without another external
    # fetch, Qwen call, confidence change, or SSE event.
    existing = await store.get_event(event_id, org_id=org_id)
    if existing and existing.get("ingestion_status") == "completed":
        return _response_from_event(existing, duplicate=True)

    # If a prior process reached an intermediate durable stage, use its exact
    # normalized evidence to finish the remaining audit/SSE stages.
    if existing:
        try:
            persisted_event = RawEvent.model_validate(existing)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=500,
                detail={"error": "GITHUB_EVENT_RECOVERY_FAILED", "detail": str(exc)[:300]},
            ) from exc
        return await _complete_intake(persisted_event, existing, org_id)

    if not settings.GITHUB_TOKEN:
        raise HTTPException(status_code=502, detail={"error": "GITHUB_TOKEN_MISSING"})
    if not diff_url:
        raise HTTPException(status_code=422, detail={"error": "GITHUB_DIFF_URL_MISSING"})

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            diff_resp = await client.get(
                diff_url,
                headers={
                    "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3.diff",
                    "User-Agent": "company-brain",
                },
            )
            diff_resp.raise_for_status()
            diff_text = diff_resp.text[:12000]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail={"error": "GITHUB_API_FAILURE", "detail": str(exc)[:300]},
        ) from exc

    narrative = (
        f"Merged GitHub PR #{pr_number} in {repo}: {title}\n\n"
        f"{body}\n\nDiff summary:\n{diff_text}"
    )
    event = RawEvent(
        event_id=event_id,
        agent_id="github-integration",
        event_type="resolution",
        content=narrative,
        outcome="merged_pr_compiled",
        org_id=org_id,
        metadata={
            "source": "github_pr",
            "repo": repo,
            "pr_number": pr_number,
            "commit_sha": merge_commit,
            "html_url": html_url,
            "files_changed": _files_changed(pr),
            "github_delivery_id": x_github_delivery,
            "source_payload_sha256": hashlib.sha256(raw).hexdigest(),
        },
    )
    claimed, event_doc = await store.claim_event(event, org_id=org_id)
    if not claimed and event_doc.get("ingestion_status") == "completed":
        return _response_from_event(event_doc, duplicate=True)
    return await _complete_intake(event, event_doc, org_id)
