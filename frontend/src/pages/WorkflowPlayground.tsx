import { useState } from "react"
import { ArrowLeft, Bot, Check, Send, TerminalSquare } from "lucide-react"
import { Link } from "react-router-dom"
import { createDemoMcpSession, createDemoSession, getWorkflowTemplates, replayIncident, type WorkflowEvidenceInput } from "../lib/api"
import { evaluateWorkflowThroughMcp, type McpLog } from "../lib/mcp"
import type { DecisionBrief, WorkflowRun, WorkflowTemplate } from "../types/schema"

type ChatLine = { role: "brain" | "you" | "tool"; body: string }

function templateId(template: WorkflowTemplate) { return template.template_id ?? template.id ?? "" }
function asBrief(run: WorkflowRun | null) { return (run?.decision_brief ?? run?.brief ?? null) as DecisionBrief | null }

function fixtureEvidence(template: WorkflowTemplate): WorkflowEvidenceInput[] {
  const fixture = template.demo_fixture as Record<string, unknown> | undefined
  return (Array.isArray(fixture?.evidence) ? fixture.evidence : []).map((item) => {
    const record = item as Record<string, unknown>
    return { source_type: String(record.source_type ?? "workspace_note"), source_name: String(record.source_name ?? "Workspace"), external_id: String(record.external_id ?? "sandbox"), occurred_at: String(record.occurred_at ?? new Date().toISOString()), excerpt: String(record.excerpt ?? "No excerpt"), metadata: (record.metadata as Record<string, unknown>) ?? {} }
  })
}

function fixtureContext(template: WorkflowTemplate): Record<string, unknown> {
  const fixture = template.demo_fixture as Record<string, unknown> | undefined
  return (fixture?.live_context as Record<string, unknown>) ?? {}
}

