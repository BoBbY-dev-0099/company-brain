import { useEffect, useMemo, useRef, useState } from "react"
import { ArrowLeft, Check, ChevronDown, CircleAlert, Clock3, LoaderCircle, Sparkles, UserRound } from "lucide-react"
import { Link, useParams } from "react-router-dom"
import { createDemoSession, createWorkflowRun, getWorkflowTemplates, postWorkflowOutcome } from "../lib/api"
import type { DecisionBrief, WorkflowRun, WorkflowTemplate } from "../types/schema"

type StageStatus = "idle" | "active" | "complete" | "fallback"

type Stage = { id: "evidence" | "memory" | "sag" | "human"; title: string; description: string; status: StageStatus }

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms))

function asRun(value: unknown): WorkflowRun | null {
  if (!value || typeof value !== "object") return null
  const candidate = value as Record<string, unknown>
  const runId = typeof candidate.run_id === "string" ? candidate.run_id : typeof candidate.id === "string" ? candidate.id : null
  return runId ? ({ ...candidate, id: runId } as WorkflowRun) : null
}

function briefFor(run: WorkflowRun | null): DecisionBrief | null {
  return (run?.decision_brief ?? run?.brief ?? null) as DecisionBrief | null
}

function inferenceText(brief: DecisionBrief | null): string {
  const inference = brief?.inference
  if (typeof inference === "string") return inference
  if (Array.isArray(inference)) return inference.join(" ")
  return inference?.text ?? "The backend did not return an inference statement."
}

function qwenCompiled(brief: DecisionBrief | null): boolean {
  const inference = brief?.inference
  return Boolean(!Array.isArray(inference) && typeof inference === "object" && inference && (inference.is_model_generated || inference.generated_by === "qwen_compiler"))
}

function verdictTone(verdict?: string): string {
  if (verdict?.includes("suspend")) return "border-[#bc3f34] bg-[#fce9e6] text-[#96332b]"
  if (verdict?.includes("review")) return "border-[#c77a17] bg-[#fff0d6] text-[#9a590b]"
  return "border-[#2e7763] bg-[#e2f4ed] text-[#1d604f]"
}

function verdictLabel(verdict?: string): string {
  return (verdict ?? "not evaluated").replaceAll("_", " ")
}

function getTemplateId(template: WorkflowTemplate): string {
  return template.template_id ?? template.id ?? ""
}

function sourceName(evidence: Record<string, unknown>): string {
  return String(evidence.source_name ?? evidence.source_type ?? "Source")
}

