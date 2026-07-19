import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { ArrowRight, Bot, Check, CircleDot, FileInput, Github, Headphones, LoaderCircle, Radio, RotateCcw, ServerCog, ShieldCheck, TerminalSquare, UserRound } from "lucide-react"
import { createDemoMcpSession, createDemoSession, getWorkflowRuns, getWorkflowTemplates, postWorkflowOutcome, type DemoMcpSession, type WorkflowEvidenceInput } from "../lib/api"
import { evaluateWorkflowThroughMcp, type McpLog } from "../lib/mcp"
import type { WorkflowRun, WorkflowTemplate } from "../types/schema"
import { AuditProof, DecisionTrace, PageFrame, asRun, briefFor, inferenceText, verdictLabel, verdictTone } from "./Simulation"

type EditableEvidence = WorkflowEvidenceInput & { key: string }

function templateId(template: WorkflowTemplate): string { return template.template_id ?? template.id ?? "" }

function readFixture(template: WorkflowTemplate): { evidence: EditableEvidence[]; live: Record<string, string | boolean> } {
  const fixture = template.demo_fixture as Record<string, unknown> | undefined
  const rawEvidence = Array.isArray(fixture?.evidence) ? fixture.evidence : []
  const evidence = rawEvidence.map((entry, index) => {
    const value = entry as Record<string, unknown>
    return {
      key: `${String(value.source_type ?? "source")}-${index}`,
      source_type: String(value.source_type ?? "unknown"),
      source_name: typeof value.source_name === "string" ? value.source_name : undefined,
      external_id: typeof value.external_id === "string" ? value.external_id : "",
      excerpt: typeof value.excerpt === "string" ? value.excerpt : "",
      occurred_at: typeof value.occurred_at === "string" ? value.occurred_at : new Date().toISOString(),
      availability: typeof value.availability === "string" ? value.availability : "available",
      metadata: (value.metadata as Record<string, unknown> | undefined) ?? {},
    }
  })
  const rawLive = fixture?.live_context && typeof fixture.live_context === "object" ? fixture.live_context as Record<string, unknown> : {}
  const live = Object.fromEntries(Object.entries(rawLive).map(([key, value]) => [key, typeof value === "boolean" ? value : String(value)]))
  return { evidence, live }
}

function liveSchema(template: WorkflowTemplate): Array<{ name: string; value_type: string; description: string }> {
  return Array.isArray(template.live_context_schema) ? template.live_context_schema as Array<{ name: string; value_type: string; description: string }> : []
}

