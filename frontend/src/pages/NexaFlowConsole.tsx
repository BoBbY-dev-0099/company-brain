import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  FileText,
  Github,
  Loader2,
  MessageSquareText,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from "lucide-react"
import { Link } from "react-router-dom"
import {
  getNexaFlowOverview,
  runNexaFlowCaseMatrix,
  runNexaFlowReleaseCheck,
  type DecisionRun,
  type NexaFlowCaseMatrix,
  type NexaFlowDecision,
  type NexaFlowOverview,
  type QwenCaseResult,
  type RealityMemory,
  type SourceConnection,
  type SourceEvidence,
} from "../lib/api"

function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } } }
  return value.response?.data?.detail || "The console could not reach the local API. Start Docker and refresh."
}

function providerIcon(provider: string) {
  if (provider === "slack") return MessageSquareText
  if (provider === "alibaba_oss") return FileText
  return Github
}

function providerLabel(provider: string) {
  if (provider === "slack") return "Slack incident"
  if (provider === "alibaba_oss") return "Alibaba OSS runbook"
  return "GitHub merged PR"
}

function providerRole(provider: string) {
  if (provider === "slack") return "Current operational reality"
  if (provider === "alibaba_oss") return "Approved safety policy"
  return "Effective release configuration"
}

function time(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "Waiting for first record"
}

function statusTone(status: string) {
  if (status === "connected" || status === "healthy" || status === "decision_ready" || status === "active" || status === "compiled") {
    return "bg-emerald-50 text-emerald-800 border-emerald-200"
  }
  if (status === "suspended") return "bg-rose-50 text-rose-800 border-rose-200"
  if (status === "review_required" || status === "setup_required" || status === "unavailable" || status === "stale") {
    return "bg-amber-50 text-amber-900 border-amber-200"
  }
  return "bg-slate-50 text-slate-700 border-slate-200"
}

function titleStatus(status: string) {
  return status.replaceAll("_", " ")
}