export default function Simulation() {
  const { templateId = "" } = useParams()
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([])
  const [run, setRun] = useState<WorkflowRun | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState("I reviewed the decision and will take the assigned follow-up.")
  const [confirming, setConfirming] = useState(false)
  const [confirmed, setConfirmed] = useState(false)
  const sessionReady = useRef(false)
  const [stages, setStages] = useState<Stage[]>([
    { id: "evidence", title: "Evidence received", description: "Waiting to submit the source-backed fixture.", status: "idle" },
    { id: "memory", title: "Qwen memory", description: "Waiting for evidence.", status: "idle" },
    { id: "sag", title: "Live safety check", description: "Waiting for current context.", status: "idle" },
    { id: "human", title: "Human action", description: "Waiting for a governed recommendation.", status: "idle" },
  ])

  useEffect(() => { void getWorkflowTemplates().then((payload) => setTemplates(payload.templates)).catch(() => setError("Unable to load the server-defined workflow template.")) }, [])

  const template = useMemo(() => templates.find((item) => getTemplateId(item) === templateId) ?? null, [templateId, templates])
  const brief = briefFor(run)

  const setStage = (id: Stage["id"], status: StageStatus, description: string) => {
    setStages((current) => current.map((stage) => stage.id === id ? { ...stage, status, description } : stage))
  }

  const ensureSession = async () => {
    if (!sessionReady.current) {
      await createDemoSession()
      sessionReady.current = true
    }
  }

  const simulate = async () => {
    if (!template) return
    setRunning(true)
    setRun(null)
    setConfirmed(false)
    setError(null)
    setStages((current) => current.map((stage) => ({ ...stage, status: "idle", description: `Waiting for ${stage.title.toLowerCase()}.` })))
    const startedAt = Date.now()
    try {
      await ensureSession()
      setStage("evidence", "active", "Submitting the immutable source-backed fixture.")
      await sleep(650)
      setStage("memory", "active", "Qwen is compiling the submitted evidence into a memory candidate.")
      const response = await createWorkflowRun({ template_id: getTemplateId(template), fixture: true })
      const evaluated = asRun(response)
      if (!evaluated) throw new Error("The workflow engine did not return an auditable DecisionBrief.")
      const remainingMemoryTime = Math.max(0, 5000 - (Date.now() - startedAt))
      await sleep(remainingMemoryTime)
      const nextBrief = briefFor(evaluated)
      const qwenSucceeded = qwenCompiled(nextBrief)
      setStage("evidence", "complete", "Server accepted normalized evidence with source provenance.")
      setStage("memory", qwenSucceeded ? "complete" : "fallback", qwenSucceeded ? "Qwen compiled an ephemeral memory candidate for this sandbox run." : "Qwen was unavailable; the returned decision uses the stated deterministic fallback.")
      setStage("sag", "active", "Comparing the live context against the server-defined safety rule.")
      await sleep(1350)
      setStage("sag", "complete", `SAG returned: ${verdictLabel(nextBrief?.verdict)}.`)
      setStage("human", "active", "Assigning the accountable owner and recommended next action.")
      await sleep(1200)
      setStage("human", "complete", "The external action remains human-approved; nothing was executed.")
      setRun(evaluated)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to execute the sandbox simulation.")
    } finally {
      setRunning(false)
    }
  }

  const confirm = async () => {
    if (!run || !note.trim()) return
    setConfirming(true)
    setError(null)
    try {
      const response = await postWorkflowOutcome(run.id, { approved: true, outcome: "confirmed_effective", note: note.trim(), actor: "judge" })
      const updated = asRun(response)
      if (updated) setRun(updated)
      setConfirmed(true)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to record the sandbox outcome.")
    } finally {
      setConfirming(false)
    }
  }

  if (templates.length > 0 && !template) return <PageFrame><div className="rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-8">This simulation is not available.</div></PageFrame>

  return (
    <PageFrame>
      <div className="max-w-4xl">
        <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Sandbox simulation</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-[#17212b]">{template?.title ?? "Loading decision"}</h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-[#586575]">{template?.description ?? "Loading the server-defined decision template."}</p>
        <div className="mt-7 flex flex-wrap gap-3"><button type="button" onClick={() => void simulate()} disabled={running || !template} className="inline-flex items-center gap-2 rounded-xl bg-[#17212b] px-5 py-3 text-sm font-semibold text-[#fffdf7] transition hover:bg-[#293846] disabled:opacity-50">{running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}{running ? "Simulation running" : "Simulate decision"}</button><span className="self-center text-xs text-[#6b7280]">Real sandbox run · no external action</span></div>
      </div>

      {error && <div className="mt-7 rounded-2xl border border-[#bc3f34]/30 bg-[#fce9e6] p-4 text-sm text-[#96332b]">{error}</div>}

      <section className="mt-9 rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-5 shadow-[0_18px_55px_rgba(52,45,35,0.07)] md:p-7">
        <div className="grid gap-3 md:grid-cols-4">{stages.map((stage, index) => <StageCard key={stage.id} stage={stage} index={index} />)}</div>
      </section>

      {brief && <section className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <article className="rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-6 shadow-[0_18px_55px_rgba(52,45,35,0.07)]"><div className="flex flex-wrap items-center gap-3"><span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide ${verdictTone(brief.verdict)}`}>{verdictLabel(brief.verdict)}</span><span className="text-xs font-medium text-[#697585]">Backend decision brief</span></div><h2 className="mt-5 text-2xl font-semibold tracking-tight text-[#17212b]">{brief.recommended_next_action ?? "No action returned"}</h2><p className="mt-4 text-sm leading-6 text-[#536170]">{inferenceText(brief)}</p><div className="mt-6 grid gap-3 sm:grid-cols-2"><DecisionCell label="Owner" value={brief.owner ?? "Not reported"} /><DecisionCell label="Live check" value={String((brief.sag_trace as Record<string, unknown>)?.status ?? "not reported").replaceAll("_", " ")} /></div><AuditProof brief={brief} /></article>
        <article className="rounded-3xl border border-[#d7e4df] bg-[#edf8f4] p-6"><div className="flex items-center gap-2 text-[#1d604f]"><UserRound className="h-5 w-5" /><h2 className="font-semibold">Human confirmation</h2></div><p className="mt-3 text-sm leading-6 text-[#3a6559]">Record a sandbox outcome. This proves the approval boundary; it cannot execute an external company action.</p>{confirmed ? <div className="mt-6 flex items-center gap-2 rounded-xl border border-[#2e7763]/25 bg-white/60 px-4 py-3 text-sm font-medium text-[#1d604f]"><Check className="h-4 w-4" />Sandbox outcome recorded</div> : <><label className="mt-5 block text-xs font-bold uppercase tracking-[0.12em] text-[#537267]">Your decision note<textarea value={note} onChange={(event) => setNote(event.target.value)} className="mt-2 min-h-28 w-full rounded-xl border border-[#b9d4c9] bg-white px-3 py-3 text-sm font-normal leading-6 text-[#17212b] outline-none focus:border-[#2e7763]" /></label><button type="button" onClick={() => void confirm()} disabled={confirming || !note.trim()} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#1d604f] px-4 py-3 text-sm font-semibold text-white hover:bg-[#174d40] disabled:opacity-50">{confirming && <LoaderCircle className="h-4 w-4 animate-spin" />}Confirm sandbox action</button></>}</article>
      </section>}
    </PageFrame>
  )
}

function PageFrame({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-[#f5f1e8] text-[#17212b]"><header className="border-b border-[#d9d3c8] bg-[#f5f1e8]/90 backdrop-blur"><div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5"><Link to="/" className="inline-flex items-center gap-2 text-sm font-semibold text-[#17212b]"><ArrowLeft className="h-4 w-4" />All decisions</Link><Link to="/app/connect" className="text-sm font-medium text-[#39506a] hover:text-[#17212b]">Technical proof</Link></div></header><main className="mx-auto max-w-6xl px-5 py-11 md:py-16">{children}</main></div>
}

function StageCard({ stage, index }: { stage: Stage; index: number }) {
  const active = stage.status === "active"
  const complete = stage.status === "complete"
  const fallback = stage.status === "fallback"
  return <div className={`rounded-2xl border p-4 ${active ? "border-[#2f5eeb] bg-[#e7edff]" : complete ? "border-[#b7d8cc] bg-[#edf8f4]" : fallback ? "border-[#e5c991] bg-[#fff5e4]" : "border-[#e0d8cb] bg-[#faf7f0]"}`}><div className="flex items-center justify-between"><span className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#617085]">0{index + 1}</span>{active ? <LoaderCircle className="h-4 w-4 animate-spin text-[#2f5eeb]" /> : complete ? <Check className="h-4 w-4 text-[#1d604f]" /> : fallback ? <CircleAlert className="h-4 w-4 text-[#9a590b]" /> : <Clock3 className="h-4 w-4 text-[#99a2aa]" />}</div><h2 className="mt-5 font-semibold text-[#17212b]">{stage.title}</h2><p className="mt-2 text-xs leading-5 text-[#5c6876]">{stage.description}</p></div>
}

function DecisionCell({ label, value }: { label: string; value: string }) {
  return <div className="rounded-2xl border border-[#e0d8cb] bg-[#faf7f0] p-4"><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#75808c]">{label}</p><p className="mt-2 text-sm font-medium leading-5 text-[#17212b]">{value}</p></div>
}

function AuditProof({ brief }: { brief: DecisionBrief }) {
  const evidence = Array.isArray(brief.evidence) ? brief.evidence : []
  const memories = Array.isArray(brief.memory_refs) ? brief.memory_refs : []
  return <details className="group mt-6 rounded-2xl border border-[#ded7cb] bg-[#faf7f0]"><summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-4 text-sm font-semibold text-[#263544]">Audit proof<ChevronDown className="h-4 w-4 text-[#637080] transition group-open:rotate-180" /></summary><div className="space-y-5 border-t border-[#e5ddd0] p-4"><div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#75808c]">Evidence</p><div className="mt-2 space-y-2">{evidence.map((item, index) => { const record = item as unknown as Record<string, unknown>; return <div key={String(record.evidence_id ?? index)} className="rounded-xl bg-white p-3 text-xs leading-5 text-[#52606d]"><span className="font-semibold text-[#253443]">{sourceName(record)}</span> · {String(record.excerpt ?? "No excerpt")}</div> })}</div></div><div><p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[#75808c]">Memory and SAG</p><p className="mt-2 text-xs leading-5 text-[#52606d]">{inferenceText(brief)}</p>{memories.map((memory, index) => <p key={memory.memory_id ?? index} className="mt-2 rounded-xl bg-white p-3 text-xs leading-5 text-[#52606d]">{memory.summary}</p>)}<pre className="mt-3 overflow-auto rounded-xl bg-[#17212b] p-3 text-[11px] leading-5 text-[#d9e2ec]">{JSON.stringify(brief.sag_trace, null, 2)}</pre></div></div></details>
}

export { AuditProof, PageFrame, asRun, briefFor, inferenceText, verdictLabel, verdictTone }
