import axios from "axios"
import type {
  DemoReadiness,
  IntegrationCatalog,
  WorkflowOutcome,
  WorkflowRun,
  WorkflowSource,
  WorkflowTemplate,
} from "../types/schema"

export const apiClient = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
})

export async function apiGet<T = any>(path: string, options?: any): Promise<T> {
  const res = await apiClient.get(path, options)
  return res.data
}

export async function apiPost<T = any>(path: string, body: any): Promise<T> {
  const res = await apiClient.post(path, body)
  return res.data
}

export async function apiDelete<T = any>(path: string, options?: any): Promise<T> {
  const res = await apiClient.delete(path, options)
  return res.data
}

export type WorkflowTemplatesResponse = { templates: WorkflowTemplate[] }
export type WorkflowSourcesResponse = { sources: WorkflowSource[] }
export type WorkflowRunRequest = {
  template_id: string
  fixture?: boolean
  evidence?: WorkflowEvidenceInput[]
  live_context?: Record<string, unknown>
}

export type WorkflowEvidenceInput = {
  source_type: string
  source_name?: string
  external_id?: string
  url?: string
  occurred_at?: string
  excerpt: string
  availability?: string
  metadata?: Record<string, unknown>
}

export type DemoModule = {
  id: string
  kind: "playground" | "simulation"
  title: string
  route: string
  summary: string
  status: string
  primary_action: string
  template_id?: string
  fixture?: boolean
}

export type DemoSession = {
  mode: "judge_sandbox"
  expires_at: string
  retention: string
}
export type DemoMcpSession = {
  mode: "judge_sandbox_mcp"
  mcp_endpoint: string
  api_key: string
  permissions: string
  expires_at: string
  retention: string
}
export type WorkflowOutcomeRequest = {
  approved: boolean
  outcome: string
  note?: string
  actor: string
}

// Keep this small surface explicit: the Operations inbox is a consumer of
// server-owned templates and auditable runs, not a client-side workflow engine.
export function getWorkflowTemplates() {
  return apiGet<WorkflowTemplatesResponse>("/workflow-templates")
}

export function createWorkflowRun(body: WorkflowRunRequest) {
  return apiPost<WorkflowRun | { run: WorkflowRun }>("/workflow-runs", body)
}

export function getDemoModules() {
  return apiGet<{ version: string; modules: DemoModule[] }>("/demo/modules")
}

export function createDemoSession() {
  return apiPost<DemoSession>("/demo/session", {})
}

export function createDemoMcpSession() {
  return apiPost<DemoMcpSession>("/demo/mcp-session", {})
}

export function getWorkflowRun(runId: string) {
  return apiGet<WorkflowRun | { run: WorkflowRun }>(`/workflow-runs/${encodeURIComponent(runId)}`)
}

export function getWorkflowRuns(limit = 20) {
  return apiGet<{ runs: WorkflowRun[] }>("/workflow-runs?limit=" + encodeURIComponent(String(limit)))
}

export function postWorkflowOutcome(runId: string, body: WorkflowOutcomeRequest) {
  return apiPost<WorkflowRun | WorkflowOutcome | { run: WorkflowRun }>(
    `/workflow-runs/${encodeURIComponent(runId)}/outcome`,
    body,
  )
}

export function getWorkflowSources() {
  return apiGet<WorkflowSourcesResponse>("/workflow-sources")
}

export function getDemoReadiness() {
  return apiGet<DemoReadiness>("/demo/readiness")
}

// Connection claims are server-owned. The UI renders this catalog verbatim
// instead of inferring whether a source or agent connector is actually live.
export function getIntegrationCatalog() {
  return apiGet<IntegrationCatalog>("/integration-catalog")
}

export type SourceConnection = {
  provider: string
  title: string
  status: string
  allowed_scope: string[]
  endpoint?: string
  last_success_at?: string
  last_error?: string
  health?: string
  configuration?: Record<string, boolean | string | number>
}

export type SourceEvent = {
  ingestion_id: string
  provider: string
  external_id: string
  source_type: string
  source_name: string
  source_url?: string
  occurred_at: string
  retrieved_at?: string
  excerpt: string
  raw_payload_sha256: string
  freshness?: string
  availability?: string
  acl_scope?: string[]
  stage: string
  qwen_status: string
  memory_id?: string
  is_judge_sandbox?: boolean
}

export type RealityMemory = {
  memory_id: string
  claim_key: string
  subject: string
  predicate: string
  scope: string
  claim: string
  status: string
  source_ingestion_ids: string[]
  qwen_rationale: string
  qwen_generated: boolean
  supersedes: string[]
  superseded_by?: string
  is_ephemeral?: boolean
  updated_at: string
}

export type RealityOverview = {
  connections: SourceConnection[]
  events: SourceEvent[]
  memories: RealityMemory[]
  mode: string
}

export type IncidentReplay = {
  mode: string
  events: SourceEvent[]
  workflow: {
    template_id: string
    evidence: WorkflowEvidenceInput[]
    live_context: Record<string, unknown>
  }
}

export function getSourceConnections() {
  return apiGet<{ connections: SourceConnection[] }>("/source-connections")
}

export function getSourceEvents(limit = 30) {
  return apiGet<{ events: SourceEvent[] }>(`/source-events?limit=${encodeURIComponent(String(limit))}`)
}

export function getRealityMemory(query = "", includeSuperseded = true) {
  return apiGet<{ memories: RealityMemory[] }>(
    `/reality-memory?include_superseded=${includeSuperseded ? "true" : "false"}&query=${encodeURIComponent(query)}`,
  )
}

export function getRealityOverview() {
  return apiGet<RealityOverview>("/reality-overview")
}

export function replayIncident() {
  return apiPost<IncidentReplay>("/reality/replay/incident", {})
}
