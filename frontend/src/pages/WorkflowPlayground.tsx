import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Bot, Check, ChevronDown, LoaderCircle, MessageSquareText, RotateCcw, Send, TerminalSquare, UserRound, Wrench } from "lucide-react"
import { createDemoMcpSession, createDemoSession, getWorkflowRuns, getWorkflowTemplates, postWorkflowOutcome, type DemoMcpSession, type WorkflowEvidenceInput } from "../lib/api"
import { evaluateWorkflowThroughMcp, type McpLog } from "../lib/mcp"
import type { WorkflowRun, WorkflowTemplate } from "../types/schema"
import { AuditProof, DecisionTrace, PageFrame, asRun, briefFor, verdictLabel, verdictTone } from "./Simulation"

type WorkspacePlan = {
  template: WorkflowTemplate
  evidence: WorkflowEvidenceInput[]
  liveContext: Record<string, unknown>
  summary: string
}

type ConversationEntry = {
  id: string
  role: "assistant" | "user" | "tool"
  title?: string
  body: string
}

const starterMessage: ConversationEntry = {
  id: "welcome",
  role: "assistant",
  title: "Company Brain workspace",
  body: "Name a workspace, then describe a release, refund, or rollout decision. Include the current facts you know. I will show the normalized evidence, call the real MCP tool, and return only the backend DecisionBrief.",
}

function templateId(template: WorkflowTemplate): string {
  return template.template_id ?? template.id ?? ""
}

function fixtureEvidence(template: WorkflowTemplate): WorkflowEvidenceInput[] {
  const fixture = template.demo_fixture as Record<string, unknown> | undefined
  const entries = Array.isArray(fixture?.evidence) ? fixture.evidence : []
  return entries.map((entry) => {
    const record = entry as Record<string, unknown>
    return {
      source_type: String(record.source_type ?? "workspace_event"),
      source_name: typeof record.source_name === "string" ? record.source_name : "Workspace adapter",
      external_id: typeof record.external_id === "string" ? record.external_id : "workspace-event",
      url: typeof record.url === "string" ? record.url : undefined,
      occurred_at: typeof record.occurred_at === "string" ? record.occurred_at : new Date().toISOString(),
      excerpt: typeof record.excerpt === "string" ? record.excerpt : "No excerpt supplied.",
      availability: typeof record.availability === "string" ? record.availability : "available",
      metadata: (record.metadata as Record<string, unknown> | undefined) ?? {},
    }
  })
}

function fixtureContext(template: WorkflowTemplate): Record<string, unknown> {
  const fixture = template.demo_fixture as Record<string, unknown> | undefined
  return fixture?.live_context && typeof fixture.live_context === "object" ? { ...(fixture.live_context as Record<string, unknown>) } : {}
}

function chooseTemplate(templates: WorkflowTemplate[], message: string): WorkflowTemplate | null {
  const normalized = message.toLowerCase()
  const preferred = normalized.match(/refund|chargeback|invoice|billing|customer|contract|policy/)
    ? "money-safety"
    : normalized.match(/rollout|feature flag|feature-flag|cohort|error rate|reliability|incident/)
      ? "rollout-safety"
      : "release-safety"
  return templates.find((template) => templateId(template) === preferred) ?? templates[0] ?? null
}

function firstNumber(pattern: RegExp, text: string): number | null {
  const match = text.match(pattern)
  if (!match?.[1]) return null
  const value = Number(match[1].replaceAll(",", ""))
  return Number.isFinite(value) ? value : null
}

