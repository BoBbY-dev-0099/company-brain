export type HealthStatus = {
  status: "ok" | "degraded"
  version: string
  skills_compiled: number
  subscribers: number
  db: { connected: boolean; db: string }
  qwen_configured: boolean
  embedding_healthy: boolean | null
}

export type ApiKey = {
  key_id: string
  name: string
  permissions: string
  created_at: number
  org_id: string
}

export type SkillSummary = {
  skill_id: string
  name: string
  version: number
  domain: string
  summary: string
  confidence: number
  reinforcement_count: number
  auto_execute: boolean
  decay_rate: "slow" | "medium" | "fast" | "never"
  intercept_message: string
}

export type SSEEventType =
  | "skill_compiled"
  | "skill_reinforced"
  | "skill_invalidated"
  | "decision_intercepted"
  | "agent_action"
  | "agent_registered"
  | "keepalive"
  | "hello"

export type SkillCompiledPayload = {
  skill: SkillSummary
  agent_ids: string[]
}

export type DecisionInterceptedPayload = {
  agent_id: string
  skill: SkillSummary
  result: "clear" | "warn" | "block" | "auto_execute"
  confidence: number
}

export type AgentActionPayload = {
  agent_id: string
  action_type: string
  content: string
  metadata: Record<string, unknown>
}

export type AuditEntry = {
  id: string
  timestamp: number
  kind: "compile" | "propagate" | "intercept" | "agent" | "info"
  text: string
}

export type Ticket = {
  id: string
  title: string
  body: string
  status: "processing" | "resolved" | "escalated"
  compiledSkillVersion?: string
}

export type PullRequest = {
  id: string
  title: string
  author: string
  description: string
  status: "pending" | "intercepted" | "approved"
  matchedSkill?: { id: string; name: string; confidence: number }
  intercept?: {
    result: "clear" | "warn" | "block" | "auto_execute"
    skill_name: string
    confidence: number
    intercept_message: string
  }
}

export type ProductMessage = {
  role: "user" | "agent"
  content: string
  reasoning?: string
}

export type ProductSession = {
  id: string
  label: string
  messages: ProductMessage[]
  brainUpdated?: string
}

/**
 * The operational-memory API intentionally keeps evidence separate from the
 * model's inference.  UI consumers should render these records as supplied,
 * rather than manufacture a decision when an API is unavailable.
 */
export type EvidenceRecord = {
  id?: string
  evidence_id?: string
  source?: string
  source_type?: string
  source_name?: string
  label?: string
  external_id?: string
  url?: string
  timestamp?: string | number
  occurred_at?: string | number
  excerpt?: string
  freshness?: string
  availability?: string
  mode?: string
  is_demo_fixture?: boolean
  [key: string]: unknown
}

export type DecisionFact = {
  statement: string
  source_evidence_ids?: string[]
}

export type DecisionInference = {
  text: string
  generated_by?: string
  is_model_generated?: boolean
}

export type MissingEvidence = {
  field: string
  reason: string
  source_evidence_id?: string
}

export type MemoryReference = {
  id?: string
  memory_id?: string
  skill_id?: string
  name?: string
  version?: string | number
  summary?: string
  source?: string
  is_ephemeral?: boolean
  provenance?: Record<string, unknown>
  [key: string]: unknown
}

export type DecisionBrief = {
  facts?: Array<string | DecisionFact>
  inference?: string | string[] | DecisionInference
  missing_evidence?: Array<string | MissingEvidence>
  evidence?: EvidenceRecord[]
  memory_refs?: MemoryReference[]
  sag_trace?: Record<string, unknown> | string | null
  verdict?: string
  recommended_action?: string
  recommended_next_action?: string
  owner?: string
  what_changed?: string | string[]
  [key: string]: unknown
}

export type WorkflowOutcome = {
  id?: string
  approved?: boolean
  outcome?: string
  actor?: string
  created_at?: string | number
  timestamp?: string | number
  recorded_at?: string | number
  [key: string]: unknown
}

export type WorkflowRun = {
  id: string
  run_id?: string
  template_id: string
  org_id?: string
  template_name?: string
  status?: string
  brief?: DecisionBrief
  decision_brief?: DecisionBrief
  recommended_next_action?: string
  human_approval_required?: boolean
  owner?: string
  outcomes?: WorkflowOutcome[]
  fixture?: boolean
  is_demo_fixture?: boolean
  is_judge_sandbox?: boolean
  execution_origin?: string
  expires_at?: string | number
  live_context?: Record<string, unknown>
  mode?: string
  created_at?: string | number
  updated_at?: string | number
  [key: string]: unknown
}

export type WorkflowTemplate = {
  id?: string
  template_id?: string
  title?: string
  name?: string
  display_name?: string
  version?: string | number
  description?: string
  supported_source_types?: string[]
  source_types?: string[]
  required_evidence_fields?: string[]
  live_context_schema?: Record<string, unknown>
  sag_predicates?: string[]
  memory_type?: "policy" | "incident" | "decision" | "commitment" | "exception" | string
  recommended_actions?: string[]
  owner_role?: string
  human_approval_required?: boolean
  fixture?: boolean | Record<string, unknown>
  demo_fixture?: boolean | Record<string, unknown>
  latest_run?: WorkflowRun
  demo_run?: WorkflowRun
  demo_preview?: WorkflowRun
  current_run?: WorkflowRun
  [key: string]: unknown
}

export type WorkflowSource = {
  id?: string
  evidence_id?: string
  label?: string
  source_name?: string
  source_type?: string
  external_id?: string
  status?: string
  availability?: string
  freshness?: string
  last_synced_at?: string | number
  occurred_at?: string | number
  mode?: string
  is_demo_fixture?: boolean
  [key: string]: unknown
}

export type DemoReadiness = {
  build_sha?: string
  qwen_configured?: boolean
  embedding_healthy?: boolean | null
  scenario_version?: string
  canonical_skill_count?: number
  ready?: boolean
  checks?: Record<string, boolean | string | number | null>
  [key: string]: unknown
}

export type IntegrationStatus = "connected" | "setup_required" | "contract_ready" | "fixture" | "preview" | string

export type IntegrationContract = {
  method?: string
  path?: string
  endpoint?: string
  title?: string
  description?: string
  purpose?: string
  name?: string
  permission?: string
  [key: string]: unknown
}

export type IntegrationBoundary = {
  id?: string
  title?: string
  status?: IntegrationStatus
  description?: string
  endpoint?: string
  requirements?: string[]
  contracts?: Array<IntegrationContract | string>
  tools?: Array<IntegrationContract | string>
  example?: unknown
  example_request?: unknown
  examples?: unknown[]
  [key: string]: unknown
}

export type IntegrationCatalog = {
  version?: number | string
  positioning?: string
  public_base_url?: string
  connection_boundaries?: IntegrationBoundary[]
  connections?: IntegrationBoundary[]
  status_definitions?: Record<string, string>
  [key: string]: unknown
}