export default function WorkflowPlayground() {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([])
  const [selectedId, setSelectedId] = useState("release-safety")
  const [evidence, setEvidence] = useState<EditableEvidence[]>([])
  const [liveContext, setLiveContext] = useState<Record<string, string | boolean>>({})
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

  useEffect(() => {
    void getWorkflowTemplates().then((payload) => {
      setTemplates(payload.templates)
      const first = payload.templates.find((template) => templateId(template) === "release-safety") ?? payload.templates[0]
      if (first) {
        setSelectedId(templateId(first))
        const sample = readFixture(first)
        setEvidence(sample.evidence)
        setLiveContext(sample.live)
      }
    }).catch(() => setError("Unable to load the server-defined workflow templates.")).finally(() => setLoading(false))
  }, [])

  const selected = useMemo(() => templates.find((template) => templateId(template) === selectedId) ?? null, [selectedId, templates])
  const brief = briefFor(run)

  const refreshMcpRuns = useCallback(async () => {
    try {
      const payload = await getWorkflowRuns(20)
      setMcpRuns((payload.runs ?? []).map(asRun).filter((item): item is WorkflowRun => Boolean(item && item.execution_origin === "mcp")))
    } catch {
      // A temporary session may have expired; the next explicit MCP action
      // surfaces a clear server error instead of fabricating run history.
    }
  }, [])

  useEffect(() => {
    if (!mcpSession) return
    void refreshMcpRuns()
    const timer = window.setInterval(() => void refreshMcpRuns(), 4000)
    return () => window.clearInterval(timer)
  }, [mcpSession, refreshMcpRuns])

  const reset = () => {
    if (!selected) return
    const sample = readFixture(selected)
    setEvidence(sample.evidence)
    setLiveContext(sample.live)
    setRun(null)
    setConfirmed(false)
    setError(null)
  }

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
      const message = caught instanceof Error ? caught.message : "Unable to create the temporary MCP connection."
      setError(message)
      throw new Error(message)
    } finally {
      setPreparingMcp(false)
    }
  }

  const evaluate = async () => {
    if (!selected) return
    setRunning(true)
    setRun(null)
    setConfirmed(false)
    setError(null)
    try {
      const connection = await prepareMcp()
      const context = Object.fromEntries(liveSchema(selected).map((field) => {
        const value = liveContext[field.name]
        return [field.name, field.value_type === "number" ? Number(value) : value]
      }))
      setMcpLogs([])
      const response = await evaluateWorkflowThroughMcp({
        endpoint: connection.mcp_endpoint,
        apiKey: connection.api_key,
        templateId: templateId(selected),
        evidence: evidence.map(({ key: _key, ...item }) => item),
        liveContext: context,
        onLog: (entry) => setMcpLogs((current) => [...current, entry]),
      })
      const evaluated = asRun(response)
      if (!evaluated) throw new Error("The workflow engine did not return an auditable DecisionBrief.")
      setRun(evaluated)
      void refreshMcpRuns()
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to evaluate this sandbox workflow.")
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
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record the sandbox outcome.")
    } finally {
      setConfirming(false)
    }
  }

  return <PageFrame>
    <div className="max-w-4xl"><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Workflow connection lab</p><h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-[#17212b]">Connect Company Brain to a workflow.</h1><p className="mt-3 max-w-3xl text-base leading-7 text-[#586575]">Choose a safe synthetic company workflow, run its event through Company Brain, and inspect the real evidence → Qwen memory → SAG → human decision path.</p></div>
    {!loading && selected && <ConnectionMap template={selected} evidenceCount={evidence.length} />}
    {!loading && selected && <McpConnectionPanel session={mcpSession} logs={mcpLogs} runs={mcpRuns} preparing={preparingMcp} onPrepare={() => void prepareMcp()} />}
    {error && <div className="mt-7 rounded-2xl border border-[#bc3f34]/30 bg-[#fce9e6] p-4 text-sm text-[#96332b]">{error}</div>}
    <section className="mt-8 rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-5 shadow-[0_18px_55px_rgba(52,45,35,0.07)] md:p-7">
      {loading || !selected ? <div className="h-72 animate-pulse rounded-2xl bg-[#f3eee4]" /> : <>
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><div><p className="text-xs font-bold uppercase tracking-[0.13em] text-[#627083]">Connected MCP workflow</p><h2 className="mt-2 text-lg font-semibold text-[#17212b]">{selected.title ?? "Release Safety"}</h2><p className="mt-1 text-sm text-[#627083]">The public lab runs one real release workflow through evaluate_workflow over MCP.</p></div><button type="button" onClick={reset} className="inline-flex items-center gap-2 text-sm font-semibold text-[#39506a] hover:text-[#17212b]"><RotateCcw className="h-4 w-4" />Reset sample</button></div>
        <div className="mt-8 grid gap-7 lg:grid-cols-[1.15fr_0.85fr]"><div><SectionHeading label="1" title="Evidence" subtitle="Edit the source excerpts. No credentials are accepted." /> <div className="mt-4 space-y-3">{evidence.map((item, index) => <article key={item.key} className="rounded-2xl border border-[#e1d9cd] bg-[#faf7f0] p-4"><p className="text-[10px] font-bold uppercase tracking-[0.13em] text-[#667488]">{item.source_name ?? item.source_type}</p><label className="mt-3 block text-xs font-semibold text-[#263544]">Reference<input value={item.external_id ?? ""} onChange={(event) => setEvidence((current) => current.map((entry, position) => position === index ? { ...entry, external_id: event.target.value } : entry))} className="mt-1.5 w-full rounded-lg border border-[#d9d2c6] bg-white px-3 py-2 text-sm font-normal outline-none focus:border-[#2f5eeb]" /></label><label className="mt-3 block text-xs font-semibold text-[#263544]">What changed<textarea value={item.excerpt} onChange={(event) => setEvidence((current) => current.map((entry, position) => position === index ? { ...entry, excerpt: event.target.value } : entry))} className="mt-1.5 min-h-20 w-full rounded-lg border border-[#d9d2c6] bg-white px-3 py-2 text-sm font-normal leading-6 outline-none focus:border-[#2f5eeb]" /></label></article>)}</div></div>
          <div><SectionHeading label="2" title="Live context" subtitle="The deterministic safety rule evaluates these current values." /> <div className="mt-4 space-y-3">{liveSchema(selected).map((field) => <label key={field.name} className="block rounded-2xl border border-[#e1d9cd] bg-[#faf7f0] p-4"><span className="text-sm font-semibold text-[#263544]">{field.name.replaceAll("_", " ")}</span><span className="mt-1 block text-xs leading-5 text-[#6b7784]">{field.description}</span>{field.value_type === "boolean" ? <select value={String(liveContext[field.name])} onChange={(event) => setLiveContext((current) => ({ ...current, [field.name]: event.target.value === "true" }))} className="mt-3 w-full rounded-lg border border-[#d9d2c6] bg-white px-3 py-2 text-sm outline-none focus:border-[#2f5eeb]"><option value="true">True</option><option value="false">False</option></select> : <input type="number" value={String(liveContext[field.name] ?? "")} onChange={(event) => setLiveContext((current) => ({ ...current, [field.name]: event.target.value }))} className="mt-3 w-full rounded-lg border border-[#d9d2c6] bg-white px-3 py-2 text-sm outline-none focus:border-[#2f5eeb]" />}</label>)}</div></div></div>
        <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-[#e5ddd0] pt-6"><button type="button" onClick={() => void evaluate()} disabled={running} className="inline-flex items-center gap-2 rounded-xl bg-[#17212b] px-5 py-3 text-sm font-semibold text-[#fffdf7] hover:bg-[#293846] disabled:opacity-50">{running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}{running ? "Calling MCP evaluate_workflow" : "Run real workflow through MCP"}</button><span className="text-xs text-[#6b7280]">Authenticated Streamable HTTP · private sandbox · no external action</span></div>
      </>}
    </section>
    {brief && <DecisionTrace run={run} brief={brief} />}
    {brief && <section className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]"><article className="rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-6 shadow-[0_18px_55px_rgba(52,45,35,0.07)]"><span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide ${verdictTone(brief.verdict)}`}>{verdictLabel(brief.verdict)}</span><h2 className="mt-5 text-2xl font-semibold tracking-tight text-[#17212b]">{brief.recommended_next_action ?? "No action returned"}</h2><p className="mt-4 text-sm leading-6 text-[#536170]">{inferenceText(brief)}</p><AuditProof brief={brief} /></article><article className="rounded-3xl border border-[#d7e4df] bg-[#edf8f4] p-6"><h2 className="font-semibold text-[#1d604f]">Human confirmation</h2><p className="mt-3 text-sm leading-6 text-[#3a6559]">The owner is <strong>{brief.owner ?? "not reported"}</strong>. This confirmation records only a sandbox outcome.</p>{confirmed ? <div className="mt-6 flex items-center gap-2 rounded-xl border border-[#2e7763]/25 bg-white/60 px-4 py-3 text-sm font-medium text-[#1d604f]"><Check className="h-4 w-4" />Sandbox outcome recorded</div> : <><textarea value={note} onChange={(event) => setNote(event.target.value)} className="mt-5 min-h-28 w-full rounded-xl border border-[#b9d4c9] bg-white px-3 py-3 text-sm leading-6 text-[#17212b] outline-none focus:border-[#2e7763]" /><button type="button" onClick={() => void confirm()} disabled={confirming || !note.trim()} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#1d604f] px-4 py-3 text-sm font-semibold text-white hover:bg-[#174d40] disabled:opacity-50">{confirming && <LoaderCircle className="h-4 w-4 animate-spin" />}Confirm sandbox action</button></>}</article></section>}
  </PageFrame>
}

function SectionHeading({ label, title, subtitle }: { label: string; title: string; subtitle: string }) {
  return <div><span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[#e7edff] text-[10px] font-bold text-[#2148c7]">{label}</span><h2 className="mt-3 text-lg font-semibold text-[#17212b]">{title}</h2><p className="mt-1 text-sm leading-6 text-[#627083]">{subtitle}</p></div>
}

function connectionProfile(template: WorkflowTemplate): { title: string; event: string; systems: Array<{ label: string; icon: "github" | "support" | "reliability" | "server" }> } {
  switch (templateId(template)) {
    case "release-safety":
      return { title: "GitHub release pipeline", event: "A merged configuration change is about to reach deployment.", systems: [{ label: "GitHub", icon: "github" }, { label: "Runtime telemetry", icon: "server" }] }
    case "money-safety":
      return { title: "Support refund desk", event: "A customer is eligible for an automatic refund.", systems: [{ label: "Support portal", icon: "support" }, { label: "Billing policy + CRM", icon: "server" }] }
    case "rollout-safety":
      return { title: "Feature rollout control", event: "A feature flag expansion is scheduled.", systems: [{ label: "Observability + incidents", icon: "reliability" }, { label: "Feature flags", icon: "server" }] }
    default:
      return { title: template.title ?? "Company workflow", event: template.description ?? "A company event needs a governed decision.", systems: [{ label: "Company system", icon: "server" }] }
  }
}

function SystemMark({ type }: { type: "github" | "support" | "reliability" | "server" }) {
  const Icon = type === "github" ? Github : type === "support" ? Headphones : type === "reliability" ? Radio : ServerCog
  return <Icon className="h-4 w-4" />
}

function ConnectionMap({ template, evidenceCount }: { template: WorkflowTemplate; evidenceCount: number }) {
  const profile = connectionProfile(template)
  return <section className="mt-7 rounded-3xl border border-[#cbd6e8] bg-[#f6f8fe] p-5 shadow-[0_18px_55px_rgba(47,94,235,0.07)] md:p-7">
    <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between"><div><div className="inline-flex items-center gap-2 rounded-full border border-[#bcd0ee] bg-[#edf3ff] px-3 py-1 text-[10px] font-bold uppercase tracking-[0.15em] text-[#2f5eeb]"><CircleDot className="h-3 w-3" /> Synthetic adapter</div><h2 className="mt-3 text-xl font-semibold text-[#17212b]">Attach the workflow, then run an event.</h2><p className="mt-1 max-w-2xl text-sm leading-6 text-[#596778]">This uses safe sample systems. The resulting Company Brain call, Qwen compilation, and SAG decision are real sandbox responses.</p></div><span className="inline-flex w-fit items-center gap-2 rounded-full border border-[#c6d6ed] bg-white px-3 py-1.5 text-xs font-semibold text-[#39506a]"><FileInput className="h-3.5 w-3.5" />{evidenceCount} source event{evidenceCount === 1 ? "" : "s"}</span></div>
    <div className="mt-6 rounded-2xl border border-[#d9e2f0] bg-white/70 p-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#58709a]">Selected workflow</p>
      <h3 className="mt-1 font-semibold text-[#17212b]">{profile.title}</h3>
      <p className="mt-1 text-sm text-[#617085]">{profile.event}</p>
      <div className="mt-5 grid items-stretch gap-2 text-center sm:grid-cols-[1fr_auto_1fr_auto_1fr] sm:gap-3">
        <ConnectionNode icon={<SystemMark type={profile.systems[0]?.icon ?? "server"} />} title={profile.systems.map((system) => system.label).join(" + ")} detail="Synthetic company systems" />
        <ArrowRight className="mx-auto hidden h-4 w-4 self-center text-[#718096] sm:block" />
        <ConnectionNode icon={<ShieldCheck className="h-4 w-4" />} title="Company Brain" detail="Evidence · Qwen · SAG" active />
        <ArrowRight className="mx-auto hidden h-4 w-4 self-center text-[#718096] sm:block" />
        <ConnectionNode icon={<UserRound className="h-4 w-4" />} title={template.owner_role ?? "Human owner"} detail="Receives recommendation" />
      </div>
    </div>
    <div className="mt-5 grid gap-2 sm:grid-cols-4">
      <ConnectionStage number="01" title="Source event" detail="Synthetic company system sends evidence." />
      <ConnectionStage number="02" title="Governed memory" detail="Qwen compiles cited context." />
      <ConnectionStage number="03" title="Safety gate" detail="SAG checks current live values." />
      <ConnectionStage number="04" title="Human handoff" detail="Owner receives an auditable brief." />
    </div>
    <p className="mt-4 flex items-start gap-2 text-xs leading-5 text-[#607080]"><Bot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#2f5eeb]" />Company Brain is the governed checkpoint inside the workflow; it does not execute a deployment, refund, or rollout.</p>
  </section>
}

function ConnectionNode({ icon, title, detail, active = false }: { icon: React.ReactNode; title: string; detail: string; active?: boolean }) {
  return <div className={"flex min-h-20 flex-col items-center justify-center rounded-xl border px-3 py-3 " + (active ? "border-[#a9c2f0] bg-[#eaf0ff] text-[#2148c7]" : "border-[#dbe1e9] bg-white text-[#435264]")}><span>{icon}</span><p className="mt-2 text-xs font-semibold text-[#263544]">{title}</p><p className="mt-1 text-[10px] leading-4 text-[#718096]">{detail}</p></div>
}

function ConnectionStage({ number, title, detail }: { number: string; title: string; detail: string }) {
  return <div className="rounded-xl border border-[#d9e2f0] bg-white/70 p-3"><p className="text-[10px] font-bold uppercase tracking-[0.13em] text-[#60708a]">{number}</p><p className="mt-3 text-xs font-semibold text-[#263544]">{title}</p><p className="mt-1 text-[11px] leading-4 text-[#64748b]">{detail}</p></div>
}

function McpConnectionPanel({ session, logs, runs, preparing, onPrepare }: { session: DemoMcpSession | null; logs: McpLog[]; runs: WorkflowRun[]; preparing: boolean; onPrepare: () => void }) {
  return <section className="mt-6 rounded-3xl border border-[#d7e4df] bg-[#f1faf6] p-5 md:p-6">
    <div className="flex flex-col justify-between gap-4 md:flex-row md:items-start"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-[#1d7660]">Live MCP integration</p><h2 className="mt-2 text-xl font-semibold text-[#17212b]">Use the same connection from a real workflow.</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-[#41685d]">This page calls the authenticated remote MCP endpoint directly. The real-workflow folder uses the same JSON-RPC transport and temporary sandbox key.</p></div>{session ? <span className="inline-flex w-fit items-center gap-2 rounded-full border border-[#b9d9cc] bg-white px-3 py-1.5 text-xs font-semibold text-[#1d604f]"><Check className="h-3.5 w-3.5" />MCP connection ready</span> : <button type="button" onClick={onPrepare} disabled={preparing} className="inline-flex w-fit items-center gap-2 rounded-xl bg-[#1d604f] px-4 py-3 text-sm font-semibold text-white hover:bg-[#174d40] disabled:opacity-50">{preparing ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <TerminalSquare className="h-4 w-4" />}{preparing ? "Preparing connection" : "Create temporary MCP connection"}</button>}</div>
    {session ? <div className="mt-5 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]"><div className="rounded-2xl border border-[#cce3da] bg-white p-4"><p className="text-[10px] font-bold uppercase tracking-[0.13em] text-[#52766a]">Copy into real-workflow/.env</p><div className="mt-3 space-y-2 rounded-xl bg-[#17212b] p-3 font-mono text-[11px] leading-5 text-[#d9e8e1]"><p>BRAIN_MCP_URL={session.mcp_endpoint}</p><p className="break-all">BRAIN_API_KEY={session.api_key}</p></div><p className="mt-3 text-xs leading-5 text-[#52766a]">Scoped to {session.permissions}; expires at {new Date(session.expires_at).toLocaleTimeString()}. It can evaluate workflows but cannot record human outcomes or execute company actions.</p></div><div className="rounded-2xl border border-[#cce3da] bg-white p-4"><p className="text-[10px] font-bold uppercase tracking-[0.13em] text-[#52766a]">Run it locally</p><ol className="mt-3 space-y-2 text-sm leading-5 text-[#2c5146]"><li>1. Open the real-workflow folder.</li><li>2. Install its requirements.</li><li>3. Run python run_release_workflow.py.</li></ol><p className="mt-3 text-xs leading-5 text-[#52766a]">This page polls the same sandbox organization and lists MCP runs below.</p></div></div> : <p className="mt-4 text-sm leading-6 text-[#41685d]">Create a disposable connection first. No long-lived or shared API key is exposed to the public judge route.</p>}
    {(logs.length > 0 || runs.length > 0) && <div className="mt-5 grid gap-4 lg:grid-cols-2"><McpLogList logs={logs} /><McpRunList runs={runs} /></div>}
  </section>
}

function McpLogList({ logs }: { logs: McpLog[] }) {
  return <div className="rounded-2xl border border-[#cce3da] bg-white p-4"><p className="text-[10px] font-bold uppercase tracking-[0.13em] text-[#52766a]">This page's MCP calls</p>{logs.length === 0 ? <p className="mt-3 text-sm text-[#52766a]">Run the workflow to see initialize, tools/list, and evaluate_workflow responses.</p> : <div className="mt-3 space-y-2">{logs.map((log, index) => <div key={log.step + String(index)} className="rounded-xl border border-[#e0eee7] bg-[#f8fcfa] p-3"><div className="flex items-center justify-between gap-3"><p className="font-mono text-xs font-semibold text-[#1d604f]">{log.step}</p><span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#6b847b]">{log.status}</span></div><p className="mt-1 text-xs leading-5 text-[#45665c]">{log.detail}</p></div>)}</div>}</div>
}

function McpRunList({ runs }: { runs: WorkflowRun[] }) {
  return <div className="rounded-2xl border border-[#cce3da] bg-white p-4"><p className="text-[10px] font-bold uppercase tracking-[0.13em] text-[#52766a]">MCP execution log</p>{runs.length === 0 ? <p className="mt-3 text-sm text-[#52766a]">External workflow runs using this temporary key will appear here.</p> : <div className="mt-3 space-y-2">{runs.slice(0, 4).map((item) => { const brief = briefFor(item); const memories = brief?.memory_refs ?? []; return <div key={item.id} className="rounded-xl border border-[#e0eee7] bg-[#f8fcfa] p-3"><div className="flex flex-wrap items-center justify-between gap-2"><p className="font-mono text-[11px] font-semibold text-[#1d604f]">{item.id}</p><span className="rounded-full border border-[#b9d9cc] bg-white px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[#1d604f]">{verdictLabel(brief?.verdict)}</span></div><p className="mt-2 text-xs text-[#45665c]">Owner: {brief?.owner ?? "not reported"}</p>{memories.map((memory, index) => <p key={memory.memory_id ?? String(index)} className="mt-2 rounded-lg border border-[#e0eee7] bg-white px-2 py-2 text-[11px] leading-4 text-[#45665c]"><span className="font-semibold text-[#1d604f]">{String(memory.provenance?.kind ?? "memory").replaceAll("_", " ")}</span>: {memory.summary ?? "No summary returned"}</p>)}</div> })}</div>}</div>
}
