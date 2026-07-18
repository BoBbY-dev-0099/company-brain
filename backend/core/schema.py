from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecayRate(str, Enum):
    SLOW = "slow"
    MEDIUM = "medium"
    FAST = "fast"
    NEVER = "never"


class SkillAction(str, Enum):
    BLOCK = "block"
    WARN = "warn"
    AUTO_EXECUTE = "auto_execute"
    ESCALATE = "escalate"
    NONE = "none"


class ApplicabilityOperator(str, Enum):
    eq = "eq"
    neq = "neq"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    in_ = "in_"
    not_in = "not_in"
    exists = "exists"
    not_exists = "not_exists"


class ApplicabilityStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    unknown = "unknown"


class ApplicabilityCondition(BaseModel):
    key: str
    operator: ApplicabilityOperator
    value: Any | None = None


class InterceptResult(str, Enum):
    CLEAR = "clear"
    WARN = "warn"
    BLOCK = "block"
    AUTO_EXECUTE = "auto_execute"
    suspended = "suspended"


class SSEEventType(str, Enum):
    SKILL_COMPILED = "skill_compiled"
    SKILL_REINFORCED = "skill_reinforced"
    SKILL_INVALIDATED = "skill_invalidated"
    SKILL_SUSPENDED = "skill_suspended"
    DECISION_INTERCEPTED = "decision_intercepted"
    AGENT_ACTION = "agent_action"
    AGENT_REGISTERED = "agent_registered"
    CONFIG_UPDATED = "config_updated"
    KEEPALIVE = "keepalive"


class SkillPattern(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    entity_types: list[str] = Field(default_factory=list)
    context_signals: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)


class SkillKnowledge(BaseModel):
    what_happened: str = ""
    failure_mode: str = ""
    what_worked: str = ""
    conditions: list[str] = Field(default_factory=list)
    anti_conditions: list[str] = Field(default_factory=list)


class SkillExecutable(BaseModel):
    intercept_message: str = ""
    recommended_action: str = ""
    avoid_actions: list[str] = Field(default_factory=list)
    auto_execute: bool = False
    escalate_if: list[str] = Field(default_factory=list)


class SkillProvenance(BaseModel):
    source_event_id: str = ""
    compiled_at: datetime = Field(default_factory=utc_now)
    confidence: float = 0.60
    reinforcement_count: int = 0
    last_validated: datetime = Field(default_factory=utc_now)
    decay_rate: DecayRate = DecayRate.MEDIUM
    expires_at: datetime | None = None
    invalidated: bool = False
    superseded_by: str | None = None
    applies_if: list[ApplicabilityCondition] = Field(default_factory=list)
    invalidated_if: list[ApplicabilityCondition] = Field(default_factory=list)
    applicability_status: ApplicabilityStatus = Field(default=ApplicabilityStatus.active)
    last_applicability_check_at: Optional[datetime] = None
    last_invalid_reason: Optional[str] = None


class SkillPropagation(BaseModel):
    agents_notified: list[str] = Field(default_factory=list)
    propagated_at: datetime | None = None
    acknowledgements: dict[str, datetime] = Field(default_factory=dict)


class CompanyBrainSkill(BaseModel):
    skill_id: str
    name: str
    version: int = 1
    domain: str = "general"
    summary: str = ""
    pattern: SkillPattern = Field(default_factory=SkillPattern)
    knowledge: SkillKnowledge = Field(default_factory=SkillKnowledge)
    executable: SkillExecutable = Field(default_factory=SkillExecutable)
    provenance: SkillProvenance = Field(default_factory=SkillProvenance)
    propagation: SkillPropagation = Field(default_factory=SkillPropagation)
    embedding: list[float] | None = None
    is_active: bool = True
    user_id: str = "demo-user"
    org_id: str = "default"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RawEvent(BaseModel):
    event_id: str
    agent_id: str
    event_type: str
    content: str
    outcome: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)
    user_id: str = "demo-user"
    org_id: str = "default"
    session_id: str | None = None


class DecisionCheckRequest(BaseModel):
    agent_id: str
    decision_text: str
    domain: str | None = None
    user_id: str = "demo-user"
    org_id: str = "default"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DecisionCheckResponse(BaseModel):
    result: InterceptResult
    confidence: float = 0.0
    matched_skill: CompanyBrainSkill | None = None
    intercept_message: str = ""
    recommended_action: str = ""
    auto_execute: bool = False
    rationale: str = ""
    applicability_status: Optional[str] = None
    suspension_reason: Optional[str] = None
    suspension_evidence: Optional[dict] = None


class AgentRunRequest(BaseModel):
    agent_id: str = ""
    user_message: str
    session_id: str | None = None
    user_id: str = "demo-user"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunResponse(BaseModel):
    agent_id: str
    response: str
    skills_used: list[str] = Field(default_factory=list)
    intercepted: bool = False
    intercept_skill: str | None = None
    iterations: int = 0
    session_id: str | None = None


class SSEEvent(BaseModel):
    type: SSEEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=utc_now)


class SessionMemory(BaseModel):
    session_id: str
    user_id: str = "demo-user"
    org_id: str = "default"
    agent_id: str
    turn_count: int = 0
    key_decisions: list[str] = Field(default_factory=list)
    unresolved_intents: list[str] = Field(default_factory=list)
    brain_skills_used: list[str] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=utc_now)


class InterceptLogEntry(BaseModel):
    agent_id: str
    decision_text: str
    matched_skill: str | None = None
    result: InterceptResult
    confidence: float = 0.0
    org_id: str = "default"
    occurred_at: datetime = Field(default_factory=utc_now)
    applicability_status: Optional[str] = None
    suspension_reason: Optional[str] = None


class AgentRegistration(BaseModel):
    agent_id: str
    agent_type: str
    org_id: str = "default"
    last_brain_version: int = 0
    registered_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
