import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import {
  AlertTriangle,
  Bot,
  ChevronRight,
  CircleDot,
  Clock3,
  Database,
  ExternalLink,
  FileSearch,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  ShieldAlert,
  UserRound,
  X,
} from "lucide-react"
import {
  createWorkflowRun,
  getDemoReadiness,
  getWorkflowSources,
  getWorkflowTemplates,
  postWorkflowOutcome,
} from "../lib/api"
import type {
  DecisionBrief,
  DecisionFact,
  DemoReadiness,
  EvidenceRecord,
  MissingEvidence,
  WorkflowOutcome,
  WorkflowRun,
  WorkflowSource,
  WorkflowTemplate,
} from "../types/schema"

type RunsByTemplate = Record<string, WorkflowRun>

const PIPELINE = ["Evidence", "What changed", "Memory", "Decision", "Human action", "Outcome"]

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function valueAsArray<T>(payload: unknown, key: string): T[] {
  if (Array.isArray(payload)) return payload as T[]
  if (!isRecord(payload)) return []
  const value = payload[key]
  return Array.isArray(value) ? (value as T[]) : []
}

function asWorkflowRun(payload: unknown): WorkflowRun | null {
  const candidate = isRecord(payload) && isRecord(payload.run) ? payload.run : payload
  if (!isRecord(candidate) || typeof candidate.template_id !== "string") {
    return null
  }
  const runId = typeof candidate.id === "string" ? candidate.id : candidate.run_id
  if (typeof runId !== "string") return null
  return { ...candidate, id: runId } as unknown as WorkflowRun
}

function asWorkflowOutcome(payload: unknown): WorkflowOutcome | null {
  if (!isRecord(payload) || isRecord(payload.run)) return null
  return payload as unknown as WorkflowOutcome
}

function getTemplateId(template: WorkflowTemplate): string {
  return template.template_id ?? template.id ?? ""
}

function getTemplateName(template: WorkflowTemplate): string {
  return (template.title ?? template.display_name ?? template.name ?? getTemplateId(template)) || "Untitled workflow"
}

function getEmbeddedRun(template: WorkflowTemplate): WorkflowRun | null {
  return asWorkflowRun(template.demo_preview ?? template.latest_run ?? template.demo_run ?? template.current_run ?? null)
}

function getBrief(run: WorkflowRun | null): DecisionBrief | null {
  return run?.decision_brief ?? run?.brief ?? null
}

function recommendedAction(run: WorkflowRun | null): string | undefined {
  const brief = getBrief(run)
  return run?.recommended_next_action ?? brief?.recommended_next_action ?? brief?.recommended_action
}

function decisionOwner(run: WorkflowRun | null, template: WorkflowTemplate): string | undefined {
  return run?.owner ?? getBrief(run)?.owner ?? template.owner_role
}

function asStringList(value: unknown): string[] {
  if (typeof value === "string") return [value]
  if (isRecord(value) && typeof value.text === "string") return [value.text]
  if (!Array.isArray(value)) return []
  return value.flatMap((item) => {
    if (typeof item === "string") return [item]
    return isRecord(item) && typeof item.text === "string" ? [item.text] : []
  })
}

function factText(value: string | DecisionFact): string {
  return typeof value === "string" ? value : value.statement
}

function missingEvidenceText(value: string | MissingEvidence): string {
  return typeof value === "string" ? value : `${value.field}: ${value.reason}`
}

function demoFixtureTitle(template: WorkflowTemplate): string | undefined {
  const fixture = template.demo_fixture
  return isRecord(fixture) && typeof fixture.title === "string" ? fixture.title : undefined
}

function formatTime(value: string | number | undefined): string {
  if (value == null) return "Not recorded"
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString()
}

function isFixture(template: WorkflowTemplate, run: WorkflowRun | null): boolean {
  const templateFixture = template.fixture ?? template.demo_fixture
  const fixtureMode = typeof templateFixture === "object" ? templateFixture.mode : undefined
  return templateFixture === true || Boolean(template.demo_fixture) || run?.fixture === true || run?.is_demo_fixture === true || run?.mode === "demo_fixture" || fixtureMode === "demo_fixture"
}

