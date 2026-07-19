import { useCallback, useEffect, useMemo, useState } from "react"
import {
  ArrowRight,
  Check,
  ChevronDown,
  CircleAlert,
  Cloud,
  Database,
  FileText,
  Github,
  LoaderCircle,
  MessageSquareText,
  ShieldCheck,
  Sparkles,
} from "lucide-react"
import { Link } from "react-router-dom"
import {
  createDemoMcpSession,
  createDemoSession,
  getRealityOverview,
  replayIncident,
  type RealityMemory,
  type SourceConnection,
  type SourceEvent,
} from "../lib/api"
import { evaluateWorkflowThroughMcp, type McpLog } from "../lib/mcp"
import type { DecisionBrief, WorkflowRun } from "../types/schema"

type TraceStep = {
  id: string
  title: string
  detail: string
  state: "idle" | "running" | "complete" | "fallback" | "error"
}

const initialSteps: TraceStep[] = [
  { id: "sources", title: "Source evidence", detail: "Awaiting a signed or scoped source event.", state: "idle" },
  { id: "memory", title: "Qwen Reality Memory", detail: "Awaiting source normalization and compilation.", state: "idle" },
  { id: "mcp", title: "MCP decision gateway", detail: "Awaiting an agent/workflow safety check.", state: "idle" },
  { id: "human", title: "Human owner", detail: "No company action is executed by this console.", state: "idle" },
]

function statusTone(status: string) {
  if (status === "connected" || status === "decision_ready" || status === "suspended") return "border-emerald-200 bg-emerald-50 text-emerald-800"
  if (status === "setup_required" || status === "review_required") return "border-amber-200 bg-amber-50 text-amber-800"
  if (status === "contract_ready") return "border-blue-200 bg-blue-50 text-blue-800"
  if (status === "failed") return "border-rose-200 bg-rose-50 text-rose-800"
  return "border-slate-200 bg-slate-50 text-slate-600"
}

function sourceIcon(provider: string) {
  if (provider === "slack") return MessageSquareText
  if (provider === "github") return Github
  if (provider === "google_drive") return FileText
  return Cloud
}

function asBrief(run: WorkflowRun | null): DecisionBrief | null {
  if (!run) return null
  return (run.decision_brief ?? run.brief ?? null) as DecisionBrief | null
}

function text(value: unknown, fallback = "Not reported") {
  return typeof value === "string" && value.trim() ? value : fallback
}

function memoryState(memory: RealityMemory) {
  if (memory.status === "superseded") return "Superseded"
  return memory.qwen_generated ? "Qwen compiled" : "Evidence only"
}

