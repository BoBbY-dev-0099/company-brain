import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { Activity, AlertTriangle, ArrowRight, CheckCircle2, ChevronDown, FileText, Github, Loader2, MessageSquareText, RefreshCw, ShieldAlert, Sparkles } from "lucide-react"
import { Link } from "react-router-dom"
import { getNexaFlowOverview, runNexaFlowReleaseCheck, type DecisionRun, type NexaFlowDecision, type NexaFlowOverview, type RealityMemory, type SourceConnection, type SourceEvidence } from "../lib/api"

function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } } }
  return value.response?.data?.detail || "The console could not reach the local API. Start Docker and refresh."
}

function providerIcon(provider: string) {
  if (provider === "slack") return MessageSquareText
  if (provider === "alibaba_oss") return FileText
  return Github
}

function time(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "Waiting for first record"
}

function statusTone(status: string) {
  if (status === "connected" || status === "healthy" || status === "decision_ready") return "bg-emerald-50 text-emerald-800 border-emerald-200"
  if (status === "suspended") return "bg-rose-50 text-rose-800 border-rose-200"
  if (status === "review_required" || status === "setup_required") return "bg-amber-50 text-amber-900 border-amber-200"
  return "bg-slate-50 text-slate-700 border-slate-200"
}

function titleStatus(status: string) {
  return status.replaceAll("_", " ")
}