export default function WorkflowPlayground() {
  const [message, setMessage] = useState("")
  const [lines, setLines] = useState<ChatLine[]>([{ role: "brain", body: "Describe a release, refund, or rollout decision. I will call the real MCP tool and show its source-backed DecisionBrief. Try: ‘A Slack incident says the export worker is OOM after PR #842.’" }])
  const [logs, setLogs] = useState<McpLog[]>([])
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (preset?: string) => {
    const input = (preset ?? message).trim()
    if (!input || running) return
    setMessage("")
    setRunning(true)
    setError(null)
    setRun(null)
    setLogs([])
    setLines((current) => [...current, { role: "you", body: input }, { role: "tool", body: "Preparing a private sandbox and requesting the Company Brain MCP tool list..." }])
    try {
      await createDemoSession()
      const lower = input.toLowerCase()
      let templateIdValue = lower.match(/refund|contract|billing|policy/) ? "money-safety" : lower.match(/rollout|feature|reliability|cohort/) ? "rollout-safety" : "release-safety"
      let evidence: WorkflowEvidenceInput[] = []
      let liveContext: Record<string, unknown> = {}
      if (templateIdValue === "release-safety" && /slack|oom|incident|pr|deploy|export/.test(lower)) {
        const replay = await replayIncident()
        evidence = replay.workflow.evidence
        liveContext = replay.workflow.live_context
        templateIdValue = replay.workflow.template_id
        setLines((current) => [...current, { role: "tool", body: "Source replay completed: Slack incident, Drive runbook, GitHub change, and runtime telemetry are now available to the MCP workflow." }])
      } else {
        const templates = await getWorkflowTemplates()
        const template = templates.templates.find((item) => templateId(item) === templateIdValue)
        if (!template) throw new Error("The server did not publish the requested workflow contract.")
        evidence = fixtureEvidence(template)
        liveContext = fixtureContext(template)
        setLines((current) => [...current, { role: "tool", body: `The server-owned ${template.title ?? templateIdValue} fixture supplies normalized evidence and live context.` }])
      }
      const session = await createDemoMcpSession()
      const result = await evaluateWorkflowThroughMcp({ endpoint: session.mcp_endpoint, apiKey: session.api_key, templateId: templateIdValue, evidence, liveContext, onLog: (entry) => setLogs((current) => [...current.filter((item) => item.step !== entry.step), entry]) })
      setRun(result)
      const brief = asBrief(result)
      setLines((current) => [...current, { role: "brain", body: `${String(brief?.verdict ?? "Decision").replaceAll("_", " ")}: ${String(brief?.recommended_next_action ?? "The backend returned no recommendation.")}` }])
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : "The MCP workflow call failed."
      setError(detail)
      setLines((current) => [...current, { role: "brain", body: `I could not complete the backend call: ${detail}` }])
    } finally { setRunning(false) }
  }

  const brief = asBrief(run)
  return <div className="min-h-screen bg-[#f5f1e8] text-[#17212b]"><header className="border-b border-[#d9d3c8] bg-[#f5f1e8]/95"><div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-5"><Link to="/" className="inline-flex items-center gap-2 text-sm font-semibold"><ArrowLeft className="h-4 w-4" />Reality Console</Link><span className="text-xs font-semibold uppercase tracking-[0.14em] text-[#2f5eeb]">Live Workflow Lab</span></div></header><main className="mx-auto max-w-5xl px-5 py-10"><section className="max-w-3xl"><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">MCP-connected sandbox</p><h1 className="mt-3 text-4xl font-semibold tracking-[-0.05em]">Talk to the decision gateway.</h1><p className="mt-4 text-base leading-7 text-[#5a6775]">This lab does not accept company credentials or execute external actions. It turns the selected sandbox scenario into normalized evidence, then calls Company Brain through authenticated MCP.</p></section>
  <section className="mt-8 grid gap-5 lg:grid-cols-[1fr_0.8fr]"><article className="rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-5 shadow-[0_18px_55px_rgba(52,45,35,0.06)]"><div className="space-y-4">{lines.map((line, index) => <div key={index} className={`rounded-2xl px-4 py-3 text-sm leading-6 ${line.role === "you" ? "ml-8 bg-[#17212b] text-white" : line.role === "tool" ? "border border-[#d8e2f3] bg-[#f4f7fd] text-[#40556f]" : "mr-8 border border-[#e3ddd2] bg-[#faf7f0] text-[#354454]"}`}>{line.role === "tool" && <TerminalSquare className="mr-2 inline h-4 w-4 text-[#2f5eeb]" />}{line.body}</div>)}</div><div className="mt-6 flex flex-wrap gap-2"><button onClick={() => void submit("A Slack incident says the export worker is OOM after PR #842.")} className="rounded-full border border-[#cbd6e8] bg-[#f4f7fd] px-3 py-1.5 text-xs font-semibold text-[#2148c7]">Try source incident</button><button onClick={() => void submit("A customer asks for an automatic refund but contract evidence may conflict.")} className="rounded-full border border-[#d8d0c2] bg-[#faf7f0] px-3 py-1.5 text-xs font-semibold">Try refund</button><button onClick={() => void submit("Expand the feature rollout although reliability is uncertain.")} className="rounded-full border border-[#d8d0c2] bg-[#faf7f0] px-3 py-1.5 text-xs font-semibold">Try rollout</button></div><form onSubmit={(event) => { event.preventDefault(); void submit() }} className="mt-5 flex gap-2"><input value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Describe what changed..." className="min-w-0 flex-1 rounded-xl border border-[#cfd7e4] bg-white px-3 py-3 text-sm outline-none focus:border-[#2f5eeb]" /><button disabled={running || !message.trim()} className="grid h-11 w-11 place-items-center rounded-xl bg-[#17212b] text-white disabled:opacity-50"><Send className="h-4 w-4" /></button></form></article>
  <aside className="rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-5"><div className="flex items-center gap-2"><Bot className="h-5 w-5 text-[#2f5eeb]" /><h2 className="font-semibold">MCP execution</h2></div><p className="mt-2 text-sm leading-6 text-[#637080]">Browser-private API key; server resolves the organization. No caller-supplied org ID.</p>{logs.length === 0 ? <p className="mt-6 text-sm text-[#718096]">Awaiting an MCP call.</p> : <div className="mt-5 space-y-3">{logs.map((log) => <div key={log.step} className="rounded-xl border border-[#e3e8f1] bg-[#f8fafc] p-3"><p className="font-mono text-xs text-[#2148c7]">{log.step}</p><p className="mt-1 text-xs leading-5 text-[#536170]">{log.detail}</p></div>)}</div>}{brief && <div className="mt-6 rounded-xl border border-[#d8e2d8] bg-[#f2faf5] p-4"><div className="flex items-center gap-2 text-[#1d604f]"><Check className="h-4 w-4" /><span className="text-xs font-bold uppercase tracking-wide">{String(brief.verdict).replaceAll("_", " ")}</span></div><p className="mt-2 text-sm font-semibold leading-6">{brief.recommended_next_action}</p><p className="mt-2 text-xs text-[#537267]">Owner: {brief.owner} · Human approval required</p></div>}{error && <p className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">{error}</p>}</aside></section></main></div>
}