export default function Landing() {
  const [connections, setConnections] = useState<SourceConnection[]>([])
  const [events, setEvents] = useState<SourceEvent[]>([])
  const [memories, setMemories] = useState<RealityMemory[]>([])
  const [steps, setSteps] = useState<TraceStep[]>(initialSteps)
  const [logs, setLogs] = useState<McpLog[]>([])
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    const overview = await getRealityOverview()
    setConnections(overview.connections)
    setEvents(overview.events)
    setMemories(overview.memories)
  }, [])

  useEffect(() => { void refresh().catch(() => setError("Company Brain could not load its source status.")) }, [refresh])

  const setStep = (id: string, state: TraceStep["state"], detail: string) => {
    setSteps((current) => current.map((item) => item.id === id ? { ...item, state, detail } : item))
  }

  const runIncident = async () => {
    setRunning(true)
    setError(null)
    setRun(null)
    setLogs([])
    setSteps(initialSteps)
    try {
      await createDemoSession()
      setStep("sources", "running", "Creating source-backed evidence in this browser-private sandbox.")
      const replay = await replayIncident()
      setEvents(replay.events)
      setStep("sources", "complete", `${replay.events.length} source records were persisted with hashes, timestamps, and provenance.`)
      const qwenStatus = replay.events.every((event) => event.qwen_status.startsWith("compiled"))
      setStep(
        "memory",
        qwenStatus ? "complete" : "fallback",
        qwenStatus
          ? "Qwen compiled ephemeral Reality Memory; prior claims remain visible rather than overwritten."
          : "Qwen was unavailable for at least one source; the backend retained evidence without claiming compilation.",
      )
      setStep("mcp", "running", "Calling authenticated Streamable HTTP MCP evaluate_workflow.")
      const session = await createDemoMcpSession()
      const evaluated = await evaluateWorkflowThroughMcp({
        endpoint: session.mcp_endpoint,
        apiKey: session.api_key,
        templateId: replay.workflow.template_id,
        evidence: replay.workflow.evidence,
        liveContext: replay.workflow.live_context,
        onLog: (entry) => setLogs((current) => [...current.filter((item) => item.step !== entry.step), entry]),
      })
      setRun(evaluated)
      const brief = asBrief(evaluated)
      setStep("mcp", "complete", `MCP returned ${String(brief?.verdict ?? "a backend verdict").replaceAll("_", " ")}.`)
      setStep("human", "complete", `${text(brief?.owner)} owns the next step. No external company action was executed.`)
      await refresh()
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The live incident trace could not complete."
      setError(message)
      setStep("mcp", "error", message)
    } finally {
      setRunning(false)
    }
  }

  const brief = asBrief(run)
  const activeRisk = useMemo(() => {
    if (!brief) return "Run the incident-to-release check to inspect a real source-to-decision trace."
    return text(brief.recommended_next_action)
  }, [brief])

  return <div className="min-h-screen bg-[#f5f1e8] text-[#17212b]">
    <header className="border-b border-[#d9d3c8] bg-[#f5f1e8]/95 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5">
        <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight"><span className="grid h-8 w-8 place-items-center rounded-lg bg-[#17212b] text-[#fffdf8]"><Sparkles className="h-4 w-4" /></span>Company Brain</Link>
        <nav className="flex items-center gap-4 text-sm font-medium text-[#506070]"><Link to="/play/workflow" className="hover:text-[#17212b]">Workflow Lab</Link><Link to="/app/connect" className="hover:text-[#17212b]">Integration Studio</Link></nav>
      </div>
    </header>

    <main className="mx-auto max-w-7xl px-5 py-10 md:py-14">
      <section className="grid gap-8 lg:grid-cols-[1.25fr_0.75fr] lg:items-end">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Company Reality Layer</p>
          <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-[-0.05em] md:text-6xl">Before an agent acts, check what changed.</h1>
          <p className="mt-5 max-w-2xl text-base leading-7 text-[#5a6775]">Company Brain turns Slack, Drive, GitHub, and verified web evidence into auditable Qwen memory, then gives the workflow a deterministic safety decision.</p>
        </div>
        <section className="rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-5 shadow-[0_18px_55px_rgba(52,45,35,0.07)]">
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">Current decision posture</p>
          <p className="mt-2 text-lg font-semibold leading-7">{activeRisk}</p>
          <button type="button" onClick={() => void runIncident()} disabled={running} className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#17212b] px-4 py-3 text-sm font-semibold text-white hover:bg-[#293846] disabled:opacity-60">
            {running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}{running ? "Running live trace" : "Run incident-to-release check"}
          </button>
          <p className="mt-3 text-xs leading-5 text-[#6b7280]">Uses the real sandbox source pipeline and authenticated MCP. It cannot deploy or modify an external system.</p>
        </section>
      </section>

      {error && <div className="mt-7 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div>}

      <section className="mt-10" aria-label="Connected evidence sources">
        <div className="mb-4 flex items-end justify-between"><div><p className="text-xs font-bold uppercase tracking-[0.15em] text-[#718096]">Evidence surface</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">What Company Brain can observe</h2></div><Link className="inline-flex items-center gap-1 text-sm font-semibold text-[#2148c7]" to="/app/connect">Configure sources <ArrowRight className="h-4 w-4" /></Link></div>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {connections.map((connection) => {
            const Icon = sourceIcon(connection.provider)
            return <article key={connection.provider} className="rounded-2xl border border-[#ded7cb] bg-[#fffcf7] p-4"><div className="flex items-start justify-between gap-2"><span className="grid h-9 w-9 place-items-center rounded-xl bg-[#edf2fb] text-[#2f5eeb]"><Icon className="h-4 w-4" /></span><span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${statusTone(connection.status)}`}>{connection.status.replaceAll("_", " ")}</span></div><h3 className="mt-5 font-semibold">{connection.title}</h3><p className="mt-1 text-xs leading-5 text-[#637080]">{connection.allowed_scope.join(" · ")}</p>{connection.last_success_at && <p className="mt-3 text-[10px] text-[#718096]">Last verified: {new Date(connection.last_success_at).toLocaleString()}</p>}</article>
          })}
        </div>
      </section>

      <section className="mt-8 rounded-3xl border border-[#d7dde9] bg-[#fafbfe] p-5 shadow-[0_18px_55px_rgba(47,94,235,0.06)] md:p-7">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-[#2f5eeb]">Live trace</p><h2 className="mt-1 text-2xl font-semibold tracking-tight">Evidence to a human-owned decision</h2></div><p className="max-w-md text-sm leading-6 text-[#637080]">Each stage renders server output only. Qwen explains memory; deterministic SAG decides the action posture.</p></div>
        <div className="mt-6 grid gap-3 md:grid-cols-4">{steps.map((step, index) => <TraceCard key={step.id} step={step} index={index} />)}</div>

        {(events.length > 0 || brief) && <div className="mt-6 grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
          <article className="rounded-2xl border border-[#dbe3f2] bg-white p-5"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#617085]">Evidence received</p><div className="mt-3 space-y-3">{events.slice(0, 4).map((event) => <EvidenceRow key={event.ingestion_id} event={event} />)}</div></article>
          <article className="rounded-2xl border border-[#dbe3f2] bg-white p-5"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#617085]">Reality Memory</p><div className="mt-3 space-y-3">{memories.length === 0 ? <p className="text-sm text-[#6b7280]">Run the trace to inspect source-linked memory.</p> : memories.slice(0, 4).map((memory) => <MemoryRow key={memory.memory_id} memory={memory} />)}</div></article>
        </div>}

        {brief && <DecisionResult brief={brief} logs={logs} />}
        {(events.length > 0 || memories.length > 0 || brief) && <AuditProof events={events} memories={memories} brief={brief} />}
      </section>

      <section className="mt-10"><p className="text-xs font-bold uppercase tracking-[0.15em] text-[#718096]">Same engine, other consequences</p><div className="mt-4 grid gap-3 md:grid-cols-3"><CaseCard title="Release Safety" detail="Changed runtime evidence suspends a deployment." to="/play/release-safety" /><CaseCard title="Money Safety" detail="Contract evidence blocks an unsafe refund." to="/play/money-safety" /><CaseCard title="Rollout Safety" detail="Reliability evidence holds a feature expansion." to="/play/rollout-safety" /></div></section>
    </main>
  </div>
}

function TraceCard({ step, index }: { step: TraceStep; index: number }) {
  const styles = step.state === "complete" ? "border-emerald-200 bg-emerald-50" : step.state === "running" ? "border-blue-300 bg-blue-50" : step.state === "fallback" ? "border-amber-200 bg-amber-50" : step.state === "error" ? "border-rose-200 bg-rose-50" : "border-[#ded7cb] bg-[#fffcf7]"
  return <article className={`rounded-2xl border p-4 ${styles}`}><div className="flex items-center justify-between"><span className="text-[10px] font-bold tracking-[0.15em] text-[#718096]">0{index + 1}</span>{step.state === "running" ? <LoaderCircle className="h-4 w-4 animate-spin text-blue-700" /> : step.state === "complete" ? <Check className="h-4 w-4 text-emerald-700" /> : step.state === "fallback" ? <CircleAlert className="h-4 w-4 text-amber-700" /> : <Database className="h-4 w-4 text-[#94a3b8]" />}</div><h3 className="mt-5 font-semibold">{step.title}</h3><p className="mt-2 text-xs leading-5 text-[#637080]">{step.detail}</p></article>
}

function EvidenceRow({ event }: { event: SourceEvent }) {
  const observed = event.occurred_at ? new Date(event.occurred_at).toLocaleString() : "Not reported"
  const retrieved = event.retrieved_at ? new Date(event.retrieved_at).toLocaleString() : "Not reported"
  return <div className="rounded-xl border border-[#e3e8f1] bg-[#fbfcfe] p-3"><div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-sm">{event.source_name}</span><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(event.stage)}`}>{event.stage.replaceAll("_", " ")}</span></div><p className="mt-2 text-xs leading-5 text-[#536170]">{event.excerpt}</p><div className="mt-3 grid gap-1 text-[10px] leading-4 text-[#6f7d8e]"><p><span className="font-semibold">Observed:</span> {observed} | <span className="font-semibold">Retrieved:</span> {retrieved}</p><p><span className="font-semibold">Freshness:</span> {event.freshness ?? "not reported"} | <span className="font-semibold">Availability:</span> {event.availability ?? "not reported"}</p><p><span className="font-semibold">Scope:</span> {event.acl_scope?.join(" / ") || "not reported"}</p></div><p className="mt-2 font-mono text-[10px] text-[#8190a0]">hash {event.raw_payload_sha256.slice(0, 16)}... | Qwen {event.qwen_status}</p></div>
}

function MemoryRow({ memory }: { memory: RealityMemory }) {
  return <div className="rounded-xl border border-[#e3e8f1] bg-[#fbfcfe] p-3"><div className="flex flex-wrap items-center gap-2"><span className="font-semibold text-sm">{memory.subject}</span><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(memory.status)}`}>{memoryState(memory)}</span></div><p className="mt-2 text-xs leading-5 text-[#536170]">{memory.claim}</p><p className="mt-2 text-[10px] text-[#8190a0]">{memory.source_ingestion_ids.length} source link{memory.source_ingestion_ids.length === 1 ? "" : "s"} · {memory.scope}</p></div>
}

function readableValue(value: unknown) {
  if (typeof value === "string") return value
  if (Array.isArray(value)) return value.map((item) => typeof item === "string" ? item : JSON.stringify(item)).join(" ")
  if (value && typeof value === "object") return JSON.stringify(value)
  return "Not reported"
}

function DecisionResult({ brief, logs }: { brief: DecisionBrief; logs: McpLog[] }) {
  const verdict = text(brief.verdict).replaceAll("_", " ")
  const suspended = brief.verdict === "suspended"
  return <section className="mt-6 rounded-2xl border border-[#d9d3c8] bg-[#fffcf7] p-5"><div className="flex flex-wrap items-center gap-3"><span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide ${suspended ? "border-rose-200 bg-rose-50 text-rose-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>{verdict}</span><span className="text-xs font-medium text-[#667483]">Actual MCP DecisionBrief</span></div><h3 className="mt-4 text-2xl font-semibold tracking-tight">{text(brief.recommended_next_action)}</h3><div className="mt-5 grid gap-3 sm:grid-cols-2"><Fact label="Human owner" value={text(brief.owner)} /><Fact label="Safety check" value={text((brief.sag_trace as Record<string, unknown> | undefined)?.status).replaceAll("_", " ")} /></div><div className="mt-4 grid gap-3 md:grid-cols-3"><Fact label="What changed" value={readableValue(brief.what_changed)} /><Fact label="Qwen inference" value={readableValue(brief.inference)} /><Fact label="Missing evidence" value={readableValue(brief.missing_evidence)} /></div>{logs.length > 0 && <div className="mt-5 rounded-xl border border-[#e3e8f1] bg-[#f8fafc] p-3"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#667483]">MCP call log</p><div className="mt-2 space-y-2">{logs.map((log) => <p key={log.step} className="text-xs leading-5 text-[#536170]"><span className="font-mono text-[#2148c7]">{log.step}</span> — {log.detail}</p>)}</div></div>}</section>
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-[#e3e8f1] bg-white p-3"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#718096]">{label}</p><p className="mt-1 text-sm font-medium">{value}</p></div> }

function AuditProof({ events, memories, brief }: { events: SourceEvent[]; memories: RealityMemory[]; brief: DecisionBrief | null }) {
  return <details className="group mt-6 rounded-2xl border border-[#d9d3c8] bg-[#fffcf7]"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4 text-sm font-semibold">Audit proof <ChevronDown className="h-4 w-4 text-[#637080] transition group-open:rotate-180" /></summary><div className="grid gap-5 border-t border-[#e5ddd0] p-5 lg:grid-cols-3"><pre className="overflow-auto rounded-xl bg-[#17212b] p-3 text-[11px] leading-5 text-[#d9e2ec]">{JSON.stringify(events, null, 2)}</pre><pre className="overflow-auto rounded-xl bg-[#17212b] p-3 text-[11px] leading-5 text-[#d9e2ec]">{JSON.stringify(memories, null, 2)}</pre><pre className="overflow-auto rounded-xl bg-[#17212b] p-3 text-[11px] leading-5 text-[#d9e2ec]">{JSON.stringify(brief?.sag_trace ?? {}, null, 2)}</pre></div></details>
}

function CaseCard({ title, detail, to }: { title: string; detail: string; to: string }) { return <Link to={to} className="group rounded-2xl border border-[#ded7cb] bg-[#fffcf7] p-5 shadow-[0_12px_32px_rgba(52,45,35,0.04)] transition hover:-translate-y-0.5 hover:border-[#a6b5d5]"><h3 className="font-semibold">{title}</h3><p className="mt-2 text-sm leading-6 text-[#637080]">{detail}</p><span className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-[#2148c7]">Explore <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" /></span></Link> }