function adaptLiveContext(template: WorkflowTemplate, message: string): Record<string, unknown> {
  const context = fixtureContext(template)
  const text = message.toLowerCase()
  const id = templateId(template)

  if (id === "release-safety") {
    const memoryMb = firstNumber(/(\d+(?:\.\d+)?)\s*(?:mi?b|mb)\b/i, message)
    if (memoryMb !== null) context.worker_memory_mb = memoryMb
    if (/runbook[^.]{0,40}(?:not validated|unvalidated|outdated|false)/.test(text)) context.runbook_validated = false
    if (/runbook[^.]{0,40}(?:validated|valid|true)/.test(text)) context.runbook_validated = true
    if (/(?:window|deployment)[^.]{0,30}(?:closed|blocked|false)/.test(text)) context.deployment_window_open = false
    if (/(?:window|deployment)[^.]{0,30}(?:open|approved|true)/.test(text)) context.deployment_window_open = true
  }

  if (id === "money-safety") {
    const days = firstNumber(/(\d+)\s*days?\b/i, message)
    if (days !== null) context.days_since_first_charge = days
    if (/non[-\s]?enterprise|not enterprise/.test(text)) context.is_enterprise_contract = false
    else if (/enterprise|contract/.test(text)) context.is_enterprise_contract = true
    if (/(?:no|without) [^.]{0,30}(?:exception|policy exception)/.test(text)) context.policy_exception_open = false
    else if (/exception/.test(text)) context.policy_exception_open = true
  }

  if (id === "rollout-safety") {
    const errorRate = firstNumber(/(\d+(?:\.\d+)?)\s*%[^.]{0,30}(?:error|failure)/i, message)
      ?? firstNumber(/(?:error|failure)[^.]{0,20}(\d+(?:\.\d+)?)\s*%/i, message)
    const sampleSize = firstNumber(/(\d[\d,]*)\s*(?:requests|events|observations)\b/i, message)
    if (errorRate !== null) context.error_rate_percent = errorRate
    if (sampleSize !== null) context.sample_size = sampleSize
    if (/(?:no|without) [^.]{0,30}(?:incident|outage)/.test(text)) context.incident_open = false
    else if (/incident|outage/.test(text)) context.incident_open = true
  }
  return context
}

function planWorkspaceRun(templates: WorkflowTemplate[], workspace: string, message: string): WorkspacePlan | null {
  const template = chooseTemplate(templates, message)
  if (!template) return null
  const baseEvidence = fixtureEvidence(template)
  const workspaceLabel = workspace.trim() || "Untitled workspace"
  const submittedEvidence: WorkflowEvidenceInput = {
    source_type: baseEvidence[0]?.source_type ?? "workspace_event",
    source_name: workspaceLabel,
    external_id: "workspace-message-" + Date.now(),
    occurred_at: new Date().toISOString(),
    excerpt: message.trim(),
    availability: "available",
    metadata: { workspace_label: workspaceLabel, adapter: "judge-workspace-chat" },
  }
  const evidence = [submittedEvidence, ...baseEvidence.slice(1)]
  const liveContext = adaptLiveContext(template, message)
  return {
    template,
    evidence,
    liveContext,
    summary: "Routed to " + (template.title ?? "the governed workflow") + ". Your message became the newest evidence record; unspecified required evidence and live fields use the clearly labeled sandbox fixture.",
  }
}

function logDescription(log: McpLog): string {
  return log.step === "initialize" ? "MCP session initialization" : log.step === "tools_list" ? "Tool discovery" : "Company Brain workflow evaluation"
}

