import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import {
  AlertTriangle,
  Bot,
  ChevronDown,
  ChevronRight,
  CircleDot,
  Clock3,
  Database,
  ExternalLink,
  Fingerprint,
  LoaderCircle,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
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
  if (!isRecord(candidate) || typeof candidate.template_id !== "string") return null
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

function templateText(template: WorkflowTemplate, key: string): string | undefined {
  const value = template[key]
  return typeof value === "string" && value.trim() ? value : undefined
}

function recommendedAction(run: WorkflowRun | null, template?: WorkflowTemplate): string | undefined {
  const brief = getBrief(run)
  return run?.recommended_next_action ?? brief?.recommended_next_action ?? brief?.recommended_action ?? (template ? templateText(template, "recommended_action") : undefined)
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

function formatTime(value: string | number | undefined): string {
  if (value == null) return "Not recorded"
  const date = new Date(value)
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleString()
}

function humanize(value: string | undefined): string {
  if (!value) return "Not reported"
  return value.replaceAll("_", " ")
}

function isFixture(template: WorkflowTemplate, run: WorkflowRun | null): boolean {
  const templateFixture = template.fixture ?? template.demo_fixture
  const fixtureMode = isRecord(templateFixture) ? templateFixture.mode : undefined
  return templateFixture === true || Boolean(template.demo_fixture) || run?.fixture === true || run?.is_demo_fixture === true || run?.mode === "demo_fixture" || fixtureMode === "demo_fixture"
}

function isCanonicalPreview(run: WorkflowRun | null): boolean {
  if (!run?.is_demo_fixture) return false
  const orgId = run.org_id
  return typeof orgId === "string" && orgId === "judge-demo-v1"
}

function verdictClass(value: string | undefined): string {
  const normalized = value?.toLowerCase() ?? ""
  if (/(suspend|block)/.test(normalized)) return "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#fca5a5]"
  if (/(review|hold|warn|escalat)/.test(normalized)) return "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]"
  if (/(clear|allow|approved|auto_execute|active|proceed)/.test(normalized)) return "border-[#22c55e]/40 bg-[#22c55e]/10 text-[#86efac]"
  return "border-[#2a2a30] bg-[#17171a] text-[#a1a1aa]"
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
  return parts.length > 0 ? parts.join(" / ") : "Status not reported"
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

function changedStatements(run: WorkflowRun | null): string[] {
  const brief = getBrief(run)
  return asStringList(brief?.what_changed).concat(asStringList(brief?.inference))
}

function blockerText(run: WorkflowRun | null, template: WorkflowTemplate): string {
  const brief = getBrief(run)
  const changed = changedStatements(run)[0]
  if (changed) return changed
  const fact = brief?.facts?.[0]
  if (fact) return factText(fact)
  return template.description ?? "The server has not returned an evidence-backed blocker yet."
}

function freshnessText(run: WorkflowRun | null): string {
  const freshness = (getBrief(run)?.evidence ?? [])
    .map((item) => item.freshness)
    .filter((value): value is string => typeof value === "string" && value.length > 0)
  const distinct = [...new Set(freshness)]
  return distinct.length > 0 ? `Evidence freshness: ${distinct.map(humanize).join(" / ")}` : "Evidence freshness not reported"
}

function sagExplanation(verdict: string | undefined): string {
  const normalized = verdict?.toLowerCase() ?? ""
  if (/(suspend|block)/.test(normalized)) {
    return "The live condition no longer meets the safety rule stored with this memory, so the old path is suspended."
  }
  if (/(review|hold|warn|escalat)/.test(normalized)) {
    return "The safety rule cannot support an action until the required evidence is available and current."
  }
  if (/(proceed|clear|allow|approved|active)/.test(normalized)) {
    return "The live conditions satisfy the deterministic safety rule, but a human still owns the final action."
  }
  return "The backend did not return a recognizable safety verdict."
}

function jsonText(value: unknown): string {
  if (typeof value === "string") return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return "Unable to render the server trace."
  }
}

function Freshness({ run }: { run: WorkflowRun | null }) {
  return (
    <p className="flex items-center gap-1.5 text-xs text-[#7c7c8a]">
      <Clock3 className="h-3.5 w-3.5" />
      {freshnessText(run)}
    </p>
  )
}

function VerdictBadge({ value }: { value: string | undefined }) {
  return value ? (
    <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${verdictClass(value)}`}>{humanize(value)}</span>
  ) : (
    <span className="rounded-full border border-[#2a2a30] bg-[#17171a] px-2.5 py-1 text-xs text-[#7c7c8a]">Not evaluated</span>
  )
}

function FlagshipCard({
  template,
  run,
  busy,
  onOpen,
  onRun,
}: {
  template: WorkflowTemplate
  run: WorkflowRun | null
  busy: boolean
  onOpen: () => void
  onRun: () => void
}) {
  const verdict = getBrief(run)?.verdict ?? run?.status
  const owner = decisionOwner(run, template) ?? "Owner role not assigned"
  const action = recommendedAction(run, template) ?? "No backend recommendation has been recorded."

  return (
    <article className="overflow-hidden rounded-2xl border border-[#22c55e]/30 bg-gradient-to-br from-[#14321f] via-[#111114] to-[#111114] shadow-[0_18px_60px_rgba(0,0,0,0.3)]">
      <div className="grid gap-0 lg:grid-cols-[1.35fr_0.85fr]">
        <div className="p-5 md:p-7">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="rounded-full border border-[#22c55e]/30 bg-[#22c55e]/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#86efac]">
                  Flagship decision
                </span>
                {isFixture(template, run) && <span className="text-[10px] font-medium uppercase tracking-wide text-[#93c5fd]">Judge fixture</span>}
              </div>
              <h2 className="text-2xl font-semibold tracking-tight text-[#fafafa]">{getTemplateName(template)}</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-[#b4b4bb]">{template.description}</p>
            </div>
            <VerdictBadge value={verdict} />
          </div>

          <div className="mt-6 rounded-xl border border-[#ef4444]/25 bg-[#050505]/55 p-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#fca5a5]">What stopped</p>
            <p className="mt-2 text-base leading-6 text-[#f4f4f5]">{blockerText(run, template)}</p>
          </div>

          <Freshness run={run} />

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={onOpen}
              className="inline-flex items-center gap-2 rounded bg-[#22c55e] px-4 py-2.5 text-sm font-semibold text-[#050505] transition-colors hover:bg-[#4ade80]"
            >
              Review decision <ChevronRight className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={onRun}
              disabled={busy || !getTemplateId(template)}
              className="inline-flex items-center gap-2 rounded border border-[#2a2a30] bg-[#111114] px-3 py-2.5 text-xs font-semibold text-[#e4e4e7] hover:border-[#60a5fa]/60 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              Replay in sandbox
            </button>
          </div>
        </div>

        <div className="border-t border-[#1f1f22] bg-[#09090b]/60 p-5 lg:border-l lg:border-t-0 lg:p-7">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7c7c8a]">Human handoff</p>
          <div className="mt-4 space-y-5">
            <div>
              <div className="flex items-center gap-2 text-xs text-[#7c7c8a]"><UserRound className="h-3.5 w-3.5 text-[#60a5fa]" /> Owner</div>
              <p className="mt-1 text-sm font-medium text-[#e4e4e7]">{owner}</p>
            </div>
            <div>
              <div className="flex items-center gap-2 text-xs text-[#7c7c8a]"><ShieldCheck className="h-3.5 w-3.5 text-[#22c55e]" /> Recommended next action</div>
              <p className="mt-1 text-sm leading-6 text-[#d4d4d8]">{action}</p>
            </div>
            <p className="border-t border-[#1f1f22] pt-4 text-xs leading-5 text-[#7c7c8a]">No external action is automatic. A human confirmation is required and recorded separately.</p>
          </div>
        </div>
      </div>
    </article>
  )
}

function CompactCard({
  template,
  run,
  busy,
  onOpen,
  onRun,
}: {
  template: WorkflowTemplate
  run: WorkflowRun | null
  busy: boolean
  onOpen: () => void
  onRun: () => void
}) {
  const verdict = getBrief(run)?.verdict ?? run?.status
  return (
    <article className="rounded-xl border border-[#1f1f22] bg-[#111114] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold text-[#f4f4f5]">{getTemplateName(template)}</h3>
            {isFixture(template, run) && <span className="text-[10px] font-medium uppercase tracking-wide text-[#93c5fd]">Fixture</span>}
          </div>
          <p className="mt-1 text-xs leading-5 text-[#7c7c8a]">{template.description}</p>
        </div>
        <VerdictBadge value={verdict} />
      </div>

      <p className="mt-4 border-l-2 border-[#f59e0b]/60 pl-3 text-sm leading-5 text-[#d4d4d8]">{blockerText(run, template)}</p>
      <Freshness run={run} />

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-[#1f1f22] pt-4">
        <div className="min-w-0 text-xs text-[#a1a1aa]"><span className="text-[#7c7c8a]">Owner: </span>{decisionOwner(run, template) ?? "Not assigned"}</div>
        <div className="flex items-center gap-3">
          <button type="button" onClick={onOpen} className="text-xs font-semibold text-[#86efac] hover:underline">Review</button>
          <button type="button" onClick={onRun} disabled={busy} className="text-xs text-[#a1a1aa] hover:text-[#e4e4e7] disabled:opacity-50">
            {busy ? "Replaying..." : "Sandbox replay"}
          </button>
        </div>
      </div>
    </article>
  )
}

function StoryStep({ number, title, icon, children }: { number: number; title: string; icon: ReactNode; children: ReactNode }) {
  return (
    <section className="relative border-l border-[#2a2a30] pb-7 pl-7 last:pb-0">
      <span className="absolute -left-3 top-0 flex h-6 w-6 items-center justify-center rounded-full border border-[#22c55e]/40 bg-[#111114] text-[10px] font-semibold text-[#86efac]">{number}</span>
      <h3 className="flex items-center gap-2 text-sm font-semibold text-[#f4f4f5]">{icon}{title}</h3>
      <div className="mt-2">{children}</div>
    </section>
  )
}

function EvidenceCards({ evidence }: { evidence: EvidenceRecord[] }) {
  if (evidence.length === 0) return <p className="text-sm text-[#7c7c8a]">No evidence records were returned.</p>
  return (
    <div className="space-y-3">
      {evidence.map((item, index) => (
        <div key={item.id ?? item.evidence_id ?? `${item.source_type ?? item.source}-${index}`} className="rounded border border-[#1f1f22] bg-[#111114] p-3">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium text-[#e4e4e7]">{formatEvidenceSource(item)}</span>
            {evidenceMode(item) === "demo_fixture" && <span className="text-[10px] font-medium uppercase tracking-wide text-[#93c5fd]">Fixture</span>}
            {item.freshness && <span className="text-[#7c7c8a]">{humanize(item.freshness)}</span>}
          </div>
          {item.excerpt && <p className="mt-2 text-sm leading-5 text-[#c4c4ca]">{item.excerpt}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[#7c7c8a]">
            <span>{formatTime(item.occurred_at ?? item.timestamp)}</span>
            {item.url && <a href={item.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[#86efac] hover:underline">Source <ExternalLink className="h-3 w-3" /></a>}
          </div>
        </div>
      ))}
    </div>
  )
}

function AuditProof({ run, template }: { run: WorkflowRun; template: WorkflowTemplate }) {
  const brief = getBrief(run)
  const evidence = brief?.evidence ?? []
  const inference = asStringList(brief?.inference)
  const missing = brief?.missing_evidence ?? []
  const memories = brief?.memory_refs ?? []
  const outcomes = run.outcomes ?? []

  return (
    <details className="group rounded-xl border border-[#1f1f22] bg-[#09090b]">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-[#e4e4e7]">
        <span className="flex items-center gap-2"><Fingerprint className="h-4 w-4 text-[#a78bfa]" /> Audit proof</span>
        <ChevronDown className="h-4 w-4 text-[#7c7c8a] transition-transform group-open:rotate-180" />
      </summary>
      <div className="space-y-5 border-t border-[#1f1f22] p-4">
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#7c7c8a]">Source excerpts and freshness</h4>
          <EvidenceCards evidence={evidence} />
        </section>
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#7c7c8a]">Qwen inference</h4>
          {inference.length > 0 ? <div className="space-y-2 text-sm leading-5 text-[#c4c4ca]">{inference.map((item, index) => <p key={`${item}-${index}`}>{item}</p>)}</div> : <p className="text-sm text-[#7c7c8a]">No inference was returned.</p>}
        </section>
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#7c7c8a]">Memory provenance</h4>
          {memories.length > 0 ? (
            <div className="space-y-2">
              {memories.map((memory, index) => (
                <div key={memory.id ?? memory.memory_id ?? memory.skill_id ?? index} className="rounded border border-[#1f1f22] bg-[#111114] p-3 text-sm">
                  <div className="font-medium text-[#e4e4e7]">{memory.name ?? memory.skill_id ?? memory.memory_id ?? "Referenced memory"}</div>
                  {memory.summary && <p className="mt-1 text-[#a1a1aa]">{memory.summary}</p>}
                  {isRecord(memory.provenance) && <pre className="mt-2 overflow-auto text-[10px] leading-5 text-[#7c7c8a]">{jsonText(memory.provenance)}</pre>}
                </div>
              ))}
            </div>
          ) : <p className="text-sm text-[#7c7c8a]">No memory references were returned.</p>}
        </section>
        {missing.length > 0 && (
          <section>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#fbbf24]">Missing evidence</h4>
            <ul className="space-y-1 text-sm text-[#d4d4d8]">{missing.map((item, index) => <li key={`${missingEvidenceText(item)}-${index}`}>- {missingEvidenceText(item)}</li>)}</ul>
          </section>
        )}
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#7c7c8a]">Deterministic SAG trace</h4>
          <pre className="max-h-64 overflow-auto rounded bg-[#050505] p-3 text-[11px] leading-5 text-[#a1a1aa]">{jsonText(brief?.sag_trace)}</pre>
        </section>
        <section>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#7c7c8a]">Outcome history</h4>
          {outcomes.length === 0 ? <p className="text-sm text-[#7c7c8a]">No human outcome has been recorded for this run.</p> : (
            <div className="space-y-2">
              {outcomes.map((outcome, index) => (
                <div key={outcome.id ?? index} className="rounded bg-[#111114] p-3 text-sm">
                  <div className="flex items-center justify-between gap-3"><span className={outcome.approved ? "text-[#86efac]" : "text-[#fbbf24]"}>{outcome.approved ? "Human-approved" : "Kept in review"}</span><span className="text-[10px] text-[#7c7c8a]">{formatTime(outcome.recorded_at ?? outcome.created_at ?? outcome.timestamp)}</span></div>
                  {typeof outcome.note === "string" ? <p className="mt-1 text-[#c4c4ca]">{outcome.note}</p> : outcome.outcome && <p className="mt-1 text-[#c4c4ca]">{outcome.outcome}</p>}
                  {outcome.actor && <p className="mt-1 font-mono text-[10px] text-[#7c7c8a]">{outcome.actor}</p>}
                </div>
              ))}
            </div>
          )}
        </section>
        <p className="text-[10px] text-[#686871]">Template: {getTemplateId(template)}. Raw values above are returned by the backend and are not client-side verdicts.</p>
      </div>
    </details>
  )
}

function DetailDrawer({
  template,
  run,
  outcomeText,
  outcomeBusy,
  outcomeError,
  replayBusy,
  onOutcomeTextChange,
  onRecordOutcome,
  onReplay,
  onClose,
}: {
  template: WorkflowTemplate
  run: WorkflowRun | null
  outcomeText: string
  outcomeBusy: boolean
  outcomeError: string | null
  replayBusy: boolean
  onOutcomeTextChange: (value: string) => void
  onRecordOutcome: (approved: boolean) => void
  onReplay: () => void
  onClose: () => void
}) {
  const brief = getBrief(run)
  const facts = brief?.facts ?? []
  const changed = changedStatements(run)
  const memories = brief?.memory_refs ?? []
  const verdict = brief?.verdict ?? run?.status
  const canonicalPreview = isCanonicalPreview(run)

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-label="Decision explanation">
      <button type="button" onClick={onClose} className="absolute inset-0 bg-black/75" aria-label="Close decision explanation" />
      <aside className="relative h-full w-full max-w-2xl overflow-y-auto border-l border-[#2a2a30] bg-[#0b0b0d] p-5 shadow-2xl sm:p-7">
        <div className="sticky top-0 z-10 -mt-5 -mx-5 mb-6 flex items-start justify-between border-b border-[#1f1f22] bg-[#0b0b0d]/95 px-5 py-5 backdrop-blur sm:-mt-7 sm:-mx-7 sm:px-7 sm:py-6">
          <div className="pr-4">
            <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#22c55e]">Decision explanation</p>
            <div className="mt-1 flex flex-wrap items-center gap-2"><h2 className="text-xl font-semibold text-[#fafafa]">{getTemplateName(template)}</h2><VerdictBadge value={verdict} /></div>
            <p className="mt-2 text-xs text-[#7c7c8a]">A five-step causal story from evidence to a human-owned next action.</p>
          </div>
          <button type="button" onClick={onClose} className="rounded p-1 text-[#7c7c8a] hover:bg-[#17171a] hover:text-[#e4e4e7]" aria-label="Close"><X className="h-5 w-5" /></button>
        </div>

        {!run ? (
          <div className="rounded-lg border border-dashed border-[#2a2a30] bg-[#111114] p-5 text-sm text-[#a1a1aa]">This workflow has no evaluated server run yet. Start the labeled sandbox replay to create an auditable DecisionBrief.</div>
        ) : (
          <div className="space-y-0">
            <StoryStep number={1} title="What was stopped?" icon={<ShieldAlert className="h-4 w-4 text-[#fca5a5]" />}>
              <p className="text-sm leading-6 text-[#d4d4d8]">{blockerText(run, template)}</p>
              <div className="mt-3 rounded-lg border border-[#1f1f22] bg-[#111114] p-3"><p className="text-[10px] uppercase tracking-wide text-[#7c7c8a]">Backend verdict</p><div className="mt-2"><VerdictBadge value={verdict} /></div></div>
            </StoryStep>

            <StoryStep number={2} title="What changed?" icon={<AlertTriangle className="h-4 w-4 text-[#fbbf24]" />}>
              {changed.length > 0 ? <div className="space-y-2 text-sm leading-6 text-[#c4c4ca]">{changed.map((item, index) => <p key={`${item}-${index}`}>{item}</p>)}</div> : <p className="text-sm text-[#7c7c8a]">No server-provided change inference was returned.</p>}
              {facts.length > 0 && <div className="mt-3 rounded border border-[#22c55e]/20 bg-[#22c55e]/5 p-3"><p className="mb-1 text-[10px] uppercase tracking-wide text-[#86efac]">Facts used</p><ul className="space-y-1 text-sm text-[#c4c4ca]">{facts.map((fact, index) => <li key={`${factText(fact)}-${index}`}>- {factText(fact)}</li>)}</ul></div>}
            </StoryStep>

            <StoryStep number={3} title="What did Company Brain remember?" icon={<Database className="h-4 w-4 text-[#a78bfa]" />}>
              {memories.length > 0 ? <div className="space-y-2">{memories.map((memory, index) => <div key={memory.id ?? memory.memory_id ?? memory.skill_id ?? index} className="rounded border border-[#1f1f22] bg-[#111114] p-3 text-sm"><div className="font-medium text-[#e4e4e7]">{memory.name ?? memory.skill_id ?? memory.memory_id ?? "Referenced memory"}</div>{memory.summary && <p className="mt-1 leading-5 text-[#a1a1aa]">{memory.summary}</p>}</div>)}</div> : <p className="text-sm text-[#7c7c8a]">No prior memory references were returned.</p>}
            </StoryStep>

            <StoryStep number={4} title="Why did the safety check fail?" icon={<ShieldCheck className="h-4 w-4 text-[#fbbf24]" />}>
              <p className="text-sm leading-6 text-[#d4d4d8]">{sagExplanation(verdict)}</p>
              <p className="mt-2 text-xs leading-5 text-[#7c7c8a]">SAG is deterministic: it checks the current context against the server-defined rule. The full trace is preserved in Audit proof.</p>
            </StoryStep>

            <StoryStep number={5} title="Who must act next?" icon={<UserRound className="h-4 w-4 text-[#60a5fa]" />}>
              <div className="rounded-lg border border-[#1f1f22] bg-[#111114] p-3"><p className="text-[10px] uppercase tracking-wide text-[#7c7c8a]">Owner</p><p className="mt-1 text-sm font-medium text-[#e4e4e7]">{decisionOwner(run, template) ?? "Owner role not assigned"}</p><p className="mt-3 text-[10px] uppercase tracking-wide text-[#7c7c8a]">Recommended action</p><p className="mt-1 text-sm leading-6 text-[#d4d4d8]">{recommendedAction(run, template) ?? "No server recommendation was returned."}</p></div>
              {canonicalPreview ? (
                <div className="mt-3 rounded-lg border border-[#60a5fa]/25 bg-[#60a5fa]/5 p-3"><p className="text-sm leading-5 text-[#bfdbfe]">This is the immutable judge fixture. Replay it in the sandbox to compile evidence with Qwen and record a human outcome without changing canonical memory.</p><button type="button" onClick={onReplay} disabled={replayBusy} className="mt-3 inline-flex items-center gap-2 rounded border border-[#60a5fa]/50 px-3 py-2 text-xs font-semibold text-[#bfdbfe] hover:bg-[#60a5fa]/10 disabled:opacity-50">{replayBusy && <LoaderCircle className="h-3.5 w-3.5 animate-spin" />}{replayBusy ? "Replaying..." : "Replay in sandbox"}</button></div>
              ) : (
                <div className="mt-3"><p className="text-xs leading-5 text-[#7c7c8a]">Recording this outcome does not execute an external company action.</p><textarea value={outcomeText} onChange={(event) => onOutcomeTextChange(event.target.value)} placeholder="Record the human decision or follow-up..." className="mt-3 min-h-20 w-full rounded border border-[#2a2a30] bg-[#111114] px-3 py-2 text-sm text-[#e4e4e7] outline-none placeholder:text-[#5a5a62] focus:border-[#22c55e]/70" />{outcomeError && <p className="mt-2 text-xs text-[#fca5a5]">{outcomeError}</p>}<div className="mt-3 flex flex-wrap gap-2"><button type="button" disabled={outcomeBusy} onClick={() => onRecordOutcome(true)} className="rounded bg-[#22c55e] px-3 py-2 text-xs font-semibold text-[#050505] hover:bg-[#4ade80] disabled:opacity-50">{outcomeBusy ? "Recording..." : "Confirm human action"}</button><button type="button" disabled={outcomeBusy} onClick={() => onRecordOutcome(false)} className="rounded border border-[#f59e0b]/50 px-3 py-2 text-xs font-semibold text-[#fbbf24] hover:bg-[#f59e0b]/10 disabled:opacity-50">Keep in review</button></div></div>
              )}
            </StoryStep>
          </div>
        )}

        {run && <div className="mt-7"><AuditProof run={run} template={template} /></div>}
      </aside>
    </div>
  )
}

function SystemProof({ readiness, readinessError, sources, sourcesError }: { readiness: DemoReadiness | null; readinessError: string | null; sources: WorkflowSource[]; sourcesError: string | null }) {
  const fixtureCount = sources.filter((source) => workflowSourceMode(source) === "demo_fixture").length
  const liveCount = sources.length - fixtureCount
  const sourceSummary = sources.length === 0 ? "No evidence records reported" : `${fixtureCount} fixture evidence record${fixtureCount === 1 ? "" : "s"} / ${liveCount} live source${liveCount === 1 ? "" : "s"}`

  return (
    <details className="group rounded-xl border border-[#1f1f22] bg-[#111114]">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-5 py-4"><div><p className="flex items-center gap-2 text-sm font-semibold text-[#e4e4e7]"><Database className="h-4 w-4 text-[#22c55e]" /> System proof</p><p className="mt-1 text-xs text-[#7c7c8a]">{sourceSummary}. Deployment and source status are reported by the backend.</p></div><ChevronDown className="h-4 w-4 shrink-0 text-[#7c7c8a] transition-transform group-open:rotate-180" /></summary>
      <div className="space-y-4 border-t border-[#1f1f22] p-4">
        {readiness ? <div className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-[#1f1f22] bg-[#1f1f22] md:grid-cols-5"><ReadinessItem label="Build" value={readiness.build_sha ?? "Not reported"} mono /><ReadinessItem label="Qwen" value={readinessValue(readiness.qwen_configured, "Configured", "Not configured")} /><ReadinessItem label="Embeddings" value={readinessValue(readiness.embedding_healthy, "Healthy", "Unavailable")} /><ReadinessItem label="Scenario" value={readiness.scenario_version ?? "Not reported"} mono /><ReadinessItem label="Canonical memory" value={readiness.canonical_skill_count != null ? `${readiness.canonical_skill_count} skills` : "Not reported"} /></div> : <p className="rounded border border-[#1f1f22] bg-[#09090b] px-3 py-2 text-xs text-[#7c7c8a]">{readinessError ?? "Loading deployment readiness..."}</p>}
        {sourcesError ? <p className="text-sm text-[#7c7c8a]">{sourcesError}</p> : sources.length === 0 ? <p className="text-sm text-[#7c7c8a]">No source records have been reported.</p> : <div className="flex flex-wrap gap-2">{sources.map((source) => <div key={workflowSourceId(source)} className="rounded border border-[#2a2a30] bg-[#09090b] px-3 py-2 text-xs"><div className="flex items-center gap-2"><span className="font-medium text-[#e4e4e7]">{workflowSourceLabel(source)}</span>{workflowSourceMode(source) === "demo_fixture" && <span className="text-[10px] font-medium uppercase tracking-wide text-[#93c5fd]">Fixture</span>}</div><div className="mt-1 text-[#7c7c8a]">{humanize(workflowSourceStatus(source))}{workflowSourceTimestamp(source) ? ` / ${formatTime(workflowSourceTimestamp(source))}` : ""}</div></div>)}</div>}
      </div>
    </details>
  )
}

function LoadingCard({ flagship = false }: { flagship?: boolean }) {
  return <div className={`animate-pulse rounded-xl border border-[#1f1f22] bg-[#111114] p-5 ${flagship ? "min-h-72" : "min-h-52"}`}><div className="h-5 w-2/3 rounded bg-[#222227]" /><div className="mt-4 h-3 w-full rounded bg-[#1b1b20]" /><div className="mt-4 h-20 rounded bg-[#17171a]" /><div className="mt-4 h-8 w-32 rounded bg-[#1b1b20]" /></div>
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
    const [templateResult, sourceResult, readinessResult] = await Promise.allSettled([getWorkflowTemplates(), getWorkflowSources(), getDemoReadiness()])

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
        return { ...embedded, ...previous }
      })
      setSelectedTemplateId((current) => current ?? getTemplateId(nextTemplates.find((template) => getTemplateId(template) === "release-safety") ?? nextTemplates[0] ?? {}))
      setTemplatesError(null)
    } else {
      setTemplates([])
      setTemplatesError("The Decision Queue API is unavailable. No client-side verdict has been inferred.")
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

  useEffect(() => { void refresh() }, [refresh])

  const orderedTemplates = useMemo(() => [...templates].sort((left, right) => {
    if (getTemplateId(left) === "release-safety") return -1
    if (getTemplateId(right) === "release-safety") return 1
    return getTemplateName(left).localeCompare(getTemplateName(right))
  }), [templates])
  const flagship = orderedTemplates[0] ?? null
  const supportingTemplates = orderedTemplates.slice(1)
  const selectedTemplate = useMemo(() => templates.find((template) => getTemplateId(template) === selectedTemplateId) ?? null, [selectedTemplateId, templates])
  const selectedRun = selectedTemplate ? runs[getTemplateId(selectedTemplate)] ?? getEmbeddedRun(selectedTemplate) : null
  const humanDecisionCount = orderedTemplates.filter((template) => getBrief(runs[getTemplateId(template)] ?? getEmbeddedRun(template))?.human_approval_required !== false).length
  const queueHeading = loading
    ? "Loading Decision Queue..."
    : templatesError
      ? "Decision Queue awaits a server response"
      : `${humanDecisionCount} decision${humanDecisionCount === 1 ? "" : "s"} need a human`

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
    const note = outcomeText.trim()
    if (!note) {
      setOutcomeError("Add a short human decision before recording an outcome.")
      return
    }
    setOutcomeError(null)
    setOutcomeBusy(true)
    try {
      const response = await postWorkflowOutcome(selectedRun.id, { approved, outcome: approved ? "confirmed_effective" : "needs_review", note, actor: "judge" })
      const returnedRun = asWorkflowRun(response)
      if (returnedRun) {
        setRuns((current) => ({ ...current, [returnedRun.template_id]: returnedRun }))
      } else {
        const returnedOutcome = asWorkflowOutcome(response)
        if (returnedOutcome) setRuns((current) => ({ ...current, [selectedRun.template_id]: { ...selectedRun, outcomes: [...(selectedRun.outcomes ?? []), returnedOutcome] } }))
      }
      setOutcomeText("")
    } catch (error) {
      setOutcomeError(error instanceof Error ? error.message : "Unable to record the human outcome.")
    } finally {
      setOutcomeBusy(false)
    }
  }

  return (
    <div className="mx-auto max-w-7xl space-y-5 pb-10">
      <section className="flex flex-col justify-between gap-4 rounded-2xl border border-[#22c55e]/25 bg-gradient-to-br from-[#22c55e]/10 via-[#111114] to-[#111114] p-5 md:flex-row md:items-end md:p-7">
        <div className="max-w-3xl"><div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[#22c55e]/30 bg-[#22c55e]/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.15em] text-[#86efac]"><CircleDot className="h-3 w-3" /> Governed decision queue</div><h1 className="text-3xl font-semibold tracking-tight text-[#fafafa]">{queueHeading}</h1><p className="mt-2 text-sm leading-6 text-[#b4b4bb] md:text-base">Company Brain catches the moment reality changes, explains why the old memory is unsafe, and hands one accountable next action to a person.</p></div>
        <button type="button" onClick={() => void refresh()} disabled={refreshing} className="inline-flex shrink-0 items-center justify-center gap-2 rounded border border-[#2a2a30] bg-[#111114] px-3 py-2 text-sm text-[#e4e4e7] hover:border-[#22c55e]/50 disabled:opacity-50"><RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh server state</button>
      </section>

      {actionError && <div className="flex items-start gap-2 rounded border border-[#ef4444]/30 bg-[#ef4444]/5 px-3 py-2 text-sm text-[#fca5a5]"><AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" /> {actionError}</div>}

      {loading ? <section className="space-y-4"><LoadingCard flagship /><div className="grid grid-cols-1 gap-4 lg:grid-cols-2"><LoadingCard /><LoadingCard /></div></section> : templatesError ? <section className="rounded-xl border border-dashed border-[#2a2a30] bg-[#111114] px-5 py-10 text-center"><ShieldAlert className="mx-auto h-7 w-7 text-[#7c7c8a]" /><h2 className="mt-3 font-medium">Decision Queue unavailable</h2><p className="mx-auto mt-1 max-w-lg text-sm text-[#7c7c8a]">{templatesError}</p><button type="button" onClick={() => void refresh()} className="mt-4 text-sm font-medium text-[#86efac] hover:underline">Retry server connection</button></section> : !flagship ? <section className="rounded-xl border border-dashed border-[#2a2a30] bg-[#111114] px-5 py-10 text-center"><Bot className="mx-auto h-7 w-7 text-[#7c7c8a]" /><h2 className="mt-3 font-medium">No workflow templates reported</h2><p className="mx-auto mt-1 max-w-lg text-sm text-[#7c7c8a]">The API is available, but it has not returned any server-owned workflow templates yet.</p></section> : <>
        <section><FlagshipCard template={flagship} run={runs[getTemplateId(flagship)] ?? getEmbeddedRun(flagship)} busy={runningTemplateId === getTemplateId(flagship)} onOpen={() => openDrawer(getTemplateId(flagship))} onRun={() => void runFixture(flagship)} /></section>
        {supportingTemplates.length > 0 && <section><div className="mb-3 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between"><div><h2 className="text-lg font-semibold text-[#f4f4f5]">Same engine, two more business decisions</h2><p className="mt-1 text-sm text-[#7c7c8a]">These are reusable workflow templates, not isolated demo agents.</p></div><span className="text-xs text-[#7c7c8a]">Evidence to memory to live context to human action</span></div><div className="grid grid-cols-1 gap-4 lg:grid-cols-2">{supportingTemplates.map((template) => <CompactCard key={getTemplateId(template)} template={template} run={runs[getTemplateId(template)] ?? getEmbeddedRun(template)} busy={runningTemplateId === getTemplateId(template)} onOpen={() => openDrawer(getTemplateId(template))} onRun={() => void runFixture(template)} />)}</div></section>}
      </>}

      <SystemProof readiness={readiness} readinessError={readinessError} sources={sources} sourcesError={sourcesError} />
      <section className="rounded-lg border border-[#60a5fa]/25 bg-[#60a5fa]/5 px-4 py-3 text-xs leading-5 text-[#b8c7e5]"><span className="font-semibold text-[#bfdbfe]">Governance boundary: </span>Fixture replays and demo clicks do not train canonical memory. Only a human-confirmed outcome is eligible for later reinforcement.</section>

      {drawerOpen && selectedTemplate && <DetailDrawer template={selectedTemplate} run={selectedRun} outcomeText={outcomeText} outcomeBusy={outcomeBusy} outcomeError={outcomeError} replayBusy={runningTemplateId === getTemplateId(selectedTemplate)} onOutcomeTextChange={setOutcomeText} onRecordOutcome={(approved) => void recordOutcome(approved)} onReplay={() => void runFixture(selectedTemplate)} onClose={() => setDrawerOpen(false)} />}
    </div>
  )
}

function ReadinessItem({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return <div className="min-w-0 bg-[#111114] px-3 py-3"><div className="text-[10px] uppercase tracking-wide text-[#7c7c8a]">{label}</div><div className={`mt-1 truncate text-xs text-[#e4e4e7] ${mono ? "font-mono" : ""}`}>{value}</div></div>
}