function verdictClass(value: string | undefined): string {
  const normalized = value?.toLowerCase() ?? ""
  if (/(suspend|block)/.test(normalized)) {
    return "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#fca5a5]"
  }
  if (/(review|hold|warn|escalat)/.test(normalized)) {
    return "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]"
  }
  if (/(clear|allow|approved|auto_execute|active)/.test(normalized)) {
    return "border-[#22c55e]/40 bg-[#22c55e]/10 text-[#4ade80]"
  }
  return "border-[#2a2a30] bg-[#17171a] text-[#a1a1aa]"
}

function detailStageStatus(run: WorkflowRun | null, stage: string): boolean {
  const brief = getBrief(run)
  if (!run) return false
  switch (stage) {
    case "Evidence":
      return Boolean(brief?.evidence?.length)
    case "What changed":
      return Boolean(brief?.what_changed || brief?.inference)
    case "Memory":
      return Boolean(brief?.memory_refs?.length)
    case "Decision":
      return Boolean(brief?.verdict || run.status)
    case "Human action":
      return Boolean(brief?.recommended_action || brief?.owner)
    case "Outcome":
      return Boolean(run.outcomes?.length)
    default:
      return false
  }
}

function formatEvidenceSource(evidence: EvidenceRecord): string {
  return evidence.label ?? evidence.source_name ?? evidence.source ?? evidence.source_type ?? "Unlabeled source"
}

function evidenceMode(evidence: EvidenceRecord): string | undefined {
  return evidence.mode ?? (evidence.is_demo_fixture || (typeof evidence.fixture === "boolean" && evidence.fixture) ? "demo_fixture" : undefined)
}

function workflowSourceId(source: WorkflowSource): string {
  return source.id ?? source.evidence_id ?? source.external_id ?? `${source.source_type ?? "source"}-${source.occurred_at ?? "unknown"}`
}

function workflowSourceLabel(source: WorkflowSource): string {
  return source.label ?? source.source_name ?? source.source_type ?? source.external_id ?? "Unlabeled source"
}

function workflowSourceStatus(source: WorkflowSource): string {
  if (source.status) return source.status
  const parts = [source.availability, source.freshness].filter((value): value is string => typeof value === "string" && value.length > 0)
  return parts.length > 0 ? parts.join(" · ") : "Status not reported"
}

function workflowSourceMode(source: WorkflowSource): string | undefined {
  return source.mode ?? (source.is_demo_fixture ? "demo_fixture" : undefined)
}

function workflowSourceTimestamp(source: WorkflowSource): string | number | undefined {
  return source.last_synced_at ?? source.occurred_at
}

function readinessValue(value: boolean | null | undefined, positive: string, negative: string): string {
  if (value == null) return "Not reported"
  return value ? positive : negative
}

