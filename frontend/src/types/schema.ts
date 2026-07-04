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
