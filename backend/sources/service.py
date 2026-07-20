"""Durable source event processing and Qwen-backed Reality Memory."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.brain import store as brain_store
from backend.config import settings
from backend.core import compiler, propagator
from backend.core.schema import RawEvent
from backend.sources.adapters import AlibabaOSSAdapter, GoogleDriveAdapter, sha256_payload
from backend.sources.models import (
    ConnectionStatus,
    IngestionStage,
    RealityMemory,
    SourceConnection,
    SourceIngestion,
    SourceProvider,
)
from backend.sources.store import SourceRepository, get_source_repository


logger = logging.getLogger(__name__)


def normalise_source_timestamp(value: datetime) -> datetime:
    """Treat legacy Mongo datetimes without tzinfo as UTC.

    Source records are persisted as UTC. PyMongo can return those values as
    naive datetimes depending on its codec settings, so re-ingesting an
    idempotent delivery must not crash freshness calculation.
    """
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def configured_connections(*, org_id: str) -> list[SourceConnection]:
    """Return server-observed configuration, never secret material."""
    github_ready = bool(
        settings.GITHUB_WEBHOOK_SECRET.strip()
        and settings.GITHUB_TOKEN.strip()
        and settings.GITHUB_REPOS.strip()
    )
    slack_ready = bool(
        settings.SLACK_SIGNING_SECRET.strip()
        and settings.SLACK_ALLOWED_TEAM_ID.strip()
        and settings.SLACK_ALLOWED_CHANNEL_IDS.strip()
    )
    oss_ready = AlibabaOSSAdapter.configured()
    web_ready = bool(settings.WEB_EVIDENCE_ALLOWED_HOSTS.strip())
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    # Public nginx serves the SPA at `/` and proxies FastAPI below `/api/`.
    # Provider callbacks must use that public path, while direct local API
    # callers can still use the relative FastAPI path when no base is set.
    def public_api(path: str) -> str:
        return f"{base}/api{path}" if base else path
    return [
        SourceConnection(
            provider=SourceProvider.SLACK,
            org_id=org_id,
            title="Slack incidents",
            status=ConnectionStatus.CONNECTED if slack_ready else ConnectionStatus.SETUP_REQUIRED,
            allowed_scope=["configured workspace", "#ops-incidents only"],
            endpoint=public_api("/integrations/slack/events"),
            health="ready" if slack_ready else "not_configured",
            configuration={
                "signing_secret": bool(settings.SLACK_SIGNING_SECRET.strip()),
                "team_allowlist": bool(settings.SLACK_ALLOWED_TEAM_ID.strip()),
                "channel_allowlist": bool(settings.SLACK_ALLOWED_CHANNEL_IDS.strip()),
                "read_only": True,
            },
        ),
        SourceConnection(
            provider=SourceProvider.ALIBABA_OSS,
            org_id=org_id,
            title="Alibaba OSS runbook",
            status=ConnectionStatus.CONNECTED if oss_ready else ConnectionStatus.SETUP_REQUIRED,
            allowed_scope=["one private bucket prefix", "read-only"],
            endpoint=public_api("/integrations/alibaba-oss/sync"),
            health="ready" if oss_ready else "not_configured",
            configuration={
                "bucket": bool(settings.ALIBABA_OSS_BUCKET.strip()),
                "runbook_prefix": bool(settings.ALIBABA_OSS_PREFIX.strip()),
                "access_key": bool(settings.ALIBABA_OSS_ACCESS_KEY_ID.strip() and settings.ALIBABA_OSS_ACCESS_KEY_SECRET.strip()),
                "read_only": True,
            },
        ),
        SourceConnection(
            provider=SourceProvider.GITHUB,
            org_id=org_id,
            title="GitHub merged pull requests",
            status=ConnectionStatus.CONNECTED if github_ready else ConnectionStatus.SETUP_REQUIRED,
            allowed_scope=["allowlisted repositories", "merged pull requests"],
            endpoint=public_api("/integrations/github/pr"),
            health="ready" if github_ready else "not_configured",
            configuration={
                "webhook_secret": bool(settings.GITHUB_WEBHOOK_SECRET.strip()),
                "repository_allowlist": bool(settings.GITHUB_REPOS.strip()),
                "diff_read_token": bool(settings.GITHUB_TOKEN.strip()),
                "read_only": True,
            },
        ),
        SourceConnection(
            provider=SourceProvider.WEB,
            org_id=org_id,
            title="Verified web evidence",
            status=ConnectionStatus.CONTRACT_READY if web_ready else ConnectionStatus.SETUP_REQUIRED,
            allowed_scope=["configured public HTTPS hosts", "read-only"],
            endpoint=public_api("/integrations/web/fetch"),
            health="ready" if web_ready else "not_configured",
            configuration={"host_allowlist": web_ready, "ssrf_guard": True, "read_only": True},
        ),
    ]


class SourceService:
    def __init__(self, repository: SourceRepository | None = None) -> None:
        self.repository = repository or get_source_repository()

    async def accept(self, ingestion: SourceIngestion) -> tuple[bool, SourceIngestion]:
        now = datetime.now(timezone.utc)
        occurred_at = normalise_source_timestamp(ingestion.occurred_at)
        age_seconds = max(0.0, (now - occurred_at).total_seconds())
        ingestion = ingestion.model_copy(
            update={
                "occurred_at": occurred_at,
                "retrieved_at": now,
                "freshness": "fresh" if age_seconds <= 24 * 60 * 60 else "stale",
                "availability": ingestion.availability or "available",
            }
        )
        claimed, stored = await self.repository.claim(ingestion)
        if claimed:
            connection = next(
                (item for item in configured_connections(org_id=ingestion.org_id) if item.provider == ingestion.provider),
                None,
            )
            if connection is not None:
                await self.repository.upsert_connection(connection)
        return claimed, stored

    @staticmethod
    def _raw_event(ingestion: SourceIngestion) -> RawEvent:
        return RawEvent(
            event_id=f"source-{ingestion.ingestion_id}",
            agent_id=f"{ingestion.provider.value}-source-adapter",
            event_type="source_evidence",
            content=ingestion.excerpt,
            outcome="source_evidence_compiled",
            occurred_at=ingestion.occurred_at,
            org_id=ingestion.org_id,
            metadata={
                "source_provider": ingestion.provider.value,
                "source_ingestion_id": ingestion.ingestion_id,
                "external_id": ingestion.external_id,
                "source_url": ingestion.source_url,
                "raw_payload_sha256": ingestion.raw_payload_sha256,
                **ingestion.metadata,
            },
        )

    @staticmethod
    def _memory_from(
        ingestion: SourceIngestion,
        *,
        skill_id: str | None,
        qwen_rationale: str,
        qwen_generated: bool,
    ) -> RealityMemory:
        metadata = ingestion.metadata
        subject = str(metadata.get("memory_subject") or ingestion.source_name)
        predicate = str(metadata.get("memory_predicate") or "reports")
        scope = str(metadata.get("memory_scope") or ingestion.provider.value)
        claim_key = str(metadata.get("memory_key") or f"{subject}:{predicate}:{scope}").lower()
        claim = qwen_rationale.strip() or ingestion.excerpt.strip() or "Source delivered no usable excerpt."
        stable = hashlib.sha256(
            f"{ingestion.org_id}|{claim_key}|{claim}|{ingestion.ingestion_id}".encode("utf-8")
        ).hexdigest()[:24]
        return RealityMemory(
            memory_id=f"memory-{stable}",
            org_id=ingestion.org_id,
            claim_key=claim_key,
            subject=subject[:160],
            predicate=predicate[:160],
            scope=scope[:240],
            claim=claim[:2000],
            source_ingestion_ids=[ingestion.ingestion_id],
            qwen_rationale=qwen_rationale[:2000],
            qwen_generated=qwen_generated,
            compiled_skill_id=skill_id,
            valid_from=ingestion.occurred_at,
            is_ephemeral=ingestion.is_judge_sandbox,
            expires_at=ingestion.expires_at,
        )

    async def process(self, ingestion: SourceIngestion) -> SourceIngestion:
        """Compile source evidence, reconcile memory, and leave actions to MCP/REST."""
        current = ingestion
        try:
            current = await self.repository.update_ingestion(current, stage=IngestionStage.FETCHED)
            current = await self.repository.update_ingestion(current, stage=IngestionStage.NORMALIZED)
            skill_id: str | None = None
            qwen_generated = False
            qwen_rationale = ""
            qwen_status = "unavailable"
            if settings.QWEN_API_KEY:
                skill = await compiler.compile_event_to_skill(self._raw_event(current))
                if not current.is_judge_sandbox:
                    saved = await brain_store.save_skill(skill, org_id=current.org_id)
                    await brain_store.save_event(
                        self._raw_event(current), skill_compiled=saved.skill_id, org_id=current.org_id
                    )
                    await propagator.propagate_skill(saved, is_new=(saved.version == 1), org_id=current.org_id)
                    skill_id = saved.skill_id
                qwen_generated = True
                qwen_status = "compiled_ephemeral" if current.is_judge_sandbox else "compiled"
                qwen_rationale = skill.summary
                current = await self.repository.update_ingestion(
                    current,
                    stage=IngestionStage.QWEN_COMPILED,
                    compiled_skill_id=skill_id,
                    qwen_status=qwen_status,
                )
            else:
                current = await self.repository.update_ingestion(
                    current,
                    stage=IngestionStage.QWEN_COMPILED,
                    qwen_status=qwen_status,
                )
            memory = await self.repository.reconcile_memory(
                self._memory_from(
                    current,
                    skill_id=skill_id,
                    qwen_rationale=qwen_rationale,
                    qwen_generated=qwen_generated,
                )
            )
            current = await self.repository.update_ingestion(
                current,
                stage=IngestionStage.RECONCILED,
                memory_id=memory.memory_id,
            )
            completed = await self.repository.update_ingestion(current, stage=IngestionStage.DECISION_READY)
            connection = next(
                item for item in configured_connections(org_id=completed.org_id) if item.provider == completed.provider
            )
            connection.last_success_at = completed.updated_at
            connection.health = "healthy"
            await self.repository.upsert_connection(connection)
            return completed
        except Exception as exc:  # noqa: BLE001
            logger.exception("source processing failed ingestion=%s", ingestion.ingestion_id)
            return await self.repository.update_ingestion(
                current, stage=IngestionStage.FAILED, error=str(exc), qwen_status="failed"
            )

    async def process_pending(self, limit: int = 20) -> list[SourceIngestion]:
        return [await self.process(item) for item in await self.repository.pending(limit=limit)]

    async def ingest_oss_documents(self, *, org_id: str) -> list[SourceIngestion]:
        """Read changed runbooks only from the configured private OSS prefix."""
        if not AlibabaOSSAdapter.configured():
            raise RuntimeError("Alibaba Cloud OSS is not configured")
        existing = await self.repository.list_ingestions(org_id, limit=100)
        previous = [item.occurred_at for item in existing if item.provider == SourceProvider.ALIBABA_OSS]
        modified_after = max(previous).isoformat().replace("+00:00", "Z") if previous else None
        adapter = AlibabaOSSAdapter()
        documents = await adapter.list_documents(modified_after=modified_after)
        accepted: list[SourceIngestion] = []
        for document in documents:
            excerpt = await adapter.read_document(document)
            occurred_at = datetime.fromisoformat(
                str(document.get("last_modified") or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            )
            object_key = str(document.get("key") or "")
            content_sha256 = sha256_payload(excerpt)
            external_id = f"{object_key}:{content_sha256[:24]}"
            ingestion = SourceIngestion(
                ingestion_id=f"oss-{hashlib.sha256(external_id.encode()).hexdigest()[:24]}",
                provider=SourceProvider.ALIBABA_OSS,
                org_id=org_id,
                external_id=external_id,
                source_type="alibaba_oss_object",
                source_name="Alibaba Cloud OSS runbook",
                source_url=f"oss://{settings.ALIBABA_OSS_BUCKET.strip()}/{object_key}",
                occurred_at=occurred_at,
                excerpt=excerpt,
                raw_payload_sha256=sha256_payload(document),
                raw_payload=document,
                auth_verified=True,
                metadata={
                    "object_key": object_key,
                    "content_sha256": content_sha256,
                    "content_type": document.get("content_type"),
                    "memory_subject": object_key.rsplit("/", 1)[-1] or "OSS runbook policy",
                    "memory_predicate": "states",
                    "memory_scope": f"oss://{settings.ALIBABA_OSS_BUCKET.strip()}/{settings.ALIBABA_OSS_PREFIX.strip()}",
                },
                acl_scope=[
                    f"oss_bucket:{settings.ALIBABA_OSS_BUCKET.strip()}",
                    f"oss_prefix:{settings.ALIBABA_OSS_PREFIX.strip()}",
                    "read_only",
                ],
            )
            claimed, stored = await self.accept(ingestion)
            if claimed:
                accepted.append(stored)
        return accepted

    async def ingest_drive_documents(self, *, org_id: str) -> list[SourceIngestion]:
        """Legacy migration shim; new deployments use :meth:`ingest_oss_documents`."""
        if not GoogleDriveAdapter.configured():
            raise RuntimeError("Google Drive migration adapter is not configured")
        existing = await self.repository.list_ingestions(org_id, limit=100)
        previous = [item.occurred_at for item in existing if item.provider == SourceProvider.GOOGLE_DRIVE]
        modified_after = max(previous).isoformat().replace("+00:00", "Z") if previous else None
        adapter = GoogleDriveAdapter()
        documents = await adapter.list_documents(modified_after=modified_after)
        accepted: list[SourceIngestion] = []
        for document in documents:
            excerpt = await adapter.read_document(document)
            occurred_at = datetime.fromisoformat(
                str(document.get("modifiedTime") or datetime.now(timezone.utc).isoformat()).replace("Z", "+00:00")
            )
            file_id = str(document.get("id") or "")
            content_sha256 = sha256_payload(excerpt)
            external_id = f"{file_id}:{content_sha256[:24]}"
            ingestion = SourceIngestion(
                ingestion_id=f"drive-{hashlib.sha256(external_id.encode()).hexdigest()[:24]}",
                provider=SourceProvider.GOOGLE_DRIVE,
                org_id=org_id,
                external_id=external_id,
                source_type="google_drive_document",
                source_name="Google Drive migration record",
                source_url=document.get("webViewLink"),
                occurred_at=occurred_at,
                excerpt=excerpt,
                raw_payload_sha256=sha256_payload(document),
                raw_payload=document,
                auth_verified=True,
                metadata={
                    "file_id": file_id,
                    "content_sha256": content_sha256,
                    "mime_type": document.get("mimeType"),
                    "memory_subject": document.get("name") or "Legacy runbook policy",
                    "memory_predicate": "states",
                    "memory_scope": "legacy migration",
                },
                acl_scope=[f"drive_folder:{settings.GOOGLE_DRIVE_FOLDER_ID}", "read_only"],
            )
            claimed, stored = await self.accept(ingestion)
            if claimed:
                accepted.append(stored)
        return accepted

    async def record_completed_github(
        self,
        *,
        org_id: str,
        external_id: str,
        excerpt: str,
        occurred_at: datetime,
        source_url: str | None,
        raw_payload_sha256: str,
        metadata: dict[str, Any],
        compiled_skill_id: str | None,
        workflow_run_id: str | None,
        workflow_status: str | None,
    ) -> SourceIngestion:
        """Mirror the established GitHub intake in the common source ledger.

        GitHub already compiled/audited the exact event before this helper is
        reached, so this method links that immutable work rather than making a
        second Qwen call.
        """
        stable = hashlib.sha256(f"github|{org_id}|{external_id}".encode("utf-8")).hexdigest()[:24]
        ingestion = SourceIngestion(
            ingestion_id=f"github-{stable}",
            provider=SourceProvider.GITHUB,
            org_id=org_id,
            external_id=external_id,
            source_type="github_pull_request",
            source_name="GitHub",
            source_url=source_url,
            occurred_at=occurred_at,
            excerpt=excerpt[:20000],
            raw_payload_sha256=raw_payload_sha256,
            raw_payload={"external_id": external_id, "source": "github_pr"},
            metadata={
                "memory_subject": metadata.get("repo") or "GitHub change",
                "memory_predicate": "changed",
                "memory_scope": metadata.get("repo") or "allowlisted repository",
                **metadata,
            },
            auth_verified=True,
            acl_scope=[f"repository:{metadata.get('repo') or 'allowlisted'}", "merged_pull_request"],
        )
        claimed, stored = await self.accept(ingestion)
        if not claimed:
            return stored
        staged = await self.repository.update_ingestion(stored, stage=IngestionStage.FETCHED)
        staged = await self.repository.update_ingestion(staged, stage=IngestionStage.NORMALIZED)
        qwen_rationale = ""
        if compiled_skill_id:
            skill = await brain_store.get_skill(compiled_skill_id, org_id=org_id)
            qwen_rationale = skill.summary if skill else ""
        staged = await self.repository.update_ingestion(
            staged,
            stage=IngestionStage.QWEN_COMPILED,
            compiled_skill_id=compiled_skill_id,
            qwen_status="compiled" if compiled_skill_id else "unavailable",
        )
        memory = await self.repository.reconcile_memory(
            self._memory_from(
                staged,
                skill_id=compiled_skill_id,
                qwen_rationale=qwen_rationale,
                qwen_generated=bool(compiled_skill_id),
            )
        )
        staged = await self.repository.update_ingestion(
            staged,
            stage=IngestionStage.RECONCILED,
            memory_id=memory.memory_id,
        )
        completed = await self.repository.update_ingestion(
            staged,
            stage=IngestionStage.DECISION_READY,
            workflow_run_id=workflow_run_id,
            workflow_status=workflow_status,
        )
        connection = next(item for item in configured_connections(org_id=org_id) if item.provider == SourceProvider.GITHUB)
        connection.last_success_at = completed.updated_at
        connection.health = "healthy"
        await self.repository.upsert_connection(connection)
        return completed


source_service = SourceService()
