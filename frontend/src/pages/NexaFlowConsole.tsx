import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react"
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ChevronDown,
  Code2,
  Database,
  FileText,
  Github,
  Loader2,
  MessageSquareText,
  RefreshCw,
  Route,
  ShieldAlert,
  Sparkles,
  UserRound,
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
  if (["connected", "healthy", "decision_ready", "active", "compiled"].includes(status)) {
    return "border-emerald-200 bg-emerald-50 text-emerald-800"
  }
  if (status === "suspended") return "border-rose-200 bg-rose-50 text-rose-800"
  if (["review_required", "setup_required", "unavailable", "stale"].includes(status)) {
    return "border-amber-200 bg-amber-50 text-amber-900"
  }
  return "border-slate-200 bg-slate-50 text-slate-700"
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
    const value = item.excerpt.match(/^\+\s*(?:export\s+)?NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB\s*=\s*(\d+)/im)
      ?? item.excerpt.match(/NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB\s*=\s*(\d+)/i)
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

  return (
    <div className="min-h-screen bg-[#f7f5ef] text-[#1d201e]">
      <header className="border-b border-dashed border-[#d6d1c6] bg-[#f7f5ef]/95">
        <div className="mx-auto flex h-[72px] max-w-6xl items-center justify-between px-5">
          <Link to="/" className="flex items-center gap-3 font-semibold tracking-[-0.02em]">
            <span className="grid h-9 w-9 place-items-center rounded-full bg-[#113d32] text-sm font-bold text-white">B</span>
            <span>Company Brain</span>
          </Link>
          <nav className="hidden items-center gap-7 text-sm text-[#555d58] md:flex">
            <a href="#how-it-works" className="transition hover:text-[#113d32]">How it works</a>
            <a href="#why-brain" className="transition hover:text-[#113d32]">Why Brain</a>
            <a href="#proof" className="transition hover:text-[#113d32]">Proof</a>
          </nav>
          <div className="flex items-center gap-2">
            <Link to="/setup" className="hidden rounded-full border border-dashed border-[#b9c5ba] px-3 py-2 text-xs font-semibold text-[#235044] sm:inline-flex">Connect sources</Link>
            <button type="button" onClick={() => void refresh()} className="inline-flex items-center gap-2 rounded-full border border-[#c9c6bd] bg-[#fffdf8] px-3 py-2 text-xs font-semibold text-[#36423c]">
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} /> Refresh
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 pb-20 pt-12">
        <section className="grid items-start gap-12 lg:grid-cols-[1.05fr_.95fr]">
          <div className="pt-2">
            <p className="text-[10px] font-bold uppercase tracking-[.24em] text-[#16745a]">Operational memory for agent workflows</p>
            <h1 className="mt-5 max-w-2xl text-5xl font-semibold leading-[.98] tracking-[-.065em] text-[#181d1b] sm:text-6xl">
              Keep agents from acting on outdated reality.
            </h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-[#626b65]">
              Company Brain receives what changed in Slack, policy, and code; Qwen turns it into source-linked memory; SAG checks whether the next consequential action is still safe.
            </p>
            <div className="mt-7 flex flex-wrap gap-2 text-xs font-semibold text-[#4c5b53]">
              <span className="rounded-full border border-dashed border-[#b7c6bb] bg-[#f2f8f1] px-3 py-1.5">Slack · policy · GitHub</span>
              <span className="rounded-full border border-dashed border-[#c7c2b6] bg-[#fffdf8] px-3 py-1.5">Qwen memory</span>
              <span className="rounded-full border border-dashed border-[#c7c2b6] bg-[#fffdf8] px-3 py-1.5">Human approval boundary</span>
            </div>
          </div>

          <section className="rounded-2xl border border-dashed border-[#c7c4ba] bg-[#fffdf8] p-5 shadow-[0_18px_60px_rgba(46,55,47,.06)]">
            <div className="flex items-center justify-between border-b border-dashed border-[#d9d4c9] pb-4">
              <p className="font-mono text-[10px] font-bold uppercase tracking-[.18em] text-[#69736d]">Before anyone acts</p>
              <span className="rounded-full bg-[#eaf5e9] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-[#18704f]">Live checkpoint</span>
            </div>
            <div className="mt-5 space-y-1">
              <CheckpointStep number="01" icon={<Database className="h-4 w-4" />} title="Evidence arrives" detail="Slack · Alibaba OSS · GitHub" state={receivedSources === 3 ? "done" : "active"} />
              <CheckpointStep number="02" icon={<Sparkles className="h-4 w-4" />} title="Qwen compiles reality" detail={memories.length ? `${memories.length} source-linked claims` : "Waiting for source evidence"} state={memories.length ? "done" : "waiting"} />
              <CheckpointStep number="03" icon={<Route className="h-4 w-4" />} title="SAG checks the present" detail={activeRun ? verdictLabel(activeRun.decision_brief.verdict) : "No decision yet"} state={activeRun ? (activeRun.decision_brief.verdict === "suspended" ? "risk" : "done") : "waiting"} />
              <CheckpointStep number="04" icon={<UserRound className="h-4 w-4" />} title="A human confirms" detail="No deployment or external action" state="waiting" />
            </div>
            <div className="mt-5 grid gap-2 sm:grid-cols-2">
              <button type="button" disabled={running} onClick={() => void runCheck()} className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#113d32] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#0c2e26] disabled:opacity-60">
                {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldAlert className="h-4 w-4" />}
                {running ? "Checking evidence…" : "Run safety check"}
              </button>
              <button type="button" disabled={matrixRunning} onClick={() => void runMatrix()} className="inline-flex items-center justify-center gap-2 rounded-xl border border-[#b9c9bb] bg-[#f3f8f0] px-4 py-3 text-sm font-semibold text-[#1b5845] transition hover:bg-[#eaf4e8] disabled:opacity-60">
                {matrixRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Code2 className="h-4 w-4" />}
                {matrixRunning ? "Running Qwen proof…" : "Run five-case proof"}
              </button>
            </div>
            {decision && <p aria-live="polite" className="mt-3 rounded-lg border border-dashed border-[#c7c2b7] px-3 py-2 text-center text-xs text-[#5d6861]"><span className="font-semibold">Decision returned:</span> {verdictLabel(decision.run.decision_brief.verdict)}</p>}
          </section>
        </section>

        {error && <div className="mt-8 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}</div>}

        <section id="how-it-works" className="mt-20 border-t border-dashed border-[#ccc7bc] pt-8">
          <div className="grid gap-6 md:grid-cols-[.8fr_1.2fr] md:items-end">
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-[.2em] text-[#16745a]">How Company Brain works</p>
              <h2 className="mt-3 text-3xl font-semibold leading-tight tracking-[-.045em] sm:text-4xl">One memory checkpoint. Four explicit handoffs.</h2>
            </div>
            <p className="max-w-xl text-sm leading-7 text-[#667069]">The model interprets evidence; deterministic safety rules decide; a named owner confirms. That separation is what makes the result useful inside an existing agent workflow.</p>
          </div>
          <div className="mt-8 grid gap-3 md:grid-cols-4">
            <HandoffCard number="01" title="Receive" detail="Signed, scoped source events become immutable evidence with freshness and provenance." icon={<Database className="h-5 w-5" />} />
            <HandoffCard number="02" title="Remember" detail="Qwen compiles claims and keeps the source lineage instead of flattening context into chat." icon={<Sparkles className="h-5 w-5" />} />
            <HandoffCard number="03" title="Check" detail="SAG compares current reality with the approved policy and missing-evidence predicates." icon={<Route className="h-5 w-5" />} />
            <HandoffCard number="04" title="Confirm" detail="The owner receives a recommendation. Company Brain never deploys, posts, or changes systems." icon={<UserRound className="h-5 w-5" />} />
          </div>
        </section>

        {activeRun && <div id="decision" ref={decisionPanelRef}><DecisionPanel run={activeRun} parsing={decision?.parsing} boundary={decision?.boundary} /></div>}

        <section id="why-brain" className="mt-20 border-t border-dashed border-[#ccc7bc] pt-8">
          <div className="grid gap-8 lg:grid-cols-[.72fr_1.28fr] lg:items-start">
            <div>
              <p className="font-mono text-[10px] font-bold uppercase tracking-[.2em] text-[#16745a]">Why Brain</p>
              <h2 className="mt-3 text-3xl font-semibold leading-tight tracking-[-.045em] sm:text-4xl">Agents can reason. They cannot know which reality is current.</h2>
            </div>
            <div className="overflow-hidden rounded-2xl border border-dashed border-[#c9c5bb] bg-[#fffdf8]">
              <div className="grid grid-cols-[1fr_1fr] border-b border-dashed border-[#d7d1c6] text-xs font-bold uppercase tracking-[.12em] text-[#737c75]"><div className="px-4 py-3">Without a checkpoint</div><div className="border-l border-dashed border-[#d7d1c6] px-4 py-3 text-[#16745a]">With Company Brain</div></div>
              <ComparisonRow label="Context" before="Agent sees a prompt or one event" after="Fresh evidence with source, time, and scope" />
              <ComparisonRow label="Memory" before="Useful context disappears into a thread" after="Qwen claim with provenance and supersession" />
              <ComparisonRow label="Decision" before="Model output becomes an action" after="SAG trace returns a governed recommendation" />
              <ComparisonRow label="Accountability" before="No clear owner or replay" after="Named human owner and audit proof" />
            </div>
          </div>
        </section>

        <section className="mt-16">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><div><p className="font-mono text-[10px] font-bold uppercase tracking-[.2em] text-[#69736d]">Connected reality</p><h2 className="mt-2 text-2xl font-semibold tracking-[-.035em]">Three inputs · one decision</h2></div><span className="text-xs text-[#758078]">{configuredSources}/3 connected · backend-derived</span></div>
          <div className="grid gap-3 md:grid-cols-3">{(overview?.connections ?? []).filter((item) => item.provider !== "web").map((item) => <ConnectionCard key={item.provider} connection={item} />)}</div>
        </section>

        <section className="mt-4 rounded-2xl border border-dashed border-[#c9c5bb] bg-[#fffdf8] p-5"><p className="font-mono text-[10px] font-bold uppercase tracking-[.18em] text-[#69736d]">Evidence → memory → decision</p><div className="mt-4 grid gap-3 md:grid-cols-3"><FlowStep number="1" title="Receive" detail={`${receivedSources}/3 source records`} state={receivedSources === 3 ? "done" : "active"} /><FlowStep number="2" title="Qwen compiles" detail={memories.length ? `${memories.length} source-linked memories` : "Waiting for source evidence"} state={memories.length ? "done" : "waiting"} /><FlowStep number="3" title="SAG checks" detail={activeRun ? verdictLabel(activeRun.decision_brief.verdict) : "Waiting for release check"} state={activeRun ? (activeRun.decision_brief.verdict === "suspended" ? "risk" : "done") : "waiting"} /></div></section>

        {!loading && overview && !overview.release_check_ready && <section className="mt-6 rounded-xl border border-amber-200 bg-[#fffaf0] p-5"><div className="flex gap-3"><AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" /><div><p className="font-semibold text-amber-950">Release check is waiting for real evidence</p><ul className="mt-2 space-y-1 text-sm leading-6 text-amber-900">{overview.readiness_reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul><Link to="/setup" className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-[#17614b]">Configure sources <ArrowRight className="h-4 w-4" /></Link></div></div></section>}

        {(matrix || matrixError) && <div id="proof"><CaseMatrix matrix={matrix} error={matrixError} /></div>}

        <section className="mt-12 grid gap-5 lg:grid-cols-2"><EvidenceTimeline evidence={evidence} /><MemoryLineage memories={memories} /></section>
        {activeRun && <AuditProof run={activeRun} decision={decision} evidence={evidence} memories={memories} />}

        <footer className="mt-20 border-t border-dashed border-[#ccc7bc] pt-6 text-xs text-[#758078]"><div className="flex flex-wrap items-center justify-between gap-3"><p>Company Brain · governed memory for consequential workflows</p><div className="flex items-center gap-4"><Link to="/setup" className="hover:text-[#113d32]">Technical proof</Link><a href="#how-it-works" className="hover:text-[#113d32]">How it works ↑</a></div></div></footer>
      </main>
    </div>
  )
}

function CheckpointStep({ number, icon, title, detail, state }: { number: string; icon: ReactNode; title: string; detail: string; state: "done" | "active" | "waiting" | "risk" }) {
  const tone = state === "done" ? "border-emerald-200 bg-[#f3faf0]" : state === "risk" ? "border-rose-200 bg-[#fff8f5]" : state === "active" ? "border-[#a9c7b4] bg-[#f5fbf2]" : "border-[#e1ddd4] bg-[#fbfaf6]"
  const dot = state === "done" ? "bg-[#16745a] text-white" : state === "risk" ? "bg-[#b42343] text-white" : state === "active" ? "bg-[#113d32] text-white" : "bg-[#e2e0d8] text-[#69736d]"
  return <div className={`flex items-center gap-3 rounded-xl border p-3 ${tone}`}><span className={`grid h-8 w-8 shrink-0 place-items-center rounded-full ${dot}`}>{state === "done" ? <CheckCircle2 className="h-4 w-4" /> : icon}</span><div className="min-w-0"><div className="flex items-center gap-2"><span className="font-mono text-[9px] font-bold text-[#8a928c]">{number}</span><p className="text-sm font-semibold">{title}</p></div><p className="truncate text-xs text-[#69736d]">{detail}</p></div></div>
}

function HandoffCard({ number, title, detail, icon }: { number: string; title: string; detail: string; icon: ReactNode }) {
  return <article className="rounded-2xl border border-dashed border-[#c9c5bb] bg-[#fffdf8] p-4"><div className="flex items-center justify-between"><span className="font-mono text-[10px] font-bold tracking-[.16em] text-[#8b918a]">{number}</span><span className="grid h-9 w-9 place-items-center rounded-full bg-[#edf5eb] text-[#16745a]">{icon}</span></div><h3 className="mt-6 text-base font-semibold">{title}</h3><p className="mt-2 text-sm leading-6 text-[#667069]">{detail}</p></article>
}

function ComparisonRow({ label, before, after }: { label: string; before: string; after: string }) {
  return <div className="grid grid-cols-[1fr_1fr] border-b border-dashed border-[#e0dbd1] last:border-b-0"><div className="px-4 py-4"><p className="text-[10px] font-bold uppercase tracking-[.12em] text-[#9a978e]">{label}</p><p className="mt-1 text-sm leading-5 text-[#777a75]">{before}</p></div><div className="border-l border-dashed border-[#e0dbd1] bg-[#f4f9f1] px-4 py-4"><p className="text-[10px] font-bold uppercase tracking-[.12em] text-[#16745a]">Company Brain</p><p className="mt-1 text-sm leading-5 text-[#385246]">{after}</p></div></div>
}

function ConnectionCard({ connection }: { connection: SourceConnection }) {
  const Icon = providerIcon(connection.provider)
  return <article className="rounded-2xl border border-dashed border-[#c9c5bb] bg-[#fffdf8] p-5"><div className="flex items-start justify-between gap-2"><span className="grid h-10 w-10 place-items-center rounded-full bg-[#edf4ee] text-[#1c634d]"><Icon className="h-5 w-5" /></span><span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${statusTone(connection.status)}`}>{titleStatus(connection.status)}</span></div><h3 className="mt-5 font-semibold">{connection.title}</h3><p className="mt-2 min-h-10 text-xs leading-5 text-[#69736d]">{connection.allowed_scope.join(" · ")}</p><p className="mt-4 border-t border-dashed border-[#e0dbd1] pt-3 text-xs text-[#7a817b]">Last evidence: {time(connection.last_success_at)}</p></article>
}

function FlowStep({ number, title, detail, state }: { number: string; title: string; detail: string; state: "done" | "active" | "waiting" | "risk" }) {
  const tone = state === "done" ? "border-emerald-200 bg-[#f3faf0]" : state === "risk" ? "border-rose-200 bg-[#fff8f5]" : state === "active" ? "border-[#a9c7b4] bg-[#f5fbf2]" : "border-[#e1ddd4] bg-[#fbfaf6]"
  const dot = state === "done" ? "bg-[#16745a] text-white" : state === "risk" ? "bg-[#b42343] text-white" : state === "active" ? "bg-[#113d32] text-white" : "bg-[#e2e0d8] text-[#69736d]"
  return <div className={`rounded-xl border p-3 ${tone}`}><div className="flex items-center gap-3"><span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-bold ${dot}`}>{state === "done" ? <CheckCircle2 className="h-4 w-4" /> : number}</span><div><p className="text-sm font-semibold">{title}</p><p className="text-xs text-[#69736d]">{detail}</p></div></div></div>
}

