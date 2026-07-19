"""Durable source event processing and Qwen-backed Reality Memory."""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.brain import store as brain_store
from backend.config import settings
from backend.demo.judge_session import is_judge_sandbox_org
from backend.core import compiler, propagator
from backend.core.schema import RawEvent
from backend.sources.adapters import GoogleDriveAdapter, sha256_payload
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
    drive_ready = GoogleDriveAdapter.configured()
    web_ready = bool(settings.WEB_EVIDENCE_ALLOWED_HOSTS.strip())
    base = settings.PUBLIC_BASE_URL.rstrip("/")
    return [
        SourceConnection(
            provider=SourceProvider.SLACK,
            org_id=org_id,
            title="Slack incidents",
            status=ConnectionStatus.CONNECTED if slack_ready else ConnectionStatus.SETUP_REQUIRED,
            allowed_scope=["configured workspace", "#ops-incidents only"],
            endpoint=f"{base}/integrations/slack/events" if base else "/integrations/slack/events",
            health="ready" if slack_ready else "not_configured",
            configuration={
                "signing_secret": bool(settings.SLACK_SIGNING_SECRET.strip()),
                "team_allowlist": bool(settings.SLACK_ALLOWED_TEAM_ID.strip()),
                "channel_allowlist": bool(settings.SLACK_ALLOWED_CHANNEL_IDS.strip()),
                "read_only": True,
            },
        ),
        SourceConnection(
            provider=SourceProvider.GOOGLE_DRIVE,
            org_id=org_id,
            title="Google Drive policy",
            status=ConnectionStatus.CONNECTED if drive_ready else ConnectionStatus.SETUP_REQUIRED,
            allowed_scope=["one explicitly shared folder", "read-only"],
            endpoint=f"{base}/integrations/google-drive/sync" if base else "/integrations/google-drive/sync",
            health="ready" if drive_ready else "not_configured",
            configuration={
                "service_account": bool(settings.GOOGLE_SERVICE_ACCOUNT_JSON.strip() or settings.GOOGLE_SERVICE_ACCOUNT_FILE.strip()),
                "shared_folder": bool(settings.GOOGLE_DRIVE_FOLDER_ID.strip()),
                "read_only": True,
            },
        ),
        SourceConnection(
            provider=SourceProvider.GITHUB,
            org_id=org_id,
            title="GitHub merged pull requests",
            status=ConnectionStatus.CONNECTED if github_ready else ConnectionStatus.SETUP_REQUIRED,
            allowed_scope=["allowlisted repositories", "merged pull requests"],
            endpoint=f"{base}/integrations/github/pr" if base else "/integrations/github/pr",
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
            endpoint=f"{base}/integrations/web/fetch" if base else "/integrations/web/fetch",
            health="ready" if web_ready else "not_configured",
            configuration={"host_allowlist": web_ready, "ssrf_guard": True, "read_only": True},
        ),
    ]


class SourceService:
    def __init__(self, repository: SourceRepository | None = None) -> None:
        self.repository = repository or get_source_repository()

    async def accept(self, ingestion: SourceIngestion) -> tuple[bool, SourceIngestion]:
        now = datetime.now(timezone.utc)
        age_seconds = max(0.0, (now - ingestion.occurred_at).total_seconds())
        ingestion = ingestion.model_copy(
            update={
                "retrieved_at": now,
                "freshness": "fresh" if age_seconds <= 24 * 60 * 60 else "stale",
                "availability": ingestion.availability or "available",
            }
        )
        if is_judge_sandbox_org(ingestion.org_id):
            from datetime import timedelta

            ingestion = ingestion.model_copy(
                update={
                    "is_judge_sandbox": True,
                    "expires_at": ingestion.received_at + timedelta(seconds=settings.JUDGE_SANDBOX_TTL_SECONDS),
                }
            )
        claimed, stored = await self.repository.claim(ingestion)
        if claimed:
            await self.repository.upsert_connection(
                next(item for item in configured_connections(org_id=ingestion.org_id) if item.provider == ingestion.provider)
            )
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

    async def ingest_drive_documents(self, *, org_id: str) -> list[SourceIngestion]:
        """Read changed documents only from the configured shared folder."""
        if not GoogleDriveAdapter.configured():
            raise RuntimeError("Google Drive is not configured")
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
                # The immutable ledger keeps a new version when document
                # content changes, instead of silently replacing a prior
                # policy claim with a newer Drive fetch.
                external_id=external_id,
                source_type="google_drive_document",
                source_name="Google Drive",
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
                    "memory_subject": document.get("name") or "Drive policy",
                    "memory_predicate": "states",
                    "memory_scope": "configured shared folder",
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
