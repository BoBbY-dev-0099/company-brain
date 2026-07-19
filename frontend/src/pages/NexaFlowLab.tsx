import { useEffect, useState } from "react"
import { ArrowLeft, Bot, Cloud, FileText, Github, LoaderCircle, MessageSquareText, Play, ShieldAlert } from "lucide-react"
import { Link } from "react-router-dom"
import {
  createDemoMcpSession,
  createDemoSession,
  getNexaFlowScenarios,
  runNexaFlowScenario,
  type NexaFlowLab,
  type NexaFlowScenario,
  type RealityMemory,
  type SourceEvent,
} from "../lib/api"
import { inspectMemoryThroughMcp, type McpLog } from "../lib/mcp"

function iconFor(provider: string) {
  if (provider === "slack") return MessageSquareText
  if (provider === "github") return Github
  if (provider === "google_drive") return FileText
  return Cloud
}

function memoryTone(status: string) {
  if (status === "active") return "border-emerald-200 bg-emerald-50 text-emerald-800"
  if (status === "superseded") return "border-slate-200 bg-slate-50 text-slate-600"
  return "border-amber-200 bg-amber-50 text-amber-800"
}

function outcomeTone(status: string) {
  if (status === "review_required" || status === "conflict_detected") return "border-amber-200 bg-amber-50 text-amber-900"
  if (status === "superseded") return "border-blue-200 bg-blue-50 text-blue-900"
  return "border-emerald-200 bg-emerald-50 text-emerald-900"
}