function WorkflowCard({
  template,
  run,
  busy,
  onRun,
  onOpen,
}: {
  template: WorkflowTemplate
  run: WorkflowRun | null
  busy: boolean
  onRun: () => void
  onOpen: () => void
}) {
  const brief = getBrief(run)
  const templateId = getTemplateId(template)
  const verdict = brief?.verdict ?? run?.status
  const fact = brief?.facts?.[0]
  const sources = template.source_types ?? template.supported_source_types ?? []
  const fixtureTitle = demoFixtureTitle(template)

  return (
    <article className="rounded-xl border border-[#1f1f22] bg-[#111114] p-5 space-y-5 shadow-[0_8px_30px_rgba(0,0,0,0.15)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="font-semibold text-lg text-[#f4f4f5] truncate">{getTemplateName(template)}</h2>
            {isFixture(template, run) && (
              <span className="rounded border border-[#60a5fa]/40 bg-[#60a5fa]/10 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[#93c5fd]">
                Demo fixture
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-[#7c7c8a] line-clamp-2">
            {template.description ?? templateId}
          </p>
          {!run && fixtureTitle && <p className="mt-2 text-xs text-[#93c5fd]">Fixture ready: {fixtureTitle}</p>}
        </div>
        {template.version != null && (
          <span className="shrink-0 font-mono text-[10px] text-[#7c7c8a]">v{template.version}</span>
        )}
      </div>

      <div className="flex flex-wrap gap-1.5">
        {sources.map((source) => (
          <span key={source} className="rounded bg-[#050505] px-2 py-1 text-[10px] font-mono text-[#a1a1aa]">
            {source}
          </span>
        ))}
        {template.memory_type && (
          <span className="rounded bg-[#050505] px-2 py-1 text-[10px] font-mono text-[#a1a1aa]">
            memory: {template.memory_type}
          </span>
        )}
      </div>

      <div className="rounded-lg border border-[#1f1f22] bg-[#09090b] p-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[10px] uppercase tracking-[0.14em] text-[#7c7c8a]">Server decision</span>
          {verdict ? (
            <span className={`rounded border px-2 py-1 text-xs font-medium ${verdictClass(verdict)}`}>{verdict}</span>
          ) : (
            <span className="text-xs text-[#7c7c8a]">Not evaluated</span>
          )}
        </div>
        <p className="mt-2 text-sm text-[#e4e4e7] line-clamp-2">
          {recommendedAction(run) ?? "No backend recommendation has been recorded for this workflow."}
        </p>
        <div className="mt-2 flex items-center gap-1.5 text-xs text-[#7c7c8a]">
          <UserRound className="h-3.5 w-3.5" />
          {decisionOwner(run, template) ?? "Owner role not assigned"}
        </div>
      </div>

      {fact && (
        <div className="border-l-2 border-[#22c55e]/60 pl-3 text-xs leading-5 text-[#a1a1aa]">
          <span className="mr-1 uppercase tracking-wide text-[10px] text-[#7c7c8a]">Evidence</span>
          {factText(fact)}
        </div>
      )}

      <div className="grid grid-cols-3 gap-1 text-center">
        {PIPELINE.map((stage) => {
          const complete = detailStageStatus(run, stage)
          return (
            <div
              key={stage}
              className={`rounded px-1 py-1.5 text-[9px] leading-tight ${
                complete ? "bg-[#22c55e]/10 text-[#86efac]" : "bg-[#17171a] text-[#686871]"
              }`}
            >
              {stage}
            </div>
          )
        })}
      </div>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onRun}
          disabled={busy || !templateId}
          className="inline-flex items-center gap-1.5 rounded bg-[#22c55e] px-3 py-2 text-xs font-semibold text-[#050505] transition-colors hover:bg-[#4ade80] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
          {run ? "Re-run fixture" : "Run fixture"}
        </button>
        <button
          type="button"
          onClick={onOpen}
          className="inline-flex items-center gap-1 text-xs font-medium text-[#a1a1aa] hover:text-[#e4e4e7]"
        >
          Why this decision <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </article>
  )
}

function DetailSection({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="border-b border-[#1f1f22] py-4 last:border-b-0">
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-[#e4e4e7]">
        {icon}
        {title}
      </h3>
      {children}
    </section>
  )
}

function DetailDrawer({
  template,
  run,
  outcomeText,
  outcomeBusy,
  outcomeError,
  onOutcomeTextChange,
  onRecordOutcome,
  onClose,
}: {
  template: WorkflowTemplate
  run: WorkflowRun | null
  outcomeText: string
  outcomeBusy: boolean
  outcomeError: string | null
  onOutcomeTextChange: (value: string) => void
  onRecordOutcome: (approved: boolean) => void
  onClose: () => void
}) {
  const brief = getBrief(run)
  const evidence = brief?.evidence ?? []
  const facts = brief?.facts ?? []
  const inferences = asStringList(brief?.inference)
  const missingEvidence = brief?.missing_evidence ?? []
  const memoryRefs = brief?.memory_refs ?? []
  const outcomes = run?.outcomes ?? []
  const verdict = brief?.verdict ?? run?.status

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Decision evidence">
      <button type="button" onClick={onClose} className="absolute inset-0 bg-black/70" aria-label="Close decision drawer" />
      <aside className="relative h-full w-full max-w-2xl overflow-y-auto border-l border-[#2a2a30] bg-[#0b0b0d] p-5 shadow-2xl sm:p-7">
        <div className="sticky top-0 z-10 -mt-5 -mx-5 mb-5 flex items-start justify-between border-b border-[#1f1f22] bg-[#0b0b0d]/95 px-5 py-5 backdrop-blur sm:-mt-7 sm:-mx-7 sm:px-7 sm:py-6">
          <div className="pr-4">
            <div className="text-[10px] uppercase tracking-[0.16em] text-[#22c55e]">Why this decision?</div>
            <h2 className="mt-1 text-xl font-semibold">{getTemplateName(template)}</h2>
            <p className="mt-1 text-xs text-[#7c7c8a]">Server-provided evidence, Qwen inference, and deterministic SAG trace.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-[#7c7c8a] hover:bg-[#17171a] hover:text-[#e4e4e7]" aria-label="Close">
            <X className="h-5 w-5" />
          </button>
        </div>

        {!run ? (
          <div className="rounded-lg border border-dashed border-[#2a2a30] bg-[#111114] p-5 text-sm text-[#a1a1aa]">
            This template has no evaluated server run yet. Run its labeled fixture to inspect an auditable DecisionBrief.
          </div>
        ) : (
          <div className="space-y-0">
            <DetailSection title="Evidence" icon={<FileSearch className="h-4 w-4 text-[#22c55e]" />}>
              {evidence.length === 0 ? (
                <p className="text-sm text-[#7c7c8a]">No evidence records were returned.</p>
              ) : (
                <div className="space-y-3">
                  {evidence.map((item, index) => (
                    <div key={item.id ?? item.evidence_id ?? `${item.source_type ?? item.source}-${index}`} className="rounded border border-[#1f1f22] bg-[#111114] p-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="font-medium text-[#e4e4e7]">{formatEvidenceSource(item)}</span>
                        {evidenceMode(item) === "demo_fixture" && (
                          <span className="rounded border border-[#60a5fa]/40 bg-[#60a5fa]/10 px-1.5 py-0.5 text-[10px] text-[#93c5fd]">Demo fixture</span>
                        )}
                        {item.freshness && <span className="text-[#7c7c8a]">{item.freshness}</span>}
                      </div>
                      {item.excerpt && <p className="mt-2 text-sm leading-5 text-[#c4c4ca]">{item.excerpt}</p>}
                      <div className="mt-2 flex items-center gap-3 text-[10px] text-[#7c7c8a]">
                        <span>{formatTime(item.occurred_at ?? item.timestamp)}</span>
                        {item.url && (
                          <a href={item.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[#86efac] hover:underline">
                            Source <ExternalLink className="h-3 w-3" />
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </DetailSection>

            <DetailSection title="What changed" icon={<AlertTriangle className="h-4 w-4 text-[#fbbf24]" />}>
              {inferences.length === 0 ? (
                <p className="text-sm text-[#7c7c8a]">No server-provided change inference was returned.</p>
              ) : (
                <div className="space-y-2 text-sm leading-5 text-[#c4c4ca]">
                  <p className="text-[10px] uppercase tracking-wide text-[#7c7c8a]">Qwen inference (not a source fact)</p>
                  {inferences.map((inference, index) => <p key={`${inference}-${index}`}>{inference}</p>)}
                </div>
              )}
              {facts.length > 0 && (
                <div className="mt-3 rounded border border-[#22c55e]/20 bg-[#22c55e]/5 p-3">
                  <p className="mb-1 text-[10px] uppercase tracking-wide text-[#86efac]">Facts used</p>
                  <ul className="space-y-1 text-sm text-[#c4c4ca]">
                    {facts.map((fact, index) => <li key={`${factText(fact)}-${index}`}>• {factText(fact)}</li>)}
                  </ul>
                </div>
              )}
              {missingEvidence.length > 0 && (
                <div className="mt-3 rounded border border-[#f59e0b]/30 bg-[#f59e0b]/5 p-3">
                  <p className="mb-1 text-[10px] uppercase tracking-wide text-[#fbbf24]">Missing evidence</p>
                  <ul className="space-y-1 text-sm text-[#d4d4d8]">
                    {missingEvidence.map((item, index) => <li key={`${missingEvidenceText(item)}-${index}`}>• {missingEvidenceText(item)}</li>)}
                  </ul>
                </div>
              )}
            </DetailSection>

            <DetailSection title="Memory used" icon={<Database className="h-4 w-4 text-[#a78bfa]" />}>
              {memoryRefs.length === 0 ? (
                <p className="text-sm text-[#7c7c8a]">No prior memory references were returned.</p>
              ) : (
                <div className="space-y-2">
                  {memoryRefs.map((memory, index) => (
                    <div key={memory.id ?? memory.memory_id ?? memory.skill_id ?? index} className="rounded bg-[#111114] p-3 text-sm">
                      <div className="font-medium text-[#e4e4e7]">{memory.name ?? memory.skill_id ?? memory.memory_id ?? "Referenced memory"}</div>
                      {memory.summary && <p className="mt-1 text-[#a1a1aa]">{memory.summary}</p>}
                      {(memory.version != null || memory.source) && (
                        <p className="mt-1 font-mono text-[10px] text-[#7c7c8a]">
                          {memory.version != null ? `v${memory.version}` : ""}{memory.version != null && memory.source ? " · " : ""}{memory.source ?? ""}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </DetailSection>

            <DetailSection title="SAG decision" icon={<ShieldAlert className="h-4 w-4 text-[#fbbf24]" />}>
              <div className="flex flex-wrap items-center gap-2">
                {verdict ? <span className={`rounded border px-2 py-1 text-sm font-medium ${verdictClass(verdict)}`}>{verdict}</span> : <span className="text-sm text-[#7c7c8a]">No verdict returned</span>}
                {decisionOwner(run, template) && <span className="text-sm text-[#a1a1aa]">Owner: {decisionOwner(run, template)}</span>}
              </div>
              {brief?.sag_trace != null && (
                <pre className="mt-3 max-h-56 overflow-auto rounded bg-[#050505] p-3 text-[11px] leading-5 text-[#a1a1aa]">
                  {typeof brief.sag_trace === "string" ? brief.sag_trace : JSON.stringify(brief.sag_trace, null, 2)}
                </pre>
              )}
            </DetailSection>

            <DetailSection title="Human action" icon={<UserRound className="h-4 w-4 text-[#60a5fa]" />}>
              <p className="text-sm leading-5 text-[#d4d4d8]">{recommendedAction(run) ?? "No server-recommended action was returned."}</p>
              <p className="mt-2 text-xs text-[#7c7c8a]">Actions remain human-approved; recording an outcome does not execute an external action.</p>
              <textarea
                value={outcomeText}
                onChange={(event) => onOutcomeTextChange(event.target.value)}
                placeholder="Record the human decision or follow-up…"
                className="mt-3 min-h-20 w-full rounded border border-[#2a2a30] bg-[#111114] px-3 py-2 text-sm text-[#e4e4e7] outline-none placeholder:text-[#5a5a62] focus:border-[#22c55e]/70"
              />
              {outcomeError && <p className="mt-2 text-xs text-[#fca5a5]">{outcomeError}</p>}
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" disabled={outcomeBusy} onClick={() => onRecordOutcome(true)} className="rounded bg-[#22c55e] px-3 py-2 text-xs font-semibold text-[#050505] hover:bg-[#4ade80] disabled:opacity-50">
                  {outcomeBusy ? "Recording…" : "Confirm human action"}
                </button>
                <button type="button" disabled={outcomeBusy} onClick={() => onRecordOutcome(false)} className="rounded border border-[#f59e0b]/50 px-3 py-2 text-xs font-semibold text-[#fbbf24] hover:bg-[#f59e0b]/10 disabled:opacity-50">
                  Keep in review
                </button>
              </div>
            </DetailSection>

            <DetailSection title="Outcome history" icon={<Clock3 className="h-4 w-4 text-[#7c7c8a]" />}>
              {outcomes.length === 0 ? (
                <p className="text-sm text-[#7c7c8a]">No human outcome has been recorded.</p>
              ) : (
                <div className="space-y-2">
                  {outcomes.map((outcome, index) => (
                    <div key={outcome.id ?? index} className="rounded bg-[#111114] p-3 text-sm">
                      <div className="flex items-center justify-between gap-3">
                        <span className={outcome.approved ? "text-[#86efac]" : "text-[#fbbf24]"}>{outcome.approved ? "Human-approved" : "Kept in review"}</span>
                        <span className="text-[10px] text-[#7c7c8a]">{formatTime(outcome.recorded_at ?? outcome.created_at ?? outcome.timestamp)}</span>
                      </div>
                      {outcome.outcome && <p className="mt-1 text-[#c4c4ca]">{outcome.outcome}</p>}
                      {outcome.actor && <p className="mt-1 text-[10px] font-mono text-[#7c7c8a]">{outcome.actor}</p>}
                    </div>
                  ))}
                </div>
              )}
            </DetailSection>
          </div>
        )}
      </aside>
    </div>
  )
}

function LoadingCard() {
  return (
    <div className="animate-pulse rounded-xl border border-[#1f1f22] bg-[#111114] p-5 space-y-4">
      <div className="h-5 w-2/3 rounded bg-[#222227]" />
      <div className="h-3 w-full rounded bg-[#1b1b20]" />
      <div className="h-24 rounded bg-[#17171a]" />
      <div className="grid grid-cols-3 gap-1">
        {PIPELINE.map((item) => <div key={item} className="h-7 rounded bg-[#17171a]" />)}
      </div>
    </div>
  )
}

export default function Operations() {
  const [templates, setTemplates] = useState<WorkflowTemplate[]>([])
  const [runs, setRuns] = useState<RunsByTemplate>({})
  const [sources, setSources] = useState<WorkflowSource[]>([])
  const [readiness, setReadiness] = useState<DemoReadiness | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [templatesError, setTemplatesError] = useState<string | null>(null)
  const [sourcesError, setSourcesError] = useState<string | null>(null)
  const [readinessError, setReadinessError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [runningTemplateId, setRunningTemplateId] = useState<string | null>(null)
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [outcomeText, setOutcomeText] = useState("")
  const [outcomeBusy, setOutcomeBusy] = useState(false)
  const [outcomeError, setOutcomeError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setRefreshing(true)
    setActionError(null)
    const [templateResult, sourceResult, readinessResult] = await Promise.allSettled([
      getWorkflowTemplates(),
      getWorkflowSources(),
      getDemoReadiness(),
    ])

    if (templateResult.status === "fulfilled") {
      const nextTemplates = valueAsArray<WorkflowTemplate>(templateResult.value, "templates")
      setTemplates(nextTemplates)
      setRuns((previous) => {
        const embedded = nextTemplates.reduce<RunsByTemplate>((accumulator, template) => {
          const templateId = getTemplateId(template)
          const run = getEmbeddedRun(template)
          if (templateId && run) accumulator[templateId] = run
          return accumulator
        }, {})
        return { ...previous, ...embedded }
      })
      setSelectedTemplateId((current) => current ?? getTemplateId(nextTemplates[0] ?? {}))
      setTemplatesError(null)
    } else {
      setTemplates([])
      setTemplatesError("The Operations API is unavailable. No client-side verdict has been inferred.")
    }

    if (sourceResult.status === "fulfilled") {
      setSources(valueAsArray<WorkflowSource>(sourceResult.value, "sources"))
      setSourcesError(null)
    } else {
      setSources([])
      setSourcesError("Source status is unavailable.")
    }

    if (readinessResult.status === "fulfilled") {
      const payload = readinessResult.value
      setReadiness(isRecord(payload) && isRecord(payload.readiness) ? (payload.readiness as DemoReadiness) : payload)
      setReadinessError(null)
    } else {
      setReadiness(null)
      setReadinessError("Deployment readiness has not been reported.")
    }

    setLoading(false)
    setRefreshing(false)
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const selectedTemplate = useMemo(
    () => templates.find((template) => getTemplateId(template) === selectedTemplateId) ?? null,
    [selectedTemplateId, templates],
  )
  const selectedRun = selectedTemplate ? runs[getTemplateId(selectedTemplate)] ?? getEmbeddedRun(selectedTemplate) : null

  const openDrawer = (templateId: string) => {
    setSelectedTemplateId(templateId)
    setOutcomeText("")
    setOutcomeError(null)
    setDrawerOpen(true)
  }

  const runFixture = async (template: WorkflowTemplate) => {
    const templateId = getTemplateId(template)
    if (!templateId) return
    setActionError(null)
    setRunningTemplateId(templateId)
    try {
      const response = await createWorkflowRun({ template_id: templateId, fixture: true })
      const run = asWorkflowRun(response)
      if (!run) throw new Error("The server did not return an auditable workflow run.")
      setRuns((current) => ({ ...current, [templateId]: run }))
      setSelectedTemplateId(templateId)
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Unable to run the labeled fixture.")
    } finally {
      setRunningTemplateId(null)
    }
  }

  const recordOutcome = async (approved: boolean) => {
    if (!selectedRun) return
    const outcome = outcomeText.trim()
    if (!outcome) {
      setOutcomeError("Add a short human decision before recording an outcome.")
      return
    }
    setOutcomeError(null)
    setOutcomeBusy(true)
    try {
      const response = await postWorkflowOutcome(selectedRun.id, {
        approved,
        outcome: approved ? "confirmed_effective" : "needs_review",
        note: outcome,
        actor: "judge",
      })
      const returnedRun = asWorkflowRun(response)
      if (returnedRun) {
        setRuns((current) => ({ ...current, [returnedRun.template_id]: returnedRun }))
      } else {
        const returnedOutcome = asWorkflowOutcome(response)
        if (returnedOutcome) {
          setRuns((current) => ({
            ...current,
            [selectedRun.template_id]: {
              ...selectedRun,
              outcomes: [...(selectedRun.outcomes ?? []), returnedOutcome],
            },
          }))
        }
      }
      setOutcomeText("")
    } catch (error) {
      setOutcomeError(error instanceof Error ? error.message : "Unable to record the human outcome.")
    } finally {
      setOutcomeBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 pb-10">
      <section className="rounded-xl border border-[#22c55e]/25 bg-gradient-to-br from-[#22c55e]/10 via-[#111114] to-[#111114] p-5 md:p-7">
        <div className="flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[#22c55e]/30 bg-[#22c55e]/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.15em] text-[#86efac]">
              <CircleDot className="h-3 w-3" /> Server-owned workflows
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-[#fafafa]">Operational Risk Inbox</h1>
            <p className="mt-2 text-sm leading-6 text-[#b4b4bb] md:text-base">
              Make company memory useful when reality changes: source-backed evidence is compiled into memory, checked against live context, and routed to a human owner before action.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            disabled={refreshing}
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded border border-[#2a2a30] bg-[#111114] px-3 py-2 text-sm text-[#e4e4e7] hover:border-[#22c55e]/50 disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            Refresh server state
          </button>
        </div>
      </section>

      {readiness ? (
        <section className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-[#1f1f22] bg-[#1f1f22] md:grid-cols-5">
          <ReadinessItem label="Build" value={readiness.build_sha ?? "Not reported"} mono />
          <ReadinessItem label="Qwen" value={readinessValue(readiness.qwen_configured, "Configured", "Not configured")} />
          <ReadinessItem label="Embeddings" value={readinessValue(readiness.embedding_healthy, "Healthy", "Unavailable")} />
          <ReadinessItem label="Scenario" value={readiness.scenario_version ?? "Not reported"} mono />
          <ReadinessItem label="Canonical memory" value={readiness.canonical_skill_count != null ? `${readiness.canonical_skill_count} skills` : "Not reported"} />
        </section>
      ) : (
        <p className="rounded border border-[#1f1f22] bg-[#111114] px-4 py-3 text-xs text-[#7c7c8a]">
          {readinessError ?? "Loading deployment readiness…"}
        </p>
      )}

      <section className="rounded-xl border border-[#1f1f22] bg-[#111114] p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold"><Database className="h-4 w-4 text-[#22c55e]" /> Evidence sources</h2>
            <p className="mt-1 text-xs text-[#7c7c8a]">Fixture data is visibly labeled; source availability is reported by the server.</p>
          </div>
          {sources.length > 0 && <span className="text-xs text-[#7c7c8a]">{sources.length} connected</span>}
        </div>
        {sourcesError ? (
          <p className="mt-3 text-sm text-[#7c7c8a]">{sourcesError}</p>
        ) : sources.length === 0 ? (
          <p className="mt-3 text-sm text-[#7c7c8a]">No source records have been reported.</p>
        ) : (
          <div className="mt-3 flex flex-wrap gap-2">
            {sources.map((source) => {
              const sourceTimestamp = workflowSourceTimestamp(source)
              return (
              <div key={workflowSourceId(source)} className="rounded border border-[#2a2a30] bg-[#09090b] px-3 py-2 text-xs">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-[#e4e4e7]">{workflowSourceLabel(source)}</span>
                  {workflowSourceMode(source) === "demo_fixture" && <span className="text-[10px] text-[#93c5fd]">DEMO FIXTURE</span>}
                </div>
                <div className="mt-1 text-[#7c7c8a]">{workflowSourceStatus(source)}{sourceTimestamp ? ` · ${formatTime(sourceTimestamp)}` : ""}</div>
              </div>
              )
            })}
          </div>
        )}
      </section>

      <section>
        <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-xl font-semibold">Priority workflows</h2>
            <p className="mt-1 text-sm text-[#7c7c8a]">Each card is one reusable template, not a separate demo agent.</p>
          </div>
          <span className="text-xs text-[#7c7c8a]">Evidence → memory → live context → human action</span>
        </div>

        {actionError && (
          <div className="mb-4 flex items-start gap-2 rounded border border-[#ef4444]/30 bg-[#ef4444]/5 px-3 py-2 text-sm text-[#fca5a5]">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {actionError}
          </div>
        )}

        {loading ? (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3"><LoadingCard /><LoadingCard /><LoadingCard /></div>
        ) : templatesError ? (
          <div className="rounded-xl border border-dashed border-[#2a2a30] bg-[#111114] px-5 py-10 text-center">
            <ShieldAlert className="mx-auto h-7 w-7 text-[#7c7c8a]" />
            <h3 className="mt-3 font-medium">Operational inbox unavailable</h3>
            <p className="mx-auto mt-1 max-w-lg text-sm text-[#7c7c8a]">{templatesError}</p>
            <button type="button" onClick={() => void refresh()} className="mt-4 text-sm font-medium text-[#86efac] hover:underline">Retry server connection</button>
          </div>
        ) : templates.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[#2a2a30] bg-[#111114] px-5 py-10 text-center">
            <Bot className="mx-auto h-7 w-7 text-[#7c7c8a]" />
            <h3 className="mt-3 font-medium">No workflow templates reported</h3>
            <p className="mx-auto mt-1 max-w-lg text-sm text-[#7c7c8a]">The API is available, but it has not returned any server-owned workflow templates yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            {templates.map((template) => {
              const templateId = getTemplateId(template)
              const run = runs[templateId] ?? getEmbeddedRun(template)
              return (
                <WorkflowCard
                  key={templateId || getTemplateName(template)}
                  template={template}
                  run={run}
                  busy={runningTemplateId === templateId}
                  onRun={() => void runFixture(template)}
                  onOpen={() => openDrawer(templateId)}
                />
              )
            })}
          </div>
        )}
      </section>

      <section className="rounded-lg border border-[#60a5fa]/25 bg-[#60a5fa]/5 px-4 py-3 text-xs leading-5 text-[#b8c7e5]">
        <span className="font-semibold text-[#bfdbfe]">Governance boundary: </span>
        Runs are auditable decision records. Fixture runs and demo clicks do not train canonical memory; only a human-confirmed outcome is eligible for later reinforcement.
      </section>

      {drawerOpen && selectedTemplate && (
        <DetailDrawer
          template={selectedTemplate}
          run={selectedRun}
          outcomeText={outcomeText}
          outcomeBusy={outcomeBusy}
          outcomeError={outcomeError}
          onOutcomeTextChange={setOutcomeText}
          onRecordOutcome={(approved) => void recordOutcome(approved)}
          onClose={() => setDrawerOpen(false)}
        />
      )}
    </div>
  )
}

function ReadinessItem({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0 bg-[#111114] px-3 py-3">
      <div className="text-[10px] uppercase tracking-wide text-[#7c7c8a]">{label}</div>
      <div className={`mt-1 truncate text-xs text-[#e4e4e7] ${mono ? "font-mono" : ""}`}>{value}</div>
    </div>
  )
}