export default function WorkflowPlayground() {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([])
  const [workspace, setWorkspace] = useState("Product operations")
  const [message, setMessage] = useState("")
  const [entries, setEntries] = useState<ConversationEntry[]>([starterMessage])
  const [plan, setPlan] = useState<WorkspacePlan | null>(null)
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState("I reviewed this sandbox decision and own the next action.")
  const [confirmed, setConfirmed] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [mcpSession, setMcpSession] = useState<DemoMcpSession | null>(null)
  const [mcpLogs, setMcpLogs] = useState<McpLog[]>([])
  const [mcpRuns, setMcpRuns] = useState<WorkflowRun[]>([])
  const [preparingMcp, setPreparingMcp] = useState(false)
  const sessionReady = useRef(false)
  const brief = briefFor(run)

  useEffect(() => {
    void getWorkflowTemplates().then((payload) => setTemplates(payload.templates)).catch(() => setError("Unable to load the server-defined workflow contracts.")).finally(() => setLoading(false))
  }, [])

  const refreshMcpRuns = useCallback(async () => {
    try {
      const payload = await getWorkflowRuns(20)
      setMcpRuns((payload.runs ?? []).map(asRun).filter((item): item is WorkflowRun => Boolean(item && item.execution_origin === "mcp")))
    } catch {
      // A temporary session may expire. The next explicit action surfaces the backend response.
    }
  }, [])

  useEffect(() => {
    if (!mcpSession) return
    void refreshMcpRuns()
    const timer = window.setInterval(() => void refreshMcpRuns(), 4000)
    return () => window.clearInterval(timer)
  }, [mcpSession, refreshMcpRuns])

  const prepareMcp = async (): Promise<DemoMcpSession> => {
    if (mcpSession) return mcpSession
    setPreparingMcp(true)
    setError(null)
    try {
      if (!sessionReady.current) {
        await createDemoSession()
        sessionReady.current = true
      }
      const created = await createDemoMcpSession()
      setMcpSession(created)
      return created
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : "Unable to create the temporary MCP connection."
      setError(detail)
      throw new Error(detail)
    } finally {
      setPreparingMcp(false)
    }
  }

  const append = (entry: ConversationEntry) => setEntries((current) => [...current, entry])

  const runWorkspace = async (prompt = message) => {
    const text = prompt.trim()
    if (!text || running || loading) return
    const nextPlan = planWorkspaceRun(templates, workspace, text)
    if (!nextPlan) {
      setError("The workflow catalog is not ready yet.")
      return
    }
    setRunning(true)
    setError(null)
    setRun(null)
    setConfirmed(false)
    setPlan(nextPlan)
    setMcpLogs([])
    setMessage("")
    append({ id: "user-" + Date.now(), role: "user", body: text })
    append({ id: "adapter-" + Date.now(), role: "tool", title: "Workspace adapter", body: nextPlan.summary })
    try {
      const connection = await prepareMcp()
      const response = await evaluateWorkflowThroughMcp({
        endpoint: connection.mcp_endpoint,
        apiKey: connection.api_key,
        templateId: templateId(nextPlan.template),
        evidence: nextPlan.evidence,
        liveContext: nextPlan.liveContext,
        onLog: (log) => setMcpLogs((current) => [...current, log]),
      })
      const evaluated = asRun(response)
      if (!evaluated) throw new Error("The MCP tool did not return an auditable DecisionBrief.")
      setRun(evaluated)
      const returnedBrief = briefFor(evaluated)
      append({ id: "result-" + Date.now(), role: "assistant", title: "Company Brain response", body: "MCP returned " + verdictLabel(returnedBrief?.verdict) + ". The accountable owner is " + (returnedBrief?.owner ?? "not reported") + ". Open the trace below to inspect evidence, Qwen memory, SAG, and the human handoff." })
      void refreshMcpRuns()
    } catch (caught) {
      const detail = caught instanceof Error ? caught.message : "Unable to evaluate this workspace message."
      setError(detail)
      append({ id: "error-" + Date.now(), role: "assistant", title: "Tool call did not complete", body: detail })
    } finally {
      setRunning(false)
    }
  }

  const confirm = async () => {
    if (!run || !note.trim()) return
    setConfirming(true)
    setError(null)
    try {
      const response = await postWorkflowOutcome(run.id, { approved: true, outcome: "confirmed_effective", actor: "judge", note: note.trim() })
      const updated = asRun(response)
      if (updated) setRun(updated)
      setConfirmed(true)
      append({ id: "outcome-" + Date.now(), role: "assistant", title: "Sandbox outcome recorded", body: "The human confirmation was recorded for this private sandbox. No external company action was executed." })
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record the sandbox outcome.")
    } finally {
      setConfirming(false)
    }
  }

  const resetConversation = () => {
    setEntries([starterMessage])
    setPlan(null)
    setRun(null)
    setMcpLogs([])
    setError(null)
    setConfirmed(false)
    setMessage("")
  }

  const suggestions = useMemo(() => [
    "GitHub production release: worker memory changed to 8 MiB and the runbook is not validated.",
    "Enterprise customer requests a refund after 41 days and has a negotiated contract exception.",
    "Feature flag expansion: 3.8% error rate across 2540 requests and an incident is still open.",
  ], [])

  return <PageFrame>
    <section className="max-w-5xl">
      <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Interactive workflow workspace</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-[#17212b]">Talk to Company Brain before an action happens.</h1>
      <p className="mt-3 max-w-3xl text-base leading-7 text-[#586575]">Bring a workspace message, watch it become source-backed evidence, then inspect the real MCP tool call and governed decision. This public lab accepts no credentials or company data.</p>
    </section>

    <section className="mt-8 overflow-hidden rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] shadow-[0_18px_55px_rgba(52,45,35,0.07)]">
      <div className="border-b border-[#e5ddd0] bg-[#f8f5ee] px-5 py-4 md:flex md:items-center md:justify-between md:px-7"><div className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-xl bg-[#e7edff] text-[#2148c7]"><MessageSquareText className="h-5 w-5" /></span><div><p className="text-sm font-semibold text-[#17212b]">Workspace conversation</p><p className="text-xs text-[#627083]">Browser-private sandbox session</p></div></div><button type="button" onClick={resetConversation} className="mt-3 inline-flex items-center gap-2 text-xs font-semibold text-[#526b86] hover:text-[#17212b] md:mt-0"><RotateCcw className="h-3.5 w-3.5" />New conversation</button></div>

      <div className="grid lg:grid-cols-[1.25fr_0.75fr]">
        <div className="min-w-0 border-b border-[#e5ddd0] p-5 md:p-7 lg:border-b-0 lg:border-r">
          <label className="block"><span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#627083]">Workspace label</span><input value={workspace} onChange={(event) => setWorkspace(event.target.value)} placeholder="e.g. Payments operations" className="mt-2 w-full rounded-xl border border-[#d9d2c6] bg-white px-3 py-2.5 text-sm text-[#17212b] outline-none focus:border-[#2f5eeb]" /><span className="mt-2 block text-xs leading-5 text-[#728092]">A local label for this session only. It does not create a connector or receive credentials.</span></label>

          <div className="mt-6 space-y-4" aria-live="polite">{entries.map((entry) => <ConversationBubble key={entry.id} entry={entry} />)}</div>

          <div className="mt-6 border-t border-[#e5ddd0] pt-5"><p className="text-xs font-semibold text-[#536170]">Try a real sandbox scenario</p><div className="mt-3 flex flex-wrap gap-2">{suggestions.map((suggestion) => <button key={suggestion} type="button" onClick={() => void runWorkspace(suggestion)} disabled={running || loading} className="rounded-full border border-[#d2dcec] bg-[#f6f8fe] px-3 py-2 text-left text-xs leading-5 text-[#36506f] hover:border-[#9db8e7] disabled:opacity-50">{suggestion}</button>)}</div></div>

          <form className="mt-6" onSubmit={(event) => { event.preventDefault(); void runWorkspace() }}><label className="block"><span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#627083]">Describe the decision and current facts</span><textarea value={message} onChange={(event) => setMessage(event.target.value)} placeholder="Example: The export worker now has 8 MiB memory and the runbook was not revalidated." className="mt-2 min-h-28 w-full rounded-2xl border border-[#d9d2c6] bg-white px-4 py-3 text-sm leading-6 text-[#17212b] outline-none focus:border-[#2f5eeb]" /></label><div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="max-w-md text-xs leading-5 text-[#667788]">Company Brain routes only release, money, and rollout safety contracts in this judge sandbox.</p><button type="submit" disabled={running || loading || !message.trim()} className="inline-flex items-center gap-2 rounded-xl bg-[#17212b] px-4 py-3 text-sm font-semibold text-white hover:bg-[#293846] disabled:opacity-50">{running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}{running ? "Calling Company Brain" : "Send to Company Brain"}</button></div></form>
        </div>

        <aside className="bg-[#f6f8fe] p-5 md:p-7"><div className="flex items-center gap-2"><Wrench className="h-4 w-4 text-[#2f5eeb]" /><p className="text-xs font-bold uppercase tracking-[0.15em] text-[#2f5eeb]">Live tool feed</p></div><h2 className="mt-3 text-lg font-semibold text-[#17212b]">Nothing is hidden behind the chat.</h2><p className="mt-2 text-sm leading-6 text-[#596778]">The conversation never invents a decision. It surfaces the actual MCP transport and the normalized payload sent to Company Brain.</p>
          <ToolFeed logs={mcpLogs} running={running} />
          <PayloadProof plan={plan} />
          <ConnectionProof session={mcpSession} preparing={preparingMcp} onPrepare={() => void prepareMcp()} />
          {mcpRuns.length > 0 && <McpHistory runs={mcpRuns} />}
        </aside>
      </div>
    </section>

    {error && <div className="mt-6 rounded-2xl border border-[#bc3f34]/30 bg-[#fce9e6] p-4 text-sm text-[#96332b]">{error}</div>}
    {brief && <DecisionTrace run={run} brief={brief} />}
    {brief && <section className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]"><article className="rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-6 shadow-[0_18px_55px_rgba(52,45,35,0.07)]"><span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide ${verdictTone(brief.verdict)}`}>{verdictLabel(brief.verdict)}</span><h2 className="mt-5 text-2xl font-semibold tracking-tight text-[#17212b]">{brief.recommended_next_action ?? "No action returned"}</h2><AuditProof brief={brief} /></article><article className="rounded-3xl border border-[#d7e4df] bg-[#edf8f4] p-6"><h2 className="font-semibold text-[#1d604f]">Human confirmation</h2><p className="mt-3 text-sm leading-6 text-[#3a6559]">The owner is <strong>{brief.owner ?? "not reported"}</strong>. This records a sandbox outcome only.</p>{confirmed ? <div className="mt-6 flex items-center gap-2 rounded-xl border border-[#2e7763]/25 bg-white/60 px-4 py-3 text-sm font-medium text-[#1d604f]"><Check className="h-4 w-4" />Sandbox outcome recorded</div> : <><textarea value={note} onChange={(event) => setNote(event.target.value)} className="mt-5 min-h-28 w-full rounded-xl border border-[#b9d4c9] bg-white px-3 py-3 text-sm leading-6 text-[#17212b] outline-none focus:border-[#2e7763]" /><button type="button" onClick={() => void confirm()} disabled={confirming || !note.trim()} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#1d604f] px-4 py-3 text-sm font-semibold text-white hover:bg-[#174d40] disabled:opacity-50">{confirming && <LoaderCircle className="h-4 w-4 animate-spin" />}Confirm sandbox action</button></>}</article></section>}
  </PageFrame>
}

function ConversationBubble({ entry }: { entry: ConversationEntry }) {
  const isUser = entry.role === "user"
  const isTool = entry.role === "tool"
  const Icon = isUser ? UserRound : isTool ? Wrench : Bot
  const tone = isUser ? "border-[#c7d5ef] bg-[#edf3ff]" : isTool ? "border-[#d7e4df] bg-[#f1faf6]" : "border-[#e2ddd2] bg-[#faf7f0]"
  return <article className={`rounded-2xl border p-4 ${tone}`}><div className="flex items-center gap-2 text-xs font-semibold text-[#435264]"><Icon className="h-3.5 w-3.5" />{entry.title ?? (isUser ? "You" : isTool ? "Tool activity" : "Company Brain")}</div><p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-[#263544]">{entry.body}</p></article>
}

function ToolFeed({ logs, running }: { logs: McpLog[]; running: boolean }) {
  return <div className="mt-5 space-y-2">{logs.length === 0 ? <div className="rounded-xl border border-[#dbe3f2] bg-white p-3 text-xs leading-5 text-[#627083]">Send a message to see MCP initialize, tool discovery, and the live workflow call.</div> : logs.map((log, index) => <div key={log.step + String(index)} className="rounded-xl border border-[#dbe3f2] bg-white p-3"><div className="flex items-center justify-between gap-3"><p className="text-xs font-semibold text-[#263544]">{logDescription(log)}</p><span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#43678f]">{log.status}</span></div><p className="mt-1 font-mono text-[11px] text-[#52718e]">{log.step}</p><p className="mt-1 text-xs leading-5 text-[#596778]">{log.detail}</p></div>)}{running && <div className="flex items-center gap-2 px-1 text-xs text-[#42658b]"><LoaderCircle className="h-3.5 w-3.5 animate-spin" />Waiting for the backend tool response.</div>}</div>
}

function PayloadProof({ plan }: { plan: WorkspacePlan | null }) {
  if (!plan) return null
  return <details className="group mt-5 rounded-xl border border-[#d8e0ef] bg-white"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-3 text-xs font-semibold text-[#36506f]">Evidence and live context sent to MCP <ChevronDown className="h-4 w-4 transition group-open:rotate-180" /></summary><div className="space-y-3 border-t border-[#e3e9f3] p-3"><p className="text-xs leading-5 text-[#596778]">{plan.summary}</p><div><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#627083]">Evidence</p>{plan.evidence.map((item, index) => <div key={item.external_id ?? String(index)} className="mt-2 rounded-lg bg-[#f8faff] p-2 text-xs leading-5 text-[#425872]"><span className="font-semibold">{item.source_name}</span>: {item.excerpt}</div>)}</div><div><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#627083]">Live context</p><pre className="mt-2 overflow-auto rounded-lg bg-[#17212b] p-2 text-[10px] leading-5 text-[#d9e2ec]">{JSON.stringify(plan.liveContext, null, 2)}</pre></div></div></details>
}

function ConnectionProof({ session, preparing, onPrepare }: { session: DemoMcpSession | null; preparing: boolean; onPrepare: () => void }) {
  return <details className="group mt-5 rounded-xl border border-[#cce3da] bg-white"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-3 text-xs font-semibold text-[#1d604f]">{session ? "Authenticated MCP connection ready" : "Create an MCP connection"}<ChevronDown className="h-4 w-4 transition group-open:rotate-180" /></summary><div className="border-t border-[#dcebe4] p-3">{session ? <><p className="text-xs leading-5 text-[#52766a]">This browser-private key has {session.permissions} scopes and expires automatically. It can evaluate a workflow but cannot execute an external action.</p><details className="mt-3 rounded-lg border border-[#dcebe4] px-2 py-2"><summary className="cursor-pointer text-[11px] font-semibold text-[#52766a]">Use with real-workflow/ locally</summary><div className="mt-2 rounded-lg bg-[#17212b] p-2 font-mono text-[10px] leading-5 text-[#d9e8e1]"><p>BRAIN_MCP_URL={session.mcp_endpoint}</p><p className="break-all">BRAIN_API_KEY={session.api_key}</p></div></details></> : <button type="button" onClick={onPrepare} disabled={preparing} className="inline-flex items-center gap-2 rounded-lg bg-[#1d604f] px-3 py-2 text-xs font-semibold text-white hover:bg-[#174d40] disabled:opacity-50">{preparing ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <TerminalSquare className="h-3.5 w-3.5" />}{preparing ? "Preparing" : "Create temporary MCP connection"}</button>}</div></details>
}

function McpHistory({ runs }: { runs: WorkflowRun[] }) {
  return <details className="group mt-5 rounded-xl border border-[#d8e0ef] bg-white"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-3 py-3 text-xs font-semibold text-[#36506f]">MCP execution history ({runs.length})<ChevronDown className="h-4 w-4 transition group-open:rotate-180" /></summary><div className="space-y-2 border-t border-[#e3e9f3] p-3">{runs.slice(0, 4).map((item) => { const brief = briefFor(item); return <div key={item.id} className="rounded-lg bg-[#f8faff] p-2 text-xs text-[#425872]"><div className="flex items-center justify-between gap-2"><span className="font-mono text-[10px]">{item.id}</span><span className="font-bold uppercase text-[10px]">{verdictLabel(brief?.verdict)}</span></div><p className="mt-1">{brief?.owner ?? "Owner not reported"}</p></div> })}</div></details>
}
