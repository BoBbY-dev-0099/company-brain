import { useEffect, useMemo, useRef, useState } from "react"
import { Check, LoaderCircle, RotateCcw, ShieldCheck } from "lucide-react"
import { createDemoSession, createWorkflowRun, getWorkflowTemplates, postWorkflowOutcome, type WorkflowEvidenceInput } from "../lib/api"
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

  const chooseTemplate = (nextId: string) => {
    const next = templates.find((template) => templateId(template) === nextId)
    if (!next) return
    const sample = readFixture(next)
    setSelectedId(nextId)
    setEvidence(sample.evidence)
    setLiveContext(sample.live)
    setRun(null)
    setConfirmed(false)
    setError(null)
  }

  const reset = () => selected && chooseTemplate(templateId(selected))

  const evaluate = async () => {
    if (!selected) return
    setRunning(true)
    setRun(null)
    setConfirmed(false)
    setError(null)
    try {
      if (!sessionReady.current) {
        await createDemoSession()
        sessionReady.current = true
      }
      const context = Object.fromEntries(liveSchema(selected).map((field) => {
        const value = liveContext[field.name]
        return [field.name, field.value_type === "number" ? Number(value) : value]
      }))
      const response = await createWorkflowRun({
        template_id: templateId(selected),
        evidence: evidence.map(({ key: _key, ...item }) => item),
        live_context: context,
      })
      const evaluated = asRun(response)
      if (!evaluated) throw new Error("The workflow engine did not return an auditable DecisionBrief.")
      setRun(evaluated)
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
    <div className="max-w-4xl"><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Guided workflow playground</p><h1 className="mt-3 text-4xl font-semibold tracking-[-0.04em] text-[#17212b]">Add Company Brain to a decision.</h1><p className="mt-3 max-w-2xl text-base leading-7 text-[#586575]">Use safe sample evidence and live context. This is a private, temporary sandbox—not a live connector or credential form.</p></div>
    {error && <div className="mt-7 rounded-2xl border border-[#bc3f34]/30 bg-[#fce9e6] p-4 text-sm text-[#96332b]">{error}</div>}
    <section className="mt-8 rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-5 shadow-[0_18px_55px_rgba(52,45,35,0.07)] md:p-7">
      {loading || !selected ? <div className="h-72 animate-pulse rounded-2xl bg-[#f3eee4]" /> : <>
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end"><label className="block max-w-sm text-xs font-bold uppercase tracking-[0.13em] text-[#627083]">Decision template<select value={selectedId} onChange={(event) => chooseTemplate(event.target.value)} className="mt-2 w-full rounded-xl border border-[#d9d2c6] bg-white px-3 py-3 text-sm font-medium normal-case tracking-normal text-[#17212b] outline-none focus:border-[#2f5eeb]">{templates.map((template) => <option key={templateId(template)} value={templateId(template)}>{template.title}</option>)}</select></label><button type="button" onClick={reset} className="inline-flex items-center gap-2 text-sm font-semibold text-[#39506a] hover:text-[#17212b]"><RotateCcw className="h-4 w-4" />Reset sample</button></div>
        <div className="mt-8 grid gap-7 lg:grid-cols-[1.15fr_0.85fr]"><div><SectionHeading label="1" title="Evidence" subtitle="Edit the source excerpts. No credentials are accepted." /> <div className="mt-4 space-y-3">{evidence.map((item, index) => <article key={item.key} className="rounded-2xl border border-[#e1d9cd] bg-[#faf7f0] p-4"><p className="text-[10px] font-bold uppercase tracking-[0.13em] text-[#667488]">{item.source_name ?? item.source_type}</p><label className="mt-3 block text-xs font-semibold text-[#263544]">Reference<input value={item.external_id ?? ""} onChange={(event) => setEvidence((current) => current.map((entry, position) => position === index ? { ...entry, external_id: event.target.value } : entry))} className="mt-1.5 w-full rounded-lg border border-[#d9d2c6] bg-white px-3 py-2 text-sm font-normal outline-none focus:border-[#2f5eeb]" /></label><label className="mt-3 block text-xs font-semibold text-[#263544]">What changed<textarea value={item.excerpt} onChange={(event) => setEvidence((current) => current.map((entry, position) => position === index ? { ...entry, excerpt: event.target.value } : entry))} className="mt-1.5 min-h-20 w-full rounded-lg border border-[#d9d2c6] bg-white px-3 py-2 text-sm font-normal leading-6 outline-none focus:border-[#2f5eeb]" /></label></article>)}</div></div>
          <div><SectionHeading label="2" title="Live context" subtitle="The deterministic safety rule evaluates these current values." /> <div className="mt-4 space-y-3">{liveSchema(selected).map((field) => <label key={field.name} className="block rounded-2xl border border-[#e1d9cd] bg-[#faf7f0] p-4"><span className="text-sm font-semibold text-[#263544]">{field.name.replaceAll("_", " ")}</span><span className="mt-1 block text-xs leading-5 text-[#6b7784]">{field.description}</span>{field.value_type === "boolean" ? <select value={String(liveContext[field.name])} onChange={(event) => setLiveContext((current) => ({ ...current, [field.name]: event.target.value === "true" }))} className="mt-3 w-full rounded-lg border border-[#d9d2c6] bg-white px-3 py-2 text-sm outline-none focus:border-[#2f5eeb]"><option value="true">True</option><option value="false">False</option></select> : <input type="number" value={String(liveContext[field.name] ?? "")} onChange={(event) => setLiveContext((current) => ({ ...current, [field.name]: event.target.value }))} className="mt-3 w-full rounded-lg border border-[#d9d2c6] bg-white px-3 py-2 text-sm outline-none focus:border-[#2f5eeb]" />}</label>)}</div></div></div>
        <div className="mt-8 flex flex-wrap items-center gap-3 border-t border-[#e5ddd0] pt-6"><button type="button" onClick={() => void evaluate()} disabled={running} className="inline-flex items-center gap-2 rounded-xl bg-[#17212b] px-5 py-3 text-sm font-semibold text-[#fffdf7] hover:bg-[#293846] disabled:opacity-50">{running ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}{running ? "Evaluating with Qwen + SAG" : "Evaluate with Company Brain"}</button><span className="text-xs text-[#6b7280]">Private sandbox · expires after 60 minutes · never changes canonical memory</span></div>
      </>}
    </section>
    {brief && <DecisionTrace run={run} brief={brief} />}
    {brief && <section className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]"><article className="rounded-3xl border border-[#d8d0c2] bg-[#fffcf7] p-6 shadow-[0_18px_55px_rgba(52,45,35,0.07)]"><span className={`rounded-full border px-3 py-1 text-xs font-bold uppercase tracking-wide ${verdictTone(brief.verdict)}`}>{verdictLabel(brief.verdict)}</span><h2 className="mt-5 text-2xl font-semibold tracking-tight text-[#17212b]">{brief.recommended_next_action ?? "No action returned"}</h2><p className="mt-4 text-sm leading-6 text-[#536170]">{inferenceText(brief)}</p><AuditProof brief={brief} /></article><article className="rounded-3xl border border-[#d7e4df] bg-[#edf8f4] p-6"><h2 className="font-semibold text-[#1d604f]">Human confirmation</h2><p className="mt-3 text-sm leading-6 text-[#3a6559]">The owner is <strong>{brief.owner ?? "not reported"}</strong>. This confirmation records only a sandbox outcome.</p>{confirmed ? <div className="mt-6 flex items-center gap-2 rounded-xl border border-[#2e7763]/25 bg-white/60 px-4 py-3 text-sm font-medium text-[#1d604f]"><Check className="h-4 w-4" />Sandbox outcome recorded</div> : <><textarea value={note} onChange={(event) => setNote(event.target.value)} className="mt-5 min-h-28 w-full rounded-xl border border-[#b9d4c9] bg-white px-3 py-3 text-sm leading-6 text-[#17212b] outline-none focus:border-[#2e7763]" /><button type="button" onClick={() => void confirm()} disabled={confirming || !note.trim()} className="mt-4 inline-flex items-center gap-2 rounded-xl bg-[#1d604f] px-4 py-3 text-sm font-semibold text-white hover:bg-[#174d40] disabled:opacity-50">{confirming && <LoaderCircle className="h-4 w-4 animate-spin" />}Confirm sandbox action</button></>}</article></section>}
  </PageFrame>
}

function SectionHeading({ label, title, subtitle }: { label: string; title: string; subtitle: string }) {
  return <div><span className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-[#e7edff] text-[10px] font-bold text-[#2148c7]">{label}</span><h2 className="mt-3 text-lg font-semibold text-[#17212b]">{title}</h2><p className="mt-1 text-sm leading-6 text-[#627083]">{subtitle}</p></div>
}
