"""Typed contracts for source ingestion and time-aware Reality Memory."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from backend.core.schema import utc_now


class SourceProvider(str, Enum):
    GITHUB = "github"
    SLACK = "slack"
    ALIBABA_OSS = "alibaba_oss"
    # Kept for migration of pre-OSS records; new ingestion never emits it.
    GOOGLE_DRIVE = "google_drive"
    WEB = "web"


class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    SETUP_REQUIRED = "setup_required"
    CONTRACT_READY = "contract_ready"
    FIXTURE = "fixture"
    PREVIEW = "preview"


class IngestionStage(str, Enum):
    ACCEPTED = "accepted"
    FETCHED = "fetched"
    NORMALIZED = "normalized"
    QWEN_COMPILED = "qwen_compiled"
    RECONCILED = "reconciled"
    DECISION_READY = "decision_ready"
    FAILED = "failed"


class RealityMemoryStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVIEW_REQUIRED = "review_required"


class SourceConnection(BaseModel):
    provider: SourceProvider
    org_id: str
    title: str
    status: ConnectionStatus
    allowed_scope: list[str] = Field(default_factory=list)
    endpoint: str | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    health: str = "not_configured"
    configuration: dict[str, bool | str | int] = Field(default_factory=dict)


class SourceIngestion(BaseModel):
    ingestion_id: str
    provider: SourceProvider
    org_id: str
    external_id: str
    source_type: str
    source_name: str
    # Source timestamp and retrieval timestamp are deliberately separate: a
    # document may be retrieved now while describing an older condition.
    occurred_at: datetime = Field(default_factory=utc_now)
    retrieved_at: datetime = Field(default_factory=utc_now)
    received_at: datetime = Field(default_factory=utc_now)
    source_url: str | None = None
    excerpt: str = ""
    raw_payload_sha256: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    # Server-derived evidence usability fields. Browser clients cannot claim
    # their own freshness, availability, or access boundary.
    freshness: str = "fresh"
    availability: str = "available"
    acl_scope: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    auth_verified: bool = False
    stage: IngestionStage = IngestionStage.ACCEPTED
    attempts: int = 0
    compiled_skill_id: str | None = None
    memory_id: str | None = None
    workflow_run_id: str | None = None
    workflow_status: str | None = None
    qwen_status: str = "pending"
    error: str | None = None
    is_judge_sandbox: bool = False
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RealityMemory(BaseModel):
    memory_id: str
    org_id: str
    claim_key: str
    subject: str
    predicate: str
    scope: str
    claim: str
    status: RealityMemoryStatus = RealityMemoryStatus.ACTIVE
    source_ingestion_ids: list[str] = Field(default_factory=list)
    source_evidence_ids: list[str] = Field(default_factory=list)
    qwen_rationale: str = ""
    qwen_generated: bool = False
    compiled_skill_id: str | None = None
    valid_from: datetime = Field(default_factory=utc_now)
    valid_until: datetime | None = None
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    is_ephemeral: bool = False
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OperationalNote(BaseModel):
    """An agent-authored, evidence-linked note shared across an organization."""

    note_id: str
    org_id: str
    agent_id: str
    subject: str
    scope: str = ""
    claim: str
    evidence_refs: list[str] = Field(default_factory=list)
    memory_id: str | None = None
    qwen_generated: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