export default function NexaFlowLab() {
  const [scenarios, setScenarios] = useState<NexaFlowScenario[]>([])
  const [lab, setLab] = useState<NexaFlowLab | null>(null)
  const [mcpMemories, setMcpMemories] = useState<RealityMemory[]>([])
  const [logs, setLogs] = useState<McpLog[]>([])
  const [runningId, setRunningId] = useState<string | null>(null)
  const [phase, setPhase] = useState("Choose a scenario. Each run uses a private, expiring evidence sandbox.")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getNexaFlowScenarios()
      .then((response) => setScenarios(response.scenarios))
      .catch(() => setError("The NexaFlow scenario catalog could not load."))
  }, [])

  async function runScenario(scenarioId: string) {
    if (runningId) return
    setRunningId(scenarioId)
    setError(null)
    setLab(null)
    setMcpMemories([])
    setLogs([])
    try {
      await createDemoSession()
      setPhase("Writing fixture evidence to the immutable, browser-private source ledger.")
      const result = await runNexaFlowScenario(scenarioId)
      setLab(result)
      const compiled = result.events.filter((event) => event.qwen_status.startsWith("compiled")).length
      setPhase(`${result.events.length} evidence record(s) processed; Qwen compiled ${compiled} Reality Memory candidate(s). Reading the result through MCP.`)
      const session = await createDemoMcpSession()
      const memories = await inspectMemoryThroughMcp({
        endpoint: session.mcp_endpoint,
        apiKey: session.api_key,
        query: result.scenario.agent_query,
        onLog: (entry) => setLogs((current) => [...current.filter((item) => item.step !== entry.step), entry]),
      })
      setMcpMemories(memories)
      setPhase("Complete. The answer, evidence lineage, and MCP memory read came from this temporary sandbox.")
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The NexaFlow scenario could not complete."
      setError(message)
      setPhase("The scenario stopped before Company Brain returned a complete evidence trace.")
    } finally {
      setRunningId(null)
    }
  }

  return <div className="min-h-screen bg-[#f5f1e8] text-[#17212b]">
    <header className="border-b border-[#d9d3c8] bg-[#f5f1e8]/95">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5">
        <Link to="/" className="inline-flex items-center gap-2 text-sm font-semibold"><ArrowLeft className="h-4 w-4" />Reality Console</Link>
        <span className="text-xs font-bold uppercase tracking-[0.15em] text-[#2f5eeb]">NexaFlow Logistics test company</span>
      </div>
    </header>
    <main className="mx-auto max-w-7xl px-5 py-10">
      <section className="max-w-3xl">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Temporal memory lab</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-[-0.05em] md:text-5xl">Show what Company Brain knows, changed, and cannot honestly claim.</h1>
        <p className="mt-4 text-base leading-7 text-[#5a6775]">NexaFlow is a synthetic logistics company. Its Slack, Drive, GitHub, and CRM-shaped records are labelled fixtures; no real company or connector is contacted. The source ledger and Qwen compilation are real sandbox paths.</p>
      </section>

      <section className="mt-8 grid gap-3 md:grid-cols-2">
        {scenarios.map((scenario, index) => <article key={scenario.id} className="rounded-2xl border border-[#d8d0c2] bg-[#fffcf7] p-5 shadow-[0_12px_32px_rgba(52,45,35,0.04)]">
          <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-[#2f5eeb]">Scene 0{index + 1}</p>
          <h2 className="mt-2 text-xl font-semibold">{scenario.title}</h2>
          <p className="mt-2 text-sm font-medium leading-6 text-[#354454]">{scenario.question}</p>
          <p className="mt-2 text-sm leading-6 text-[#637080]">{scenario.summary}</p>
          <button type="button" disabled={Boolean(runningId)} onClick={() => void runScenario(scenario.id)} className="mt-5 inline-flex items-center gap-2 rounded-xl bg-[#17212b] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-60">
            {runningId === scenario.id ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {runningId === scenario.id ? "Running evidence trace" : "Run this scenario"}
          </button>
        </article>)}
      </section>

      <p className="mt-5 rounded-xl border border-[#d9d3c8] bg-[#fffcf7] px-4 py-3 text-sm text-[#536170]">{phase}</p>
      {error && <p className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</p>}

      {lab && <>
        <section className="mt-7 rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-6">
          <div className="flex flex-wrap items-center gap-3"><span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide ${outcomeTone(lab.answer.status)}`}>{lab.answer.status.replaceAll("_", " ")}</span><span className="text-xs font-medium text-[#657284]">Deterministic evidence conclusion</span></div>
          <h2 className="mt-4 text-2xl font-semibold tracking-tight">{lab.answer.headline}</h2>
          <p className="mt-3 max-w-4xl text-sm leading-6 text-[#536170]">{lab.answer.response}</p>
          <div className="mt-5 grid gap-3 md:grid-cols-3"><Fact label="Confidence" value={lab.answer.confidence.replaceAll("_", " ")} /><Fact label="Next action" value={lab.answer.recommended_action} /><Fact label="Decision boundary" value="No external action; owner must verify before committing." /></div>
          <p className="mt-4 rounded-xl border border-[#dbe3f2] bg-[#f8faff] p-3 text-xs leading-5 text-[#536170]"><strong>Qwen boundary:</strong> {lab.answer.qwen_boundary}</p>
        </section>

        <section className="mt-7 grid gap-5 lg:grid-cols-[1.05fr_0.95fr]">
          <article className="rounded-2xl border border-[#d9d3c8] bg-[#fffcf7] p-5"><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">1. Evidence received</p><div className="mt-4 space-y-3">{lab.events.map((event) => <EvidenceRow key={event.ingestion_id} event={event} />)}</div></article>
          <article className="rounded-2xl border border-[#d9d3c8] bg-[#fffcf7] p-5"><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">2. Qwen Reality Memory reconciliation</p><div className="mt-4 space-y-3">{lab.memories.map((memory) => <MemoryRow key={memory.memory_id} memory={memory} />)}</div><div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-3"><div className="flex items-center gap-2 text-sm font-semibold text-amber-900"><ShieldAlert className="h-4 w-4" />Missing evidence</div><ul className="mt-2 space-y-1 text-xs leading-5 text-amber-900">{lab.answer.missing_evidence.map((item) => <li key={item}>- {item}</li>)}</ul></div></article>
        </section>

        <section className="mt-7 grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
          <article className="rounded-2xl border border-[#d9d3c8] bg-[#fffcf7] p-5"><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">3. MCP agent handoff</p><div className="mt-3 flex items-center gap-2 text-sm font-semibold"><Bot className="h-4 w-4 text-[#2f5eeb]" />Authenticated inspect_memory</div><p className="mt-2 text-xs leading-5 text-[#637080]">A disposable browser-private MCP key queried active and superseded memory. The caller never supplied an organization ID.</p>{logs.length > 0 && <div className="mt-4 space-y-2">{logs.map((log) => <div key={log.step} className="rounded-xl border border-[#e3e8f1] bg-[#f8fafc] p-3"><p className="font-mono text-xs text-[#2148c7]">{log.step}</p><p className="mt-1 text-xs leading-5 text-[#536170]">{log.detail}</p></div>)}</div>}</article>
          <article className="rounded-2xl border border-[#d9d3c8] bg-[#fffcf7] p-5"><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">4. What the next agent can read</p>{mcpMemories.length === 0 ? <p className="mt-4 text-sm text-[#637080]">MCP did not return a matching memory record.</p> : <div className="mt-4 space-y-3">{mcpMemories.map((memory) => <MemoryRow key={`mcp-${memory.memory_id}`} memory={memory} />)}</div>}</article>
        </section>

        <details className="group mt-7 rounded-2xl border border-[#d9d3c8] bg-[#fffcf7]"><summary className="cursor-pointer px-5 py-4 text-sm font-semibold">Audit proof: raw backend-shaped records only</summary><div className="grid gap-4 border-t border-[#e5ddd0] p-5 lg:grid-cols-3"><pre className="overflow-auto rounded-xl bg-[#17212b] p-3 text-[11px] leading-5 text-[#d9e2ec]">{JSON.stringify(lab.events, null, 2)}</pre><pre className="overflow-auto rounded-xl bg-[#17212b] p-3 text-[11px] leading-5 text-[#d9e2ec]">{JSON.stringify(lab.memories, null, 2)}</pre><pre className="overflow-auto rounded-xl bg-[#17212b] p-3 text-[11px] leading-5 text-[#d9e2ec]">{JSON.stringify(mcpMemories, null, 2)}</pre></div></details>
      </>}
    </main>
  </div>
}

function EvidenceRow({ event }: { event: SourceEvent }) {
  const Icon = iconFor(event.provider)
  return <div className="rounded-xl border border-[#e3e8f1] bg-[#fbfcfe] p-3"><div className="flex items-start gap-3"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#edf2fb] text-[#2f5eeb]"><Icon className="h-4 w-4" /></span><div><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold">{event.source_name}</span><span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-800">{event.stage.replaceAll("_", " ")}</span></div><p className="mt-1 text-xs leading-5 text-[#536170]">{event.excerpt}</p><p className="mt-2 text-[10px] text-[#738194]">Observed {new Date(event.occurred_at).toLocaleDateString()} · {event.freshness ?? "unknown"} · Qwen {event.qwen_status}</p></div></div></div>
}

function MemoryRow({ memory }: { memory: RealityMemory }) {
  return <div className="rounded-xl border border-[#e3e8f1] bg-[#fbfcfe] p-3"><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold">{memory.subject}</span><span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold uppercase ${memoryTone(memory.status)}`}>{memory.status}</span></div><p className="mt-2 text-xs leading-5 text-[#536170]">{memory.claim}</p><p className="mt-2 text-[10px] text-[#738194]">{memory.source_ingestion_ids.length} source link{memory.source_ingestion_ids.length === 1 ? "" : "s"} · {memory.predicate}</p></div>
}

function Fact({ label, value }: { label: string; value: string }) {
  return <div className="rounded-xl border border-[#e3e8f1] bg-white p-3"><p className="text-[10px] font-bold uppercase tracking-[0.12em] text-[#718096]">{label}</p><p className="mt-1 text-sm font-medium leading-5">{value}</p></div>
}
