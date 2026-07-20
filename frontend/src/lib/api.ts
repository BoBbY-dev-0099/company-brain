import axios from "axios"

export const apiClient = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
})

export type SourceConnection = {
  provider: "slack" | "alibaba_oss" | "github" | string
  title: string
  status: "connected" | "setup_required" | "contract_ready" | string
  allowed_scope: string[]
  endpoint?: string
  last_success_at?: string | null
  last_error?: string | null
  health?: string
  configuration?: Record<string, boolean | string | number>
}

export type SourceEvidence = {
  ingestion_id: string
  provider: string
  source_name: string
  source_type: string
  source_url?: string | null
  occurred_at: string
  retrieved_at?: string
  excerpt: string
  raw_payload_sha256: string
  freshness: string
  availability: string
  acl_scope: string[]
  stage: string
  qwen_status: string
  memory_id?: string | null
}

export type RealityMemory = {
  memory_id: string
  claim: string
  subject: string
  predicate: string
  scope: string
  status: string
  source_ingestion_ids: string[]
  qwen_rationale: string
  qwen_generated: boolean
  supersedes: string[]
  superseded_by?: string | null
  updated_at: string
}

export type QwenCaseResult = {
  case_id: string
  title: string
  description: string
  verdict: "suspended" | "review_required" | "proceed_with_human_approval" | string
  recommendation: string
  qwen: {
    status: "compiled" | "unavailable" | string
    model?: string | null
    summary: string
    source_count: number
    memory_id?: string | null
  }
  sag: Record<string, unknown>
  human_approval_required: boolean
  ephemeral: boolean
}

export type NexaFlowCaseMatrix = {
  scenario_version: string
  qwen_configured: boolean
  cases: QwenCaseResult[]
  boundary: string
}

export type DecisionRun = {
  run_id: string
  template_id: string
  created_at: string
  live_context: Record<string, unknown>
  decision_brief: {
    verdict: "suspended" | "review_required" | "proceed_with_human_approval" | string
    status: string
    owner: string
    recommended_next_action: string
    human_approval_required: boolean
    inference: { text: string; generated_by: string; is_model_generated: boolean }
    facts: Array<{ label: string; statement: string; source_evidence_id?: string }>
    missing_evidence: Array<{ field: string; reason: string }>
    evidence: Array<Record<string, unknown>>
    memory_refs: Array<Record<string, unknown>>
    sag_trace: Record<string, unknown>
  }
}

export type NexaFlowOverview = {
  company: string
  mode: string
  connections: SourceConnection[]
  evidence: SourceEvidence[]
  memories: RealityMemory[]
  release_check_ready: boolean
  readiness_reasons: string[]
  latest_release_check?: DecisionRun | null
  server_time: string
}

export type NexaFlowDecision = {
  run: DecisionRun
  source_selection: Record<string, string | null>
  parsing: Record<string, unknown>
  boundary: string
}

export type OperatorSetup = {
  enabled: boolean
  local_rehearsal?: boolean
  operator_auth_required?: boolean
  providers: Record<string, { fields: string[]; endpoint: string; steps: string[] }>
}

export type OperatorProviderConfig = {
  provider: string
  configured: boolean
  public: Record<string, string>
  secrets: Record<string, boolean>
  masked: Record<string, string>
  updated_at?: string | null
}

export async function getNexaFlowOverview() {
  return (await apiClient.get<NexaFlowOverview>("/nexaflow/overview")).data
}

export async function runNexaFlowReleaseCheck() {
  return (await apiClient.post<NexaFlowDecision>("/nexaflow/release-check", {})).data
}

export async function runNexaFlowCaseMatrix() {
  return (await apiClient.post<NexaFlowCaseMatrix>("/nexaflow/case-matrix", {})).data
}

export async function getOperatorSetup() {
  return (await apiClient.get<OperatorSetup>("/operator/integrations/setup")).data
}

function operatorHeaders(token?: string) {
  return token ? { headers: { "X-Integration-Admin-Token": token } } : undefined
}

export async function getOperatorConfigs(token?: string) {
  return (await apiClient.get<{ providers: Record<string, OperatorProviderConfig> }>("/operator/integrations/config", operatorHeaders(token))).data
}

export async function saveOperatorConfig(provider: string, values: Record<string, string>, token?: string) {
  return (await apiClient.put<{ provider: OperatorProviderConfig; message: string }>(`/operator/integrations/${encodeURIComponent(provider)}`, { values }, operatorHeaders(token))).data
}

export async function testOperatorConfig(provider: string, token?: string) {
  return (await apiClient.post<{ ok: boolean; status: string; detail: string }>(`/operator/integrations/${encodeURIComponent(provider)}/test`, {}, operatorHeaders(token))).data
}

export async function syncOperatorOSS(token?: string) {
  return (await apiClient.post<{ ok: boolean; accepted: number; detail: string }>("/operator/integrations/alibaba_oss/sync-now", {}, operatorHeaders(token))).data
}
