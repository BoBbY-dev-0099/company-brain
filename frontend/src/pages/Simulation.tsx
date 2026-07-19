import { useEffect, useState } from "react"
import { ArrowLeft, Check, ChevronDown, LoaderCircle, ShieldCheck, UserRound } from "lucide-react"
import { Link, useParams } from "react-router-dom"
import {
  createDemoMcpSession,
  createDemoSession,
  getWorkflowTemplates,
  postWorkflowOutcome,
  type WorkflowEvidenceInput,
} from "../lib/api"
import { evaluateWorkflowThroughMcp } from "../lib/mcp"
import type { DecisionBrief, WorkflowRun, WorkflowTemplate } from "../types/schema"

function templateId(template: WorkflowTemplate) { return template.template_id ?? template.id ?? "" }
function decisionBrief(run: WorkflowRun | null) { return (run?.decision_brief ?? run?.brief ?? null) as DecisionBrief | null }
function inferenceText(value: DecisionBrief["inference"]) { return typeof value === "string" ? value : Array.isArray(value) ? value.join(" ") : value?.text ?? "" }
function fixtureEvidence(template: WorkflowTemplate): WorkflowEvidenceInput[] {
  const fixture = template.demo_fixture as Record<string, unknown> | undefined
  return (Array.isArray(fixture?.evidence) ? fixture.evidence : []).map((item) => {
    const record = item as Record<string, unknown>
    return {
      source_type: String(record.source_type), source_name: String(record.source_name ?? "Company source"), external_id: String(record.external_id ?? "fixture"), occurred_at: String(record.occurred_at ?? new Date().toISOString()), excerpt: String(record.excerpt ?? "No excerpt"), metadata: (record.metadata as Record<string, unknown>) ?? {},
    }
  })
}
function fixtureContext(template: WorkflowTemplate) {
  const fixture = template.demo_fixture as Record<string, unknown> | undefined
  return (fixture?.live_context as Record<string, unknown>) ?? {}
}

export default function Simulation() {
  const { templateId: routeTemplate = "" } = useParams()
  const [template, setTemplate] = useState<WorkflowTemplate | null>(null)
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [running, setRunning] = useState(false)
  const [note, setNote] = useState("")
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getWorkflowTemplates().then((payload) => setTemplate(payload.templates.find((item) => templateId(item) === routeTemplate) ?? null)).catch(() => setError("Could not load this server-defined scenario."))
  }, [routeTemplate])

  const simulate = async () => {
    if (!template) return
    setRunning(true); setError(null); setRun(null)
    try {
      await createDemoSession()
      const session = await createDemoMcpSession()
      setRun(await evaluateWorkflowThroughMcp({ endpoint: session.mcp_endpoint, apiKey: session.api_key, templateId: templateId(template), evidence: fixtureEvidence(template), liveContext: fixtureContext(template), onLog: () => undefined }))
    } catch (caught) { setError(caught instanceof Error ? caught.message : "MCP simulation failed.") } finally { setRunning(false) }
  }

  const confirm = async () => {
    if (!run || !note.trim()) return
    try {
      await postWorkflowOutcome(run.run_id ?? run.id, { approved: true, outcome: "confirmed_effective", actor: "judge", note })
      setNote("Recorded")
    } catch { setError("Could not record the sandbox outcome.") }
  }
  const decision = decisionBrief(run)

  return <div className="min-h-screen bg-[#f5f1e8] text-[#17212b]">
    <header className="border-b border-[#d9d3c8]"><div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-5"><Link to="/" className="inline-flex items-center gap-2 text-sm font-semibold"><ArrowLeft className="h-4 w-4" />Reality Console</Link><Link to="/play/workflow" className="text-sm font-semibold text-[#2148c7]">Workflow Lab</Link></div></header>
    <main className="mx-auto max-w-5xl px-5 py-10">
      <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Reusable safety case</p>
      <h1 className="mt-3 text-4xl font-semibold tracking-[-0.05em]">{template?.title ?? "Loading scenario"}</h1>
      <p className="mt-4 max-w-2xl text-base leading-7 text-[#5a6775]">{template?.description}</p>
      <button onClick={() => void simulate()} disabled={!template || running} className="mt-7 inline-flex items-center gap-2 rounded-xl bg-[#17212b] px-5 py-3 text-sm font-semibold text-white disabled:opacity-50">{running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}{running ? "Calling MCP" : "Run safety check"}</button>
      {error && <p className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">{error}</p>}
      {decision && <section className="mt-8 grid gap-5 lg:grid-cols-[1fr_0.75fr]">
        <article className="rounded-3xl border border-[#d9d3c8] bg-[#fffcf7] p-6">
          <span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase ${decision.verdict === "suspended" ? "border-rose-200 bg-rose-50 text-rose-800" : "border-emerald-200 bg-emerald-50 text-emerald-800"}`}>{String(decision.verdict).replaceAll("_", " ")}</span>
          <h2 className="mt-5 text-2xl font-semibold">{decision.recommended_next_action}</h2>
          <p className="mt-4 text-sm leading-6 text-[#536170]">{inferenceText(decision.inference)}</p>
          <div className="mt-6 grid gap-3 sm:grid-cols-2"><Fact label="Owner" value={String(decision.owner)} /><Fact label="Evidence" value={`${decision.evidence?.length ?? 0} normalized records`} /></div>
          <details className="group mt-6 rounded-xl border border-[#e3ded4] bg-[#faf7f0]"><summary className="flex cursor-pointer items-center justify-between px-3 py-3 text-sm font-semibold">Audit proof <ChevronDown className="h-4 w-4 group-open:rotate-180" /></summary><pre className="overflow-auto border-t border-[#e3ded4] bg-[#17212b] p-3 text-[11px] leading-5 text-[#d9e2ec]">{JSON.stringify(decision, null, 2)}</pre></details>
        </article>
        <article className="rounded-3xl border border-[#d7e4df] bg-[#edf8f4] p-6"><div className="flex items-center gap-2 text-[#1d604f]"><UserRound className="h-5 w-5" /><h2 className="font-semibold">Human confirmation</h2></div><p className="mt-3 text-sm leading-6 text-[#3a6559]">This sandbox records the accountable follow-up only. It cannot execute a company action.</p><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="I reviewed the evidence and will take the assigned action." className="mt-5 min-h-32 w-full rounded-xl border border-[#b9d4c9] bg-white p-3 text-sm outline-none" /><button onClick={() => void confirm()} disabled={!note.trim()} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#1d604f] px-4 py-3 text-sm font-semibold text-white disabled:opacity-50"><Check className="h-4 w-4" />Confirm sandbox outcome</button></article>
      </section>}
    </main>
  </div>
}

function Fact({ label, value }: { label: string; value: string }) { return <div className="rounded-xl border border-[#e3ded4] bg-[#faf7f0] p-3"><p className="text-[10px] font-bold uppercase text-[#718096]">{label}</p><p className="mt-1 text-sm font-semibold">{value}</p></div> }