function cleanText(value: string, limit = 360) {
  const cleaned = value
    .replace(/#{1,6}\s*/g, "")
    .replace(/```[\s\S]*?```/g, "")
    .replace(/\s+/g, " ")
    .trim()
  return cleaned.length > limit ? `${cleaned.slice(0, limit).trimEnd()}…` : cleaned
}

function evidenceHeadline(item: SourceEvidence) {
  const excerpt = cleanText(item.excerpt, 240)
  if (item.provider === "alibaba_oss") {
    const requirement = item.excerpt.match(/(?:at least|minimum(?: of)?|no less than)\s+(\d+)\s*(?:MiB|MB)/i)
    return requirement ? `Workers require at least ${requirement[1]} MiB before promotion.` : excerpt
  }
  if (item.provider === "github") {
    const value = item.excerpt.match(/NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB\s*=\s*(\d+)/i)
    return value ? `Merged PR sets the worker memory to ${value[1]} MiB.` : excerpt
  }
  return excerpt
}

function qwenStatus(status: string) {
  if (status === "compiled" || status === "compiled_ephemeral") return "compiled"
  if (status === "failed" || status === "unavailable") return "unavailable"
  return status || "pending"
}

function verdictLabel(verdict: string) {
  if (verdict === "proceed_with_human_approval") return "Proceed · human approval"
  return titleStatus(verdict)
}

function plainRule(verdict: string) {
  if (verdict === "suspended") return "At least one live safety condition failed, so promotion is stopped."
  if (verdict === "review_required") return "The system cannot safely evaluate the rule until the required evidence is fresh and complete."
  return "The current evidence satisfies the rule, but a human owner must still approve the action."
}

export default function NexaFlowConsole() {
  const [overview, setOverview] = useState<NexaFlowOverview | null>(null)
  const [decision, setDecision] = useState<NexaFlowDecision | null>(null)
  const [matrix, setMatrix] = useState<NexaFlowCaseMatrix | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [matrixRunning, setMatrixRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [matrixError, setMatrixError] = useState<string | null>(null)
  const decisionPanelRef = useRef<HTMLDivElement | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setOverview(await getNexaFlowOverview())
      setError(null)
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])

  const activeRun = decision?.run ?? (overview?.release_check_ready ? overview.latest_release_check : null)
  const evidence = overview?.evidence ?? []
  const memories = overview?.memories ?? []
  const configuredSources = (overview?.connections ?? []).filter((item) => item.provider !== "web" && item.status === "connected").length
  const receivedSources = new Set(evidence.map((item) => item.provider)).size

  async function runCheck() {
    setRunning(true)
    try {
      const response = await runNexaFlowReleaseCheck()
      setDecision(response)
      setOverview(await getNexaFlowOverview())
      setError(null)
      requestAnimationFrame(() => decisionPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }))
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setRunning(false)
    }
  }

  async function runMatrix() {
    setMatrixRunning(true)
    setMatrixError(null)
    try {
      setMatrix(await runNexaFlowCaseMatrix())
    } catch (reason) {
      setMatrixError(errorText(reason))
    } finally {
      setMatrixRunning(false)
    }
  }

  return <div className="min-h-screen bg-[#f6f4ef] text-[#17212b]">
    <header className="border-b border-[#ddd8ce] bg-[#f6f4ef]/95"><div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5"><Link to="/" className="flex items-center gap-2 font-semibold tracking-[-0.02em]"><span className="grid h-8 w-8 place-items-center rounded-lg bg-[#16386e] text-sm font-bold text-white">N</span>NexaFlow</Link><div className="flex items-center gap-4"><span className="hidden text-xs text-[#697585] sm:block">Reality memory console</span><Link to="/setup" className="text-sm font-semibold text-[#174ea6]">Setup sources</Link><button type="button" onClick={() => void refresh()} className="inline-flex items-center gap-2 rounded-lg border border-[#ccd4df] bg-white px-3 py-2 text-sm font-semibold text-[#34455c]"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />Refresh</button></div></div></header>
    <main className="mx-auto max-w-6xl px-5 py-10">
      <section className="grid gap-8 lg:grid-cols-[1.15fr_.85fr]"><div><p className="text-xs font-bold uppercase tracking-[.18em] text-[#2364d2]">Live operations console</p><h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-[-.055em] text-[#142234] sm:text-5xl">Stop a release when company reality changes.</h1><p className="mt-4 max-w-2xl text-base leading-7 text-[#5c6a7b]">Qwen turns the latest Slack, Alibaba OSS, and GitHub evidence into a source-linked memory. SAG then checks the live release conditions before anyone acts.</p></div><div className="rounded-2xl border border-[#d5dbe3] bg-[#eef5ff] p-5"><p className="text-xs font-bold uppercase tracking-[.14em] text-[#3265ad]">One governed decision</p><p className="mt-2 text-lg font-semibold">Fulfillment release safety</p><p className="mt-2 text-sm leading-6 text-[#52647c]">The server selects the newest ready evidence. The browser supplies no organization, evidence, or verdict.</p><div className="mt-5 flex flex-wrap gap-2"><button type="button" disabled={running} onClick={() => void runCheck()} className="inline-flex items-center gap-2 rounded-xl bg-[#16386e] px-4 py-3 text-sm font-semibold text-white shadow-sm disabled:opacity-60">{running ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldAlert className="h-4 w-4" />}{running ? "Checking real evidence..." : "Run release safety check"}</button><button type="button" disabled={matrixRunning} onClick={() => void runMatrix()} className="inline-flex items-center gap-2 rounded-xl border border-[#b9cbe6] bg-white px-4 py-3 text-sm font-semibold text-[#23466f] disabled:opacity-60">{matrixRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}{matrixRunning ? "Running 5 Qwen cases..." : "Run Qwen case proof"}</button></div>{decision && <div aria-live="polite" className="mt-4 rounded-xl border border-[#b9cbe6] bg-white/75 px-3 py-2 text-sm"><span className="font-semibold">Decision returned:</span> {verdictLabel(decision.run.decision_brief.verdict)}</div>}</div></section>

      {error && <div className="mt-7 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}</div>}
      {activeRun && <div ref={decisionPanelRef}><DecisionPanel run={activeRun} parsing={decision?.parsing} boundary={decision?.boundary} /></div>}
      <section className="mt-9"><div className="mb-3 flex items-end justify-between"><div><p className="text-xs font-bold uppercase tracking-[.14em] text-[#718096]">Source connections</p><h2 className="mt-1 text-xl font-semibold">Three inputs · one decision</h2></div><span className="text-xs text-[#718096]">{configuredSources}/3 connected · backend-derived</span></div><div className="grid gap-3 md:grid-cols-3">{(overview?.connections ?? []).filter((item) => item.provider !== "web").map((item) => <ConnectionCard key={item.provider} connection={item} />)}</div></section>

      <section className="mt-4 rounded-2xl border border-[#ddd8ce] bg-[#fffdfa] p-5"><p className="text-xs font-bold uppercase tracking-[.14em] text-[#718096]">Evidence → memory → decision</p><div className="mt-4 grid gap-3 md:grid-cols-3"><FlowStep number="1" title="Receive" detail={`${receivedSources}/3 source records`} state={receivedSources === 3 ? "done" : "active"} /><FlowStep number="2" title="Qwen compiles" detail={memories.length ? `${memories.length} source-linked memories` : "Waiting for source evidence"} state={memories.length ? "done" : "waiting"} /><FlowStep number="3" title="SAG checks" detail={activeRun ? verdictLabel(activeRun.decision_brief.verdict) : "Waiting for release check"} state={activeRun ? (activeRun.decision_brief.verdict === "suspended" ? "risk" : "done") : "waiting"} /></div></section>

      {!loading && overview && !overview.release_check_ready && <section className="mt-6 rounded-2xl border border-amber-200 bg-[#fffaf0] p-5"><div className="flex gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" /><div><p className="font-semibold text-amber-950">Release check is waiting for real evidence</p><ul className="mt-2 space-y-1 text-sm leading-6 text-amber-900">{overview.readiness_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul><Link to="/setup" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[#174ea6]">Configure the NexaFlow test company <ArrowRight className="h-4 w-4" /></Link></div></div></section>}

      {(matrix || matrixError) && <CaseMatrix matrix={matrix} error={matrixError} />}
      <section className="mt-10 grid gap-6 lg:grid-cols-[1fr_.9fr]"><EvidenceTimeline evidence={evidence} /><MemoryLineage memories={memories} /></section>
      {activeRun && <AuditProof run={activeRun} decision={decision} evidence={evidence} memories={memories} />}
    </main>
  </div>
}

function ConnectionCard({ connection }: { connection: SourceConnection }) {
  const Icon = providerIcon(connection.provider)
  return <article className="rounded-2xl border border-[#ddd8ce] bg-[#fffdfa] p-5"><div className="flex items-start justify-between gap-2"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef3fb] text-[#265ba9]"><Icon className="h-5 w-5" /></span><span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${statusTone(connection.status)}`}>{titleStatus(connection.status)}</span></div><h3 className="mt-5 font-semibold">{connection.title}</h3><p className="mt-2 min-h-10 text-xs leading-5 text-[#647284]">{connection.allowed_scope.join(" · ")}</p><p className="mt-4 border-t border-[#ece7dd] pt-3 text-xs text-[#6d7988]">Last evidence: {time(connection.last_success_at)}</p></article>
}

function FlowStep({ number, title, detail, state }: { number: string; title: string; detail: string; state: "done" | "active" | "waiting" | "risk" }) {
  const tone = state === "done" ? "border-emerald-200 bg-[#f4fbf6]" : state === "risk" ? "border-rose-200 bg-[#fff8f7]" : state === "active" ? "border-[#a9c2e4] bg-[#f0f6ff]" : "border-[#e4dfd6] bg-[#faf8f3]"
  const dot = state === "done" ? "bg-emerald-700 text-white" : state === "risk" ? "bg-rose-700 text-white" : state === "active" ? "bg-[#16386e] text-white" : "bg-[#e2e6eb] text-[#697585]"
  return <div className={`rounded-xl border p-3 ${tone}`}><div className="flex items-center gap-3"><span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-bold ${dot}`}>{state === "done" ? <CheckCircle2 className="h-4 w-4" /> : number}</span><div><p className="text-sm font-semibold">{title}</p><p className="text-xs text-[#697585]">{detail}</p></div></div></div>
}

function DecisionPanel({ run, parsing, boundary }: { run: DecisionRun; parsing?: Record<string, unknown>; boundary?: string }) {
  const brief = run.decision_brief
  const suspended = brief.verdict === "suspended"
  const review = brief.verdict === "review_required"
  const Icon = suspended || review ? ShieldAlert : CheckCircle2
  const facts = brief.facts ?? []
  return <section className={`mt-9 rounded-2xl border p-6 ${suspended ? "border-rose-200 bg-[#fff8f7]" : review ? "border-amber-200 bg-[#fffaf0]" : "border-emerald-200 bg-[#f4fbf6]"}`}><div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between"><div className="flex max-w-3xl gap-4"><span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${suspended ? "bg-rose-100 text-rose-800" : review ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}><Icon className="h-5 w-5" /></span><div><div className="flex flex-wrap items-center gap-2"><p className="text-xs font-bold uppercase tracking-[.14em]">Backend decision</p><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(brief.verdict)}`}>{verdictLabel(brief.verdict)}</span></div><h2 className="mt-3 text-2xl font-semibold tracking-[-.035em]">{brief.recommended_next_action}</h2></div></div><div className="min-w-48 rounded-xl border border-black/10 bg-white/65 p-4 text-sm"><p className="text-[10px] font-bold uppercase tracking-[.13em] text-[#687789]">Human owner</p><p className="mt-1 font-semibold">{brief.owner}</p><p className="mt-3 text-[10px] font-bold uppercase tracking-[.13em] text-[#687789]">Execution</p><p className="mt-1 font-semibold">Human confirmation required</p></div></div>
    <div className="mt-5 grid gap-4 lg:grid-cols-[1.25fr_.75fr]"><div className="rounded-xl border border-[#b9cbe6] bg-[#eef5ff] p-4"><div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[.13em] text-[#3265ad]"><Sparkles className="h-4 w-4" />Qwen interpretation</div><p className="mt-2 text-sm leading-6 text-[#304b70]">{brief.inference.text}</p><p className="mt-3 text-xs font-semibold text-[#5f7594]">{brief.inference.is_model_generated ? `Compiled by ${brief.inference.generated_by}` : "Deterministic fallback · Qwen response unavailable"}</p></div><div className="rounded-xl border border-black/10 bg-white/55 p-4"><p className="text-[10px] font-bold uppercase tracking-[.13em] text-[#687789]">Why this verdict?</p><p className="mt-2 text-sm leading-6 text-[#4f5e70]">{plainRule(brief.verdict)}</p><p className="mt-3 text-xs font-semibold text-[#687789]">SAG status: {String(brief.sag_trace.status ?? "not evaluated")}</p></div></div>
    {facts.length > 0 && <div className="mt-5 grid gap-3 border-t border-black/10 pt-5 md:grid-cols-3">{facts.slice(0, 3).map((fact, index) => <div key={`${fact.statement}-${index}`} className="rounded-xl border border-black/10 bg-white/55 p-3"><p className="text-[10px] font-bold uppercase tracking-[.13em] text-[#687789]">Observed fact</p><p className="mt-1 text-sm leading-5">{fact.statement}</p></div>)}</div>}
    {parsing && <div className="mt-5 grid gap-3 border-t border-black/10 pt-5 sm:grid-cols-3"><Fact label="Runbook minimum" value={parsing.runbook_minimum_memory_mb ? `${parsing.runbook_minimum_memory_mb} MiB` : "Not parsed"} /><Fact label="Merged configuration" value={parsing.merged_worker_memory_mb ? `${parsing.merged_worker_memory_mb} MiB` : "Not parsed"} /><Fact label="Slack incident" value={parsing.linked_incident_open === true ? "Open" : parsing.linked_incident_open === false ? "Closed" : "Not identified"} /></div>}
    {boundary && <p className="mt-5 text-xs leading-5 text-[#647284]">{boundary}</p>}
  </section>
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-black/10 bg-white/55 p-3"><p className="text-[10px] font-bold uppercase tracking-[.13em] text-[#687789]">{label}</p><p className="mt-1 font-semibold">{value}</p></div> }

function EvidenceTimeline({ evidence }: { evidence: SourceEvidence[] }) {
  const shown = evidence.filter((item) => ["slack", "alibaba_oss", "github"].includes(item.provider))
  return <section className="rounded-2xl border border-[#ddd8ce] bg-[#fffdfa] p-6"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-[.14em] text-[#718096]">Persisted evidence</p><h2 className="mt-1 text-xl font-semibold">What the company systems sent</h2></div><span className="rounded-full bg-[#eef5ff] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-[#3265ad]">Source ledger</span></div>{shown.length === 0 ? <Empty icon={<Activity className="h-5 w-5" />} text="No real source records yet. Configure Slack, Alibaba OSS, and GitHub, then refresh." /> : <div className="mt-5 space-y-3">{shown.map((item) => <EvidenceCard key={item.ingestion_id} item={item} />)}</div>}</section>
}

function EvidenceCard({ item }: { item: SourceEvidence }) {
  const Icon = providerIcon(item.provider)
  const qwen = qwenStatus(item.qwen_status)
  return <article className="rounded-xl border border-[#e4dfd6] bg-[#faf8f3] p-4"><div className="flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-white text-[#265ba9]"><Icon className="h-4 w-4" /></span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-semibold">{providerLabel(item.provider)}</p><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(item.stage)}`}>{titleStatus(item.stage)}</span><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(qwen)}`}>Qwen {qwen}</span></div><p className="mt-1 text-xs text-[#788494]">{providerRole(item.provider)} · {item.freshness} · {time(item.retrieved_at)}</p></div></div><div className="mt-4 rounded-lg border border-[#e5e0d7] bg-white/70 p-3"><p className="text-[10px] font-bold uppercase tracking-[.13em] text-[#718096]">What arrived</p><p className="mt-1 text-sm leading-6 text-[#394b61]">{evidenceHeadline(item)}</p></div><details className="mt-3"><summary className="cursor-pointer text-xs font-semibold text-[#3265ad]">View source excerpt and provenance</summary><p className="mt-2 text-xs leading-5 text-[#687789]">{cleanText(item.excerpt, 1400)}</p><p className="mt-2 text-[10px] text-[#8893a1]">Source ID {item.ingestion_id} · SHA {item.raw_payload_sha256.slice(0, 12)}…</p></details></article>
}

function MemoryLineage({ memories }: { memories: RealityMemory[] }) {
  const active = useMemo(() => memories.slice(0, 6), [memories])
  return <section className="rounded-2xl border border-[#ddd8ce] bg-[#fffdfa] p-6"><div className="flex items-start justify-between gap-4"><div><p className="text-xs font-bold uppercase tracking-[.14em] text-[#718096]">Reality memory</p><h2 className="mt-1 text-xl font-semibold">What Qwen carried forward</h2></div><span className="rounded-full bg-[#f3edff] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-[#6b4bb5]">Qwen + provenance</span></div>{active.length === 0 ? <Empty icon={<Sparkles className="h-5 w-5" />} text="Memory appears after a source record is processed. If Qwen is unavailable, the console will say so." /> : <div className="mt-5 space-y-3">{active.map((memory) => <MemoryCard key={memory.memory_id} memory={memory} />)}</div>}</section>
}

function MemoryCard({ memory }: { memory: RealityMemory }) {
  const qwen = memory.qwen_generated ? "compiled" : "unavailable"
  return <article className="rounded-xl border border-[#e4dfd6] bg-[#faf8f3] p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold text-[#516174]">{cleanText(memory.subject, 90)}</p><p className="mt-1 text-[10px] font-bold uppercase tracking-[.13em] text-[#8a95a3]">Qwen operational claim</p></div><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(memory.status)}`}>{titleStatus(memory.status)}</span></div><p className="mt-3 text-sm leading-6 text-[#394b61]">{cleanText(memory.claim, 300)}</p><div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] text-[#788494]"><span className={`rounded-full border px-2 py-0.5 font-bold uppercase ${statusTone(qwen)}`}>Qwen {qwen}</span><span>{memory.source_ingestion_ids.length} linked source{memory.source_ingestion_ids.length === 1 ? "" : "s"}</span><span>updated {time(memory.updated_at)}</span></div><details className="mt-3"><summary className="cursor-pointer text-xs font-semibold text-[#3265ad]">How this memory is grounded</summary><p className="mt-2 text-xs leading-5 text-[#687789]">{cleanText(memory.qwen_rationale || memory.claim, 900)}</p><p className="mt-2 text-[10px] text-[#8893a1]">Memory ID {memory.memory_id} · source IDs {memory.source_ingestion_ids.join(", ") || "none"}</p></details></article>
}

function CaseMatrix({ matrix, error }: { matrix: NexaFlowCaseMatrix | null; error: string | null }) {
  return <section className="mt-8 rounded-2xl border border-[#cfdcf0] bg-[#f7faff] p-6"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><p className="text-xs font-bold uppercase tracking-[.14em] text-[#3265ad]">Qwen verification</p><h2 className="mt-1 text-xl font-semibold">Five realities · one governed engine</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-[#5b6d84]">Each case is compiled through Qwen, then evaluated by the same deterministic SAG rule. These runs are ephemeral and never change the live company memory.</p></div>{matrix && <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase ${statusTone(matrix.qwen_configured ? "compiled" : "unavailable")}`}>{matrix.qwen_configured ? "Qwen configured" : "Qwen unavailable"}</span>}</div>{error && <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">{error}</div>}{matrix && <div className="mt-5 grid gap-3 md:grid-cols-2 lg:grid-cols-3">{matrix.cases.map((item) => <CaseCard key={item.case_id} item={item} />)}</div>}{matrix && <p className="mt-5 text-xs leading-5 text-[#687789]">{matrix.boundary}</p>}</section>
}

function CaseCard({ item }: { item: QwenCaseResult }) {
  return <article className="rounded-xl border border-[#d9e3f1] bg-white p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold">{item.title}</p><p className="mt-1 text-xs leading-5 text-[#687789]">{item.description}</p></div><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(item.verdict)}`}>{verdictLabel(item.verdict)}</span></div><div className="mt-3 rounded-lg bg-[#f3edff] p-3"><div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-[.12em] text-[#6b4bb5]"><Sparkles className="h-3.5 w-3.5" />Qwen {item.qwen.status}</div><p className="mt-1 text-xs leading-5 text-[#51436f]">{cleanText(item.qwen.summary, 180)}</p>{item.qwen.model && <p className="mt-2 text-[10px] text-[#806db1]">Model: {item.qwen.model} · {item.qwen.source_count} source records</p>}</div><p className="mt-3 text-xs leading-5 text-[#58697e]"><span className="font-semibold">SAG:</span> {plainRule(item.verdict)}</p></article>
}

function Empty({ icon, text }: { icon: ReactNode; text: string }) { return <div className="mt-5 flex gap-3 rounded-xl bg-[#f6f7f8] p-4 text-sm leading-6 text-[#657384]"><span className="mt-0.5 text-[#7891b6]">{icon}</span>{text}</div> }

function AuditProof({ run, decision, evidence, memories }: { run: DecisionRun; decision: NexaFlowDecision | null; evidence: SourceEvidence[]; memories: RealityMemory[] }) {
  return <details className="mt-8 rounded-2xl border border-[#d8d3ca] bg-[#fbfaf7] p-5"><summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold"><span>Audit proof</span><ChevronDown className="h-4 w-4" /></summary><p className="mt-3 text-sm leading-6 text-[#5d6b7b]">The readable cards above are backed by this server response. Open the raw trace only when you need source IDs, provenance, or the exact SAG evaluation.</p><div className="mt-5 grid gap-4 lg:grid-cols-2"><Proof title="Deterministic SAG rule" value={run.decision_brief.sag_trace} /><Proof title="Decision evidence" value={run.decision_brief.evidence} /><Proof title="Memory provenance" value={run.decision_brief.memory_refs} /><Proof title="Source selection and parsing" value={{ source_selection: decision?.source_selection, parsing: decision?.parsing, source_records: evidence, memories }} /></div></details>
}

function Proof({ title, value }: { title: string; value: unknown }) { return <div><p className="mb-2 text-xs font-bold uppercase tracking-[.13em] text-[#718096]">{title}</p><pre className="max-h-80 overflow-auto rounded-xl border border-[#e0dbd2] bg-[#17212b] p-4 text-xs leading-5 text-[#dce7f6]">{JSON.stringify(value, null, 2)}</pre></div> }