export default function NexaFlowConsole() {
  const [overview, setOverview] = useState<NexaFlowOverview | null>(null)
  const [decision, setDecision] = useState<NexaFlowDecision | null>(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
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

  // Do not surface an old empty/review run as if it were the current decision.
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
      // The decision is the judge's primary result. Bring it into view after
      // the backend responds instead of leaving the new panel below the fold.
      requestAnimationFrame(() => decisionPanelRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }))
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setRunning(false)
    }
  }

  return <div className="min-h-screen bg-[#f6f4ef] text-[#17212b]">
    <header className="border-b border-[#ddd8ce] bg-[#f6f4ef]/95"><div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5"><Link to="/" className="flex items-center gap-2 font-semibold tracking-[-0.02em]"><span className="grid h-8 w-8 place-items-center rounded-lg bg-[#16386e] text-sm font-bold text-white">N</span>NexaFlow</Link><div className="flex items-center gap-4"><span className="hidden text-xs text-[#697585] sm:block">Local real-integration rehearsal</span><Link to="/setup" className="text-sm font-semibold text-[#174ea6]">Setup sources</Link><button type="button" onClick={() => void refresh()} className="inline-flex items-center gap-2 rounded-lg border border-[#ccd4df] bg-white px-3 py-2 text-sm font-semibold text-[#34455c]"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />Refresh</button></div></div></header>
    <main className="mx-auto max-w-6xl px-5 py-10">
      <section className="grid gap-8 lg:grid-cols-[1.2fr_.8fr]"><div><p className="text-xs font-bold uppercase tracking-[.18em] text-[#2364d2]">Live operations console</p><h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-[-.055em] text-[#142234] sm:text-5xl">Stop a release when company reality changes.</h1><p className="mt-4 max-w-2xl text-base leading-7 text-[#5c6a7b]">NexaFlow turns real Slack, Alibaba OSS, and GitHub evidence into governed memory before an agent or release workflow acts.</p></div><div className="rounded-2xl border border-[#d5dbe3] bg-[#eef5ff] p-5"><p className="text-xs font-bold uppercase tracking-[.14em] text-[#3265ad]">One decision</p><p className="mt-2 text-lg font-semibold">Fulfillment release safety</p><p className="mt-2 text-sm leading-6 text-[#52647c]">The server selects the newest ready evidence. The browser supplies no organization, evidence, or verdict.</p><button type="button" disabled={running} onClick={() => void runCheck()} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#16386e] px-4 py-3 text-sm font-semibold text-white shadow-sm disabled:opacity-60">{running ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldAlert className="h-4 w-4" />}{running ? "Checking real evidence..." : "Run release safety check"}</button>{decision && <div aria-live="polite" className="mt-4 rounded-xl border border-[#b9cbe6] bg-white/75 px-3 py-2 text-sm"><span className="font-semibold">Decision returned:</span> {titleStatus(decision.run.decision_brief.verdict)}</div>}</div></section>

      {error && <div className="mt-7 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}</div>}
      {activeRun && <div ref={decisionPanelRef}><DecisionPanel run={activeRun} parsing={decision?.parsing} boundary={decision?.boundary} /></div>}
      <section className="mt-9"><div className="mb-3 flex items-end justify-between"><div><p className="text-xs font-bold uppercase tracking-[.14em] text-[#718096]">Source connections</p><h2 className="mt-1 text-xl font-semibold">Read-only company evidence</h2></div><span className="text-xs text-[#718096]">Backend-derived status</span></div><div className="grid gap-3 md:grid-cols-3">{(overview?.connections ?? []).filter((item) => item.provider !== "web").map((item) => <ConnectionCard key={item.provider} connection={item} />)}</div></section>

      <section className="mt-4 rounded-2xl border border-[#ddd8ce] bg-[#fffdfa] p-5"><p className="text-xs font-bold uppercase tracking-[.14em] text-[#718096]">The live path</p><div className="mt-4 grid gap-3 md:grid-cols-3"><FlowStep number="1" title="Connect sources" detail={`${configuredSources}/3 configured`} state={configuredSources === 3 ? "done" : "active"} /><FlowStep number="2" title="Build reality memory" detail={`${receivedSources}/3 source events received`} state={receivedSources === 3 ? "done" : configuredSources === 3 ? "active" : "waiting"} /><FlowStep number="3" title="Check the release" detail={activeRun ? titleStatus(activeRun.decision_brief.verdict) : "Waiting for real evidence"} state={activeRun ? (activeRun.decision_brief.verdict === "suspended" ? "risk" : "done") : "waiting"} /></div></section>

      {!loading && overview && !overview.release_check_ready && <section className="mt-6 rounded-2xl border border-amber-200 bg-[#fffaf0] p-5"><div className="flex gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" /><div><p className="font-semibold text-amber-950">Release check is waiting for real evidence</p><ul className="mt-2 space-y-1 text-sm leading-6 text-amber-900">{overview.readiness_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul><Link to="/setup" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[#174ea6]">Configure the NexaFlow test company <ArrowRight className="h-4 w-4" /></Link></div></div></section>}

      <section className="mt-10 grid gap-6 lg:grid-cols-[1fr_.9fr]"><EvidenceTimeline evidence={evidence} /><MemoryLineage memories={memories} /></section>
      {activeRun && <AuditProof run={activeRun} decision={decision} evidence={evidence} memories={memories} />}
    </main>
  </div>
}

function ConnectionCard({ connection }: { connection: SourceConnection }) {
  const Icon = providerIcon(connection.provider)
  return <article className="rounded-2xl border border-[#ddd8ce] bg-[#fffdfa] p-5"><div className="flex items-start justify-between gap-2"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#eef3fb] text-[#265ba9]"><Icon className="h-5 w-5" /></span><span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${statusTone(connection.status)}`}>{titleStatus(connection.status)}</span></div><h3 className="mt-5 font-semibold">{connection.title}</h3><p className="mt-2 min-h-10 text-xs leading-5 text-[#647284]">{connection.allowed_scope.join(" | ")}</p><p className="mt-4 border-t border-[#ece7dd] pt-3 text-xs text-[#6d7988]">Last evidence: {time(connection.last_success_at)}</p></article>
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
  return <section className={`mt-9 rounded-2xl border p-6 ${suspended ? "border-rose-200 bg-[#fff8f7]" : review ? "border-amber-200 bg-[#fffaf0]" : "border-emerald-200 bg-[#f4fbf6]"}`}><div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between"><div className="flex max-w-3xl gap-4"><span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${suspended ? "bg-rose-100 text-rose-800" : review ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}><Icon className="h-5 w-5" /></span><div><p className="text-xs font-bold uppercase tracking-[.14em]">Backend decision | {titleStatus(brief.verdict)}</p><h2 className="mt-2 text-2xl font-semibold tracking-[-.035em]">{brief.recommended_next_action}</h2><p className="mt-3 text-sm leading-6 text-[#536170]">{brief.inference.text}</p></div></div><div className="min-w-48 rounded-xl border border-black/10 bg-white/65 p-4 text-sm"><p className="text-[10px] font-bold uppercase tracking-[.13em] text-[#687789]">Human owner</p><p className="mt-1 font-semibold">{brief.owner}</p><p className="mt-3 text-[10px] font-bold uppercase tracking-[.13em] text-[#687789]">Execution</p><p className="mt-1 font-semibold">Human confirmation required</p></div></div>{parsing && <div className="mt-5 grid gap-3 border-t border-black/10 pt-5 sm:grid-cols-3"><Fact label="Runbook minimum" value={parsing.runbook_minimum_memory_mb ? `${parsing.runbook_minimum_memory_mb} MiB` : "Not parsed"} /><Fact label="Merged configuration" value={parsing.merged_worker_memory_mb ? `${parsing.merged_worker_memory_mb} MiB` : "Not parsed"} /><Fact label="Slack incident" value={parsing.linked_incident_open === true ? "Open" : parsing.linked_incident_open === false ? "Closed" : "Not identified"} /></div>}{boundary && <p className="mt-5 text-xs leading-5 text-[#647284]">{boundary}</p>}</section>
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-black/10 bg-white/55 p-3"><p className="text-[10px] font-bold uppercase tracking-[.13em] text-[#687789]">{label}</p><p className="mt-1 font-semibold">{value}</p></div> }

function EvidenceTimeline({ evidence }: { evidence: SourceEvidence[] }) {
  const shown = evidence.filter((item) => ["slack", "alibaba_oss", "github"].includes(item.provider))
  return <section className="rounded-2xl border border-[#ddd8ce] bg-[#fffdfa] p-6"><p className="text-xs font-bold uppercase tracking-[.14em] text-[#718096]">Persisted evidence</p><h2 className="mt-1 text-xl font-semibold">What NexaFlow received</h2>{shown.length === 0 ? <Empty icon={<Activity className="h-5 w-5" />} text="No real source records yet. Configure Slack, Alibaba OSS, and GitHub, then refresh." /> : <ol className="mt-5 space-y-4">{shown.map((item) => <li key={item.ingestion_id} className="border-l-2 border-[#ccd9ee] pl-4"><div className="flex flex-wrap items-center gap-2"><span className="font-semibold capitalize">{item.provider.replaceAll("_", " ")}</span><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(item.stage)}`}>{titleStatus(item.stage)}</span></div><p className="mt-1 text-sm leading-6 text-[#4f5e70]">{item.excerpt}</p><p className="mt-2 text-xs text-[#788494]">Received {time(item.retrieved_at)} | freshness {item.freshness} | Qwen {item.qwen_status}</p></li>)}</ol>}</section>
}

function MemoryLineage({ memories }: { memories: NexaFlowOverview["memories"] }) {
  const active = useMemo(() => memories.slice(0, 6), [memories])
  return <section className="rounded-2xl border border-[#ddd8ce] bg-[#fffdfa] p-6"><p className="text-xs font-bold uppercase tracking-[.14em] text-[#718096]">Reality memory</p><h2 className="mt-1 text-xl font-semibold">What Qwen compiled with provenance</h2>{active.length === 0 ? <Empty icon={<Sparkles className="h-5 w-5" />} text="Memory appears only after a source record is processed. The console will show an honest unavailable status if Qwen is not configured." /> : <div className="mt-5 space-y-3">{active.map((memory) => <article key={memory.memory_id} className="rounded-xl border border-[#e4dfd6] bg-[#faf8f3] p-4"><div className="flex items-center justify-between gap-3"><p className="text-xs font-semibold">{memory.subject}</p><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(memory.status)}`}>{titleStatus(memory.status)}</span></div><p className="mt-2 text-sm leading-6 text-[#536170]">{memory.claim}</p><p className="mt-2 text-xs text-[#788494]">{memory.qwen_generated ? "Qwen-compiled" : "Qwen unavailable"} | {memory.source_ingestion_ids.length} source record(s)</p></article>)}</div>}</section>
}

function Empty({ icon, text }: { icon: React.ReactNode; text: string }) { return <div className="mt-5 flex gap-3 rounded-xl bg-[#f6f7f8] p-4 text-sm leading-6 text-[#657384]"><span className="mt-0.5 text-[#7891b6]">{icon}</span>{text}</div> }

function AuditProof({ run, decision, evidence, memories }: { run: DecisionRun; decision: NexaFlowDecision | null; evidence: SourceEvidence[]; memories: RealityMemory[] }) {
  return <details className="mt-8 rounded-2xl border border-[#d8d3ca] bg-[#fbfaf7] p-5"><summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold"><span>Audit proof</span><ChevronDown className="h-4 w-4" /></summary><p className="mt-3 text-sm leading-6 text-[#5d6b7b]">Raw source excerpts are redacted at ingestion. This is the backend response behind the visible decision - not browser-generated state.</p><div className="mt-5 grid gap-4 lg:grid-cols-2"><Proof title="Deterministic SAG rule" value={run.decision_brief.sag_trace} /><Proof title="Decision evidence" value={run.decision_brief.evidence} /><Proof title="Memory provenance" value={run.decision_brief.memory_refs} /><Proof title="Source selection and parsing" value={{ source_selection: decision?.source_selection, parsing: decision?.parsing, source_records: evidence, memories }} /></div></details>
}

function Proof({ title, value }: { title: string; value: unknown }) { return <div><p className="mb-2 text-xs font-bold uppercase tracking-[.13em] text-[#718096]">{title}</p><pre className="max-h-80 overflow-auto rounded-xl border border-[#e0dbd2] bg-[#17212b] p-4 text-xs leading-5 text-[#dce7f6]">{JSON.stringify(value, null, 2)}</pre></div> }
