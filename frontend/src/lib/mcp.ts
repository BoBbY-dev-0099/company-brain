import type { WorkflowRun } from "../types/schema"
import type { RealityMemory } from "./api"

export type McpLog = {
  step: "initialize" | "tools_list" | "evaluate_workflow" | "inspect_memory"
  status: "running" | "complete" | "error"
  detail: string
}

type McpContent = { text?: string }
type McpResponse = {
  result?: {
    content?: McpContent[]
    tools?: Array<{ name?: string }>
    serverInfo?: { name?: string; version?: string }
    isError?: boolean
  }
  error?: { message?: string }
}

type McpCall = {
  endpoint: string
  apiKey: string
  templateId: string
  evidence: Array<Record<string, unknown>>
  liveContext: Record<string, unknown>
  onLog: (entry: McpLog) => void
}

async function rpc(
  endpoint: string,
  apiKey: string,
  id: number,
  method: string,
  params: Record<string, unknown>,
): Promise<McpResponse> {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: {
      Accept: "application/json, text/event-stream",
      "Content-Type": "application/json",
      "X-Brain-Api-Key": apiKey,
    },
    body: JSON.stringify({ jsonrpc: "2.0", id, method, params }),
  })
  const payload = await response.json().catch(() => ({})) as McpResponse
  if (!response.ok) throw new Error(payload.error?.message ?? "MCP endpoint rejected the request.")
  if (payload.error) throw new Error(payload.error.message ?? "MCP returned a JSON-RPC error.")
  if (!payload.result) throw new Error("MCP returned no result.")
  return payload
}

export async function evaluateWorkflowThroughMcp(input: McpCall): Promise<WorkflowRun> {
  input.onLog({ step: "initialize", status: "running", detail: "Opening authenticated Streamable HTTP MCP connection." })
  const initialized = await rpc(input.endpoint, input.apiKey, 1, "initialize", {
    protocolVersion: "2025-03-26",
    capabilities: {},
    clientInfo: { name: "company-brain-workflow-lab", version: "1.0.0" },
  })
  const server = initialized.result?.serverInfo
  input.onLog({
    step: "initialize",
    status: "complete",
    detail: "Connected to " + (server?.name ?? "Company Brain") + (server?.version ? " " + server.version : "") + ".",
  })

  input.onLog({ step: "tools_list", status: "running", detail: "Reading the server-published tool list." })
  const listed = await rpc(input.endpoint, input.apiKey, 2, "tools/list", {})
  const toolNames = (listed.result?.tools ?? []).map((tool) => tool.name).filter(Boolean)
  if (!toolNames.includes("evaluate_workflow")) throw new Error("The MCP server did not publish evaluate_workflow.")
  input.onLog({ step: "tools_list", status: "complete", detail: "Tool available: evaluate_workflow." })

  input.onLog({ step: "evaluate_workflow", status: "running", detail: "Sending normalized evidence and live context to Company Brain." })
  const evaluated = await rpc(input.endpoint, input.apiKey, 3, "tools/call", {
    name: "evaluate_workflow",
    arguments: {
      template_id: input.templateId,
      evidence: input.evidence,
      live_context: input.liveContext,
    },
  })
  if (evaluated.result?.isError) {
    const text = evaluated.result.content?.[0]?.text ?? "MCP workflow tool failed."
    throw new Error(text)
  }
  const text = evaluated.result?.content?.[0]?.text
  if (!text) throw new Error("MCP evaluate_workflow returned no DecisionBrief.")
  const run = JSON.parse(text) as WorkflowRun
  input.onLog({
    step: "evaluate_workflow",
    status: "complete",
    detail: "Received " + String(run.decision_brief?.verdict ?? "a governed verdict") + " from the MCP workflow tool.",
  })
  return run
}

type McpMemoryCall = {
  endpoint: string
  apiKey: string
  query: string
  onLog: (entry: McpLog) => void
}

/** Read source-backed Reality Memory through the same authenticated MCP transport.
 * This deliberately has no mutation or external-action authority. */
export async function inspectMemoryThroughMcp(input: McpMemoryCall): Promise<RealityMemory[]> {
  input.onLog({ step: "initialize", status: "running", detail: "Opening authenticated Streamable HTTP MCP connection." })
  const initialized = await rpc(input.endpoint, input.apiKey, 1, "initialize", {
    protocolVersion: "2025-03-26",
    capabilities: {},
    clientInfo: { name: "company-brain-nexaflow-lab", version: "1.0.0" },
  })
  const server = initialized.result?.serverInfo
  input.onLog({
    step: "initialize",
    status: "complete",
    detail: "Connected to " + (server?.name ?? "Company Brain") + (server?.version ? " " + server.version : "") + ".",
  })

  input.onLog({ step: "tools_list", status: "running", detail: "Reading the server-published tool list." })
  const listed = await rpc(input.endpoint, input.apiKey, 2, "tools/list", {})
  const toolNames = (listed.result?.tools ?? []).map((tool) => tool.name).filter(Boolean)
  if (!toolNames.includes("inspect_memory")) throw new Error("The MCP server did not publish inspect_memory.")
  input.onLog({ step: "tools_list", status: "complete", detail: "Tool available: inspect_memory." })

  input.onLog({ step: "inspect_memory", status: "running", detail: "Asking MCP for active and superseded source-backed memory." })
  const inspected = await rpc(input.endpoint, input.apiKey, 3, "tools/call", {
    name: "inspect_memory",
    arguments: { query: input.query, include_superseded: true, top_k: 10 },
  })
  if (inspected.result?.isError) {
    const text = inspected.result.content?.[0]?.text ?? "MCP memory inspection failed."
    throw new Error(text)
  }
  const text = inspected.result?.content?.[0]?.text
  if (!text) throw new Error("MCP inspect_memory returned no memory response.")
  const payload = JSON.parse(text) as { memories?: RealityMemory[] }
  const memories = Array.isArray(payload.memories) ? payload.memories : []
  input.onLog({
    step: "inspect_memory",
    status: "complete",
    detail: `MCP returned ${memories.length} source-backed memory record${memories.length === 1 ? "" : "s"}.`,
  })
  return memories
}
