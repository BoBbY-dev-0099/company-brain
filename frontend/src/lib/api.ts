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

export function getWorkflowRun(runId: string) {
  return apiGet<WorkflowRun | { run: WorkflowRun }>(`/workflow-runs/${encodeURIComponent(runId)}`)
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