function DecisionPanel({ run, parsing, boundary }: { run: DecisionRun; parsing?: Record<string, unknown>; boundary?: string }) {
  const brief = run.decision_brief
  const suspended = brief.verdict === "suspended"
  const review = brief.verdict === "review_required"
  const Icon = suspended || review ? ShieldAlert : CheckCircle2
  const facts = brief.facts ?? []
  return <section className={`mt-12 rounded-2xl border p-6 ${suspended ? "border-rose-200 bg-[#fff8f5]" : review ? "border-amber-200 bg-[#fffaf0]" : "border-emerald-200 bg-[#f3faf0]"}`}><div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between"><div className="flex max-w-3xl gap-4"><span className={`grid h-11 w-11 shrink-0 place-items-center rounded-full ${suspended ? "bg-rose-100 text-rose-800" : review ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}><Icon className="h-5 w-5" /></span><div><div className="flex flex-wrap items-center gap-2"><p className="font-mono text-[10px] font-bold uppercase tracking-[.15em]">Backend decision</p><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(brief.verdict)}`}>{verdictLabel(brief.verdict)}</span></div><h2 className="mt-3 text-2xl font-semibold leading-tight tracking-[-.035em]">{brief.recommended_next_action}</h2></div></div><div className="min-w-48 rounded-xl border border-dashed border-black/15 bg-white/65 p-4 text-sm"><p className="font-mono text-[10px] font-bold uppercase tracking-[.13em] text-[#68736c]">Human owner</p><p className="mt-1 font-semibold">{brief.owner}</p><p className="mt-3 font-mono text-[10px] font-bold uppercase tracking-[.13em] text-[#68736c]">Execution</p><p className="mt-1 font-semibold">Human confirmation required</p></div></div><div className="mt-5 grid gap-4 lg:grid-cols-[1.25fr_.75fr]"><div className="rounded-xl border border-[#bdd0c0] bg-[#edf7eb] p-4"><div className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[.13em] text-[#16745a]"><Sparkles className="h-4 w-4" />Qwen interpretation</div><p className="mt-2 text-sm leading-6 text-[#304e40]">{brief.inference.text}</p><p className="mt-3 text-xs font-semibold text-[#547060]">{brief.inference.is_model_generated ? `Compiled by ${brief.inference.generated_by}` : "Deterministic fallback · Qwen response unavailable"}</p></div><div className="rounded-xl border border-dashed border-black/10 bg-white/55 p-4"><p className="font-mono text-[10px] font-bold uppercase tracking-[.13em] text-[#68736c]">Why this verdict?</p><p className="mt-2 text-sm leading-6 text-[#4f5e55]">{plainRule(brief.verdict)}</p><p className="mt-3 text-xs font-semibold text-[#68736c]">SAG status: {String(brief.sag_trace.status ?? "not evaluated")}</p></div></div>{facts.length > 0 && <div className="mt-5 grid gap-3 border-t border-dashed border-black/10 pt-5 md:grid-cols-3">{facts.slice(0, 3).map((fact, index) => <div key={`${fact.statement}-${index}`} className="rounded-xl border border-dashed border-black/10 bg-white/55 p-3"><p className="font-mono text-[10px] font-bold uppercase tracking-[.13em] text-[#68736c]">Observed fact</p><p className="mt-1 text-sm leading-5">{fact.statement}</p></div>)}</div>}{parsing && <div className="mt-5 grid gap-3 border-t border-dashed border-black/10 pt-5 sm:grid-cols-3"><Fact label="Runbook minimum" value={parsing.runbook_minimum_memory_mb ? `${parsing.runbook_minimum_memory_mb} MiB` : "Not parsed"} /><Fact label="Merged configuration" value={parsing.merged_worker_memory_mb ? `${parsing.merged_worker_memory_mb} MiB` : "Not parsed"} /><Fact label="Slack incident" value={parsing.linked_incident_open === true ? "Open" : parsing.linked_incident_open === false ? "Closed" : "Not identified"} /></div>}{boundary && <p className="mt-5 text-xs leading-5 text-[#64736b]">{boundary}</p>}</section>
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-dashed border-black/10 bg-white/55 p-3"><p className="font-mono text-[10px] font-bold uppercase tracking-[.13em] text-[#68736c]">{label}</p><p className="mt-1 font-semibold">{value}</p></div> }

function EvidenceTimeline({ evidence }: { evidence: SourceEvidence[] }) {
  const shown = evidence.filter((item) => ["slack", "alibaba_oss", "github"].includes(item.provider))
  return <section className="rounded-2xl border border-dashed border-[#c9c5bb] bg-[#fffdf8] p-6"><div className="flex items-start justify-between gap-4"><div><p className="font-mono text-[10px] font-bold uppercase tracking-[.14em] text-[#69736d]">Persisted evidence</p><h2 className="mt-2 text-xl font-semibold">What the company systems sent</h2></div><span className="rounded-full bg-[#edf4ee] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-[#1b654d]">Source ledger</span></div>{shown.length === 0 ? <Empty icon={<Activity className="h-5 w-5" />} text="No real source records yet. Configure Slack, Alibaba OSS, and GitHub, then refresh." /> : <div className="mt-5 space-y-3">{shown.map((item) => <EvidenceCard key={item.ingestion_id} item={item} />)}</div>}</section>
}

function EvidenceCard({ item }: { item: SourceEvidence }) {
  const Icon = providerIcon(item.provider)
  const qwen = qwenStatus(item.qwen_status)
  return <article className="rounded-xl border border-dashed border-[#d6d1c6] bg-[#fbfaf6] p-4"><div className="flex items-start gap-3"><span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#edf4ee] text-[#1c634d]"><Icon className="h-4 w-4" /></span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><p className="font-semibold">{providerLabel(item.provider)}</p><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(item.stage)}`}>{titleStatus(item.stage)}</span><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(qwen)}`}>Qwen {qwen}</span></div><p className="mt-1 text-xs text-[#78827b]">{providerRole(item.provider)} · {item.freshness} · {time(item.retrieved_at)}</p></div></div><div className="mt-4 rounded-lg border border-dashed border-[#ddd8ce] bg-white/70 p-3"><p className="font-mono text-[10px] font-bold uppercase tracking-[.13em] text-[#718078]">What arrived</p><p className="mt-1 text-sm leading-6 text-[#394b41]">{evidenceHeadline(item)}</p></div><details className="mt-3"><summary className="cursor-pointer text-xs font-semibold text-[#26705a]">View source excerpt and provenance</summary><p className="mt-2 text-xs leading-5 text-[#68736c]">{cleanText(item.excerpt, 1400)}</p><p className="mt-2 font-mono text-[10px] text-[#88928a]">Source ID {item.ingestion_id} · SHA {item.raw_payload_sha256.slice(0, 12)}…</p></details></article>
}

function MemoryLineage({ memories }: { memories: RealityMemory[] }) {
  const active = useMemo(() => memories.slice(0, 6), [memories])
  return <section className="rounded-2xl border border-dashed border-[#c9c5bb] bg-[#fffdf8] p-6"><div className="flex items-start justify-between gap-4"><div><p className="font-mono text-[10px] font-bold uppercase tracking-[.14em] text-[#69736d]">Reality memory</p><h2 className="mt-2 text-xl font-semibold">What Qwen carried forward</h2></div><span className="rounded-full bg-[#f1ebff] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-[#6b4bb5]">Qwen + provenance</span></div>{active.length === 0 ? <Empty icon={<Sparkles className="h-5 w-5" />} text="Memory appears after a source record is processed. If Qwen is unavailable, the console will say so." /> : <div className="mt-5 space-y-3">{active.map((memory) => <MemoryCard key={memory.memory_id} memory={memory} />)}</div>}</section>
}

function MemoryCard({ memory }: { memory: RealityMemory }) {
  const qwen = memory.qwen_generated ? "compiled" : "unavailable"
  return <article className="rounded-xl border border-dashed border-[#d6d1c6] bg-[#fbfaf6] p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-xs font-semibold text-[#516158]">{cleanText(memory.subject, 90)}</p><p className="mt-1 font-mono text-[10px] font-bold uppercase tracking-[.13em] text-[#8a948c]">Qwen operational claim</p></div><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(memory.status)}`}>{titleStatus(memory.status)}</span></div><p className="mt-3 text-sm leading-6 text-[#394b41]">{cleanText(memory.claim, 300)}</p><div className="mt-3 flex flex-wrap items-center gap-2 text-[10px] text-[#78827b]"><span className={`rounded-full border px-2 py-0.5 font-bold uppercase ${statusTone(qwen)}`}>Qwen {qwen}</span><span>{memory.source_ingestion_ids.length} linked source{memory.source_ingestion_ids.length === 1 ? "" : "s"}</span><span>updated {time(memory.updated_at)}</span></div><details className="mt-3"><summary className="cursor-pointer text-xs font-semibold text-[#26705a]">How this memory is grounded</summary><p className="mt-2 text-xs leading-5 text-[#68736c]">{cleanText(memory.qwen_rationale || memory.claim, 900)}</p><p className="mt-2 font-mono text-[10px] text-[#88928a]">Memory ID {memory.memory_id} · source IDs {memory.source_ingestion_ids.join(", ") || "none"}</p></details></article>
}

function CaseMatrix({ matrix, error }: { matrix: NexaFlowCaseMatrix | null; error: string | null }) {
  return <section className="mt-12 rounded-2xl border border-dashed border-[#becdc1] bg-[#f3f9f1] p-6"><div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between"><div><p className="font-mono text-[10px] font-bold uppercase tracking-[.14em] text-[#16745a]">Qwen verification</p><h2 className="mt-2 text-2xl font-semibold tracking-[-.035em]">Five realities · one governed engine</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-[#5b6d61]">Each case is compiled through Qwen, then evaluated by the same deterministic SAG rule. These runs are ephemeral and never change live company memory.</p></div>{matrix && <span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase ${statusTone(matrix.qwen_configured ? "compiled" : "unavailable")}`}>{matrix.qwen_configured ? "Qwen configured" : "Qwen unavailable"}</span>}</div>{error && <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900">{error}</div>}{matrix && <div className="mt-5 grid gap-3 md:grid-cols-2 lg:grid-cols-3">{matrix.cases.map((item) => <CaseCard key={item.case_id} item={item} />)}</div>}{matrix && <p className="mt-5 text-xs leading-5 text-[#68736c]">{matrix.boundary}</p>}</section>
}

function CaseCard({ item }: { item: QwenCaseResult }) {
  return <article className="rounded-xl border border-dashed border-[#c9d6ca] bg-white/80 p-4"><div className="flex items-start justify-between gap-3"><div><p className="text-sm font-semibold">{item.title}</p><p className="mt-1 text-xs leading-5 text-[#68736c]">{item.description}</p></div><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${statusTone(item.verdict)}`}>{verdictLabel(item.verdict)}</span></div><div className="mt-3 rounded-lg border border-dashed border-[#d8cbed] bg-[#f3edff] p-3"><div className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[.12em] text-[#6b4bb5]"><Sparkles className="h-3.5 w-3.5" />Qwen {item.qwen.status}</div><p className="mt-1 text-xs leading-5 text-[#51436f]">{cleanText(item.qwen.summary, 180)}</p>{item.qwen.model && <p className="mt-2 font-mono text-[10px] text-[#806db1]">Model: {item.qwen.model} · {item.qwen.source_count} source records</p>}</div><p className="mt-3 text-xs leading-5 text-[#58697e]"><span className="font-semibold">SAG:</span> {plainRule(item.verdict)}</p></article>
}

function Empty({ icon, text }: { icon: ReactNode; text: string }) { return <div className="mt-5 flex gap-3 rounded-xl bg-[#f5f4ee] p-4 text-sm leading-6 text-[#65736b]"><span className="mt-0.5 text-[#258064]">{icon}</span>{text}</div> }

function AuditProof({ run, decision, evidence, memories }: { run: DecisionRun; decision: NexaFlowDecision | null; evidence: SourceEvidence[]; memories: RealityMemory[] }) {
  return <details className="mt-8 rounded-2xl border border-dashed border-[#c9c5bb] bg-[#fbfaf6] p-5"><summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold"><span className="flex items-center gap-2"><BookOpen className="h-4 w-4 text-[#26705a]" /> Audit proof</span><ChevronDown className="h-4 w-4" /></summary><p className="mt-3 text-sm leading-6 text-[#5d6b62]">The readable cards above are backed by the server response. Open the raw trace only when you need source IDs, provenance, or the exact SAG evaluation.</p><div className="mt-5 grid gap-4 lg:grid-cols-2"><Proof title="Deterministic SAG rule" value={run.decision_brief.sag_trace} /><Proof title="Decision evidence" value={run.decision_brief.evidence} /><Proof title="Memory provenance" value={run.decision_brief.memory_refs} /><Proof title="Source selection and parsing" value={{ source_selection: decision?.source_selection, parsing: decision?.parsing, source_records: evidence, memories }} /></div></details>
}

function Proof({ title, value }: { title: string; value: unknown }) { return <div><p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[.13em] text-[#718078]">{title}</p><pre className="max-h-80 overflow-auto rounded-xl border border-[#353a37] bg-[#1e2522] p-4 text-xs leading-5 text-[#dce7df]">{JSON.stringify(value, null, 2)}</pre></div> }
