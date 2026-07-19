import { useState } from "react"
import { ArrowLeft, Check, CircleAlert, FileText, Github, LoaderCircle, MessageSquareText, Play } from "lucide-react"
import { Link } from "react-router-dom"
import { createDemoMcpSession, createDemoSession, runDemoCompanyLab, type DemoCompanyLab, type SourceEvent } from "../lib/api"
import { evaluateWorkflowThroughMcp, type McpLog } from "../lib/mcp"
import type { DecisionBrief, WorkflowRun } from "../types/schema"

function sourceIcon(provider: string) {
  if (provider === "slack") return MessageSquareText
  if (provider === "github") return Github
  return FileText
}

function briefOf(run: WorkflowRun | null) {
  return (run?.decision_brief ?? run?.brief ?? null) as DecisionBrief | null
}

export default function IntegrationLab() {
  const [lab, setLab] = useState<DemoCompanyLab | null>(null)
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [logs, setLogs] = useState<McpLog[]>([])
  const [phase, setPhase] = useState("Ready to create a private test company.")
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function runLab() {
    setRunning(true)
    setError(null)
    setLab(null)
    setRun(null)
    setLogs([])
    try {
      await createDemoSession()
      setPhase("Creating Northstar Logistics evidence in a browser-private sandbox…")
      const result = await runDemoCompanyLab()
      setLab(result)
      const compiled = result.events.filter((event) => event.qwen_status.startsWith("compiled")).length
      setPhase(`${result.events.length} fixture records processed; Qwen compiled ${compiled} source-linked memory candidate(s). Calling MCP…`)
      const session = await createDemoMcpSession()
      const decision = await evaluateWorkflowThroughMcp({
        endpoint: session.mcp_endpoint,
        apiKey: session.api_key,
        templateId: result.workflow.template_id,
        evidence: result.workflow.evidence,
        liveContext: result.workflow.live_context,
        onLog: (entry) => setLogs((current) => [...current.filter((item) => item.step !== entry.step), entry]),
      })
      setRun(decision)
      setPhase("Complete. The source pipeline and MCP decision used only this temporary sandbox.")
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The test company could not complete."
      setError(message)
      setPhase("Test stopped before a decision was returned.")
    } finally {
      setRunning(false)
    }
  }

  const brief = briefOf(run)
  return <div className="min-h-screen bg-[#f5f1e8] text-[#17212b]">
    <header className="border-b border-[#d9d3c8] bg-[#f5f1e8]/95"><div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5"><Link to="/app/connect" className="inline-flex items-center gap-2 text-sm font-semibold"><ArrowLeft className="h-4 w-4" />Integration Studio</Link><span className="text-xs font-bold uppercase tracking-[0.15em] text-[#2f5eeb]">Synthetic company lab</span></div></header>
    <main className="mx-auto max-w-6xl px-5 py-10"><section className="grid gap-6 rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-7 lg:grid-cols-[1.2fr_0.8fr]"><div><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Northstar Logistics</p><h1 className="mt-3 text-4xl font-semibold tracking-[-0.05em]">Test the integrations before you connect a real company.</h1><p className="mt-4 max-w-2xl text-base leading-7 text-[#5a6775]">A synthetic Slack incident, two Drive runbook revisions, and a merged GitHub PR pass through the real evidence ledger, Qwen Reality Memory reconciliation, and authenticated MCP decision path.</p><p className="mt-4 text-sm leading-6 text-[#657284]">Every record is marked <strong>fixture</strong>, browser-private, and expires with this sandbox. No Slack, GitHub, Drive, or external company is contacted.</p></div><div className="rounded-2xl border border-[#dbe3f2] bg-[#f8faff] p-5"><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">Test coverage</p><ul className="mt-3 space-y-2 text-sm leading-6 text-[#536170]"><li>• Signed Slack delivery + replay window</li><li>• GitHub webhook signature shape</li><li>• Drive revision supersedes prior memory</li><li>• Duplicate source idempotency</li><li>• Private-network web fetch rejection</li><li>• MCP release-safety decision</li></ul><button type="button" disabled={running} onClick={() => void runLab()} className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#17212b] px-4 py-3 text-sm font-semibold text-white disabled:opacity-60">{running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}{running ? "Running Northstar lab…" : "Run full integration test"}</button></div></section>
      <p className="mt-5 rounded-xl border border-[#d9d3c8] bg-[#fffcf7] px-4 py-3 text-sm text-[#536170]">{phase}</p>{error && <p className="mt-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</p>}
      {lab && <section className="mt-7 grid gap-5 lg:grid-cols-[1.15fr_0.85fr]"><article className="rounded-2xl border border-[#d9d3c8] bg-[#fffcf7] p-5"><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">Source trace</p><div className="mt-4 space-y-3">{lab.events.map((event) => <SourceRow key={event.ingestion_id} event={event} />)}</div></article><article className="rounded-2xl border border-[#d9d3c8] bg-[#fffcf7] p-5"><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">Integration guards</p><div className="mt-4 space-y-3">{lab.edge_checks.map((check) => <div key={check.id} className={`rounded-xl border p-3 ${check.passed ? "border-emerald-200 bg-emerald-50" : "border-rose-200 bg-rose-50"}`}><div className="flex items-center gap-2 text-sm font-semibold">{check.passed ? <Check className="h-4 w-4 text-emerald-700" /> : <CircleAlert className="h-4 w-4 text-rose-700" />}{check.label}</div><p className="mt-1 text-xs leading-5 text-[#536170]">{check.detail}</p></div>)}</div></article></section>}
      {brief && <section className="mt-7 rounded-2xl border border-[#d8d0c2] bg-[#fffcf7] p-5"><div className="flex flex-wrap items-center gap-3"><span className="rounded-full border border-rose-200 bg-rose-50 px-3 py-1 text-xs font-bold uppercase tracking-wide text-rose-800">{String(brief.verdict ?? "decision").replaceAll("_", " ")}</span><span className="text-xs font-medium text-[#657284]">Actual MCP DecisionBrief</span></div><h2 className="mt-4 text-2xl font-semibold tracking-tight">{String(brief.recommended_next_action ?? "No recommendation reported.")}</h2><p className="mt-3 text-sm text-[#536170]">Owner: {String(brief.owner ?? "Not reported")} · Human approval required</p>{logs.length > 0 && <div className="mt-5 grid gap-2 md:grid-cols-3">{logs.map((log) => <div key={log.step} className="rounded-xl border border-[#dbe3f2] bg-[#f8fafc] p-3"><p className="font-mono text-xs text-[#2148c7]">{log.step}</p><p className="mt-1 text-xs leading-5 text-[#536170]">{log.detail}</p></div>)}</div>}</section>}
    </main>
  </div>
}

function SourceRow({ event }: { event: SourceEvent }) {
  const Icon = sourceIcon(event.provider)
  return <div className="rounded-xl border border-[#e3e8f1] bg-[#fbfcfe] p-3"><div className="flex items-start gap-3"><span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#edf2fb] text-[#2f5eeb]"><Icon className="h-4 w-4" /></span><div><div className="flex flex-wrap items-center gap-2"><span className="text-sm font-semibold">{event.source_name}</span><span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase text-emerald-800">{event.stage.replaceAll("_", " ")}</span></div><p className="mt-1 text-xs leading-5 text-[#536170]">{event.excerpt}</p><p className="mt-2 font-mono text-[10px] text-[#738194]">Qwen {event.qwen_status} · memory {event.memory_id?.slice(0, 18) ?? "not created"}…</p></div></div></div>
}
