import { useEffect, useMemo, useState } from "react"
import {
  ArrowRight,
  Bot,
  Braces,
  CheckCircle2,
  CircleDot,
  CloudCog,
  FileInput,
  KeyRound,
  RefreshCw,
  ShieldCheck,
  UserRound,
} from "lucide-react"
import { getIntegrationCatalog } from "../lib/api"
import type { IntegrationBoundary, IntegrationCatalog, IntegrationContract } from "../types/schema"

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function catalogFrom(payload: unknown): IntegrationCatalog | null {
  if (!isRecord(payload)) return null
  return (isRecord(payload.catalog) ? payload.catalog : payload) as IntegrationCatalog
}

function boundariesFrom(catalog: IntegrationCatalog | null): IntegrationBoundary[] {
  if (!catalog) return []
  if (Array.isArray(catalog.connection_boundaries)) return catalog.connection_boundaries
  return Array.isArray(catalog.connections) ? catalog.connections : []
}

function boundaryId(boundary: IntegrationBoundary, index: number): string {
  return boundary.id ?? `boundary-${index}`
}

function statusStyle(status: string | undefined): string {
  switch (status) {
    case "connected":
      return "border-[#22c55e]/40 bg-[#22c55e]/10 text-[#86efac]"
    case "contract_ready":
      return "border-[#60a5fa]/40 bg-[#60a5fa]/10 text-[#bfdbfe]"
    case "setup_required":
      return "border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#fbbf24]"
    case "fixture":
      return "border-[#a78bfa]/40 bg-[#a78bfa]/10 text-[#c4b5fd]"
    default:
      return "border-[#2a2a30] bg-[#17171a] text-[#a1a1aa]"
  }
}

function displayStatus(status: string | undefined): string {
  return status ?? "not_reported"
}

function boundaryIcon(id: string | undefined) {
  if (id === "evidence") return FileInput
  if (id === "workflow") return Braces
  if (id === "agent") return Bot
  return CloudCog
}

function contractText(value: IntegrationContract | string): string {
  if (typeof value === "string") return value
  const method = typeof value.method === "string" ? value.method : ""
  const endpoint = typeof value.path === "string" ? value.path : typeof value.endpoint === "string" ? value.endpoint : ""
  const title = typeof value.title === "string" ? value.title : ""
  const name = typeof value.name === "string" ? value.name : ""
  const permission = typeof value.permission === "string" ? `(${value.permission})` : ""
  const description = typeof value.description === "string" ? value.description : typeof value.purpose === "string" ? value.purpose : ""
  return [method, endpoint || title || name, permission, description].filter(Boolean).join(" - ") || "Server contract detail"
}

function contractItems(value: unknown): Array<IntegrationContract | string> {
  return Array.isArray(value)
    ? value.filter((item): item is IntegrationContract | string => typeof item === "string" || isRecord(item))
    : []
}

function exampleText(value: unknown): string | null {
  if (typeof value === "string") return value
  if (!isRecord(value)) return null
  for (const key of ["code", "curl", "content", "example"]) {
    if (typeof value[key] === "string") return value[key]
  }
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return null
  }
}

function BoundaryCard({ boundary, index }: { boundary: IntegrationBoundary; index: number }) {
  const Icon = boundaryIcon(boundary.id)
  const contracts = contractItems(boundary.contracts)
  const tools = contractItems(boundary.tools)
  const requirements = Array.isArray(boundary.requirements) ? boundary.requirements : []
  const examples = [boundary.example, boundary.example_request, ...(Array.isArray(boundary.examples) ? boundary.examples : [])]
    .map(exampleText)
    .filter((item): item is string => item !== null)

  return (
    <article className="rounded-2xl border border-[#1f1f22] bg-[#111114] p-5 md:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="rounded-lg border border-[#2a2a30] bg-[#09090b] p-2 text-[#86efac]">
            <Icon className="h-5 w-5" />
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7c7c8a]">Connection {index + 1}</p>
            <h2 className="mt-1 text-lg font-semibold text-[#f4f4f5]">{boundary.title ?? boundary.id ?? "Server-defined connection"}</h2>
          </div>
        </div>
        <span className={`shrink-0 rounded-full border px-2.5 py-1 font-mono text-[10px] font-semibold ${statusStyle(boundary.status)}`}>
          {displayStatus(boundary.status)}
        </span>
      </div>

      <p className="mt-4 text-sm leading-6 text-[#b4b4bb]">{boundary.description ?? "The server has not provided a description for this connection boundary."}</p>

      {boundary.endpoint && (
        <div className="mt-4 rounded-lg border border-[#1f1f22] bg-[#09090b] px-3 py-2">
          <p className="text-[10px] uppercase tracking-wide text-[#7c7c8a]">Endpoint</p>
          <code className="mt-1 block break-all text-xs text-[#bfdbfe]">{boundary.endpoint}</code>
        </div>
      )}

      {requirements.length > 0 && (
        <div className="mt-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7c7c8a]">Requirements</p>
          <ul className="mt-2 space-y-1.5 text-sm text-[#d4d4d8]">
            {requirements.map((item) => <li key={item} className="flex gap-2"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#7c7c8a]" />{item}</li>)}
          </ul>
        </div>
      )}

      {contracts.length > 0 && (
        <div className="mt-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7c7c8a]">Server contracts</p>
          <div className="mt-2 space-y-2">
            {contracts.map((contract, itemIndex) => <code key={`${contractText(contract)}-${itemIndex}`} className="block break-words rounded border border-[#1f1f22] bg-[#09090b] px-3 py-2 text-[11px] leading-5 text-[#c4c4ca]">{contractText(contract)}</code>)}
          </div>
        </div>
      )}

      {examples.length > 0 && (
        <div className="mt-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7c7c8a]">Copy-paste example</p>
          {examples.map((example, itemIndex) => <pre key={`${example.slice(0, 32)}-${itemIndex}`} className="mt-2 max-h-56 overflow-auto rounded border border-[#1f1f22] bg-[#050505] p-3 text-[11px] leading-5 text-[#c4c4ca]">{example}</pre>)}
        </div>
      )}

      {tools.length > 0 && (
        <div className="mt-4">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#7c7c8a]">MCP tools</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {tools.map((tool, itemIndex) => <code key={`${contractText(tool)}-${itemIndex}`} className="rounded border border-[#1f1f22] bg-[#09090b] px-2 py-1 text-[11px] text-[#c4c4ca]">{contractText(tool)}</code>)}
          </div>
        </div>
      )}
    </article>
  )
}

export default function Connect() {
  const [catalog, setCatalog] = useState<IntegrationCatalog | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const refresh = async () => {
    setRefreshing(true)
    try {
      const payload = await getIntegrationCatalog()
      const nextCatalog = catalogFrom(payload)
      if (!nextCatalog) throw new Error("The server returned an invalid connection catalog.")
      setCatalog(nextCatalog)
      setError(null)
    } catch {
      setCatalog(null)
      setError("The connection catalog could not be loaded. Connection statuses are intentionally not inferred in the browser.")
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => { void refresh() }, [])

  const boundaries = useMemo(() => boundariesFrom(catalog), [catalog])
  const statusDefinitions = catalog?.status_definitions ?? {}
  const positioning = catalog?.positioning ?? "Company Brain does not replace a company's agents or systems. It is the governed memory checkpoint they call before consequential actions."

  return (
    <div className="mx-auto max-w-7xl space-y-5 pb-10">
      <section className="rounded-2xl border border-[#22c55e]/25 bg-gradient-to-br from-[#22c55e]/10 via-[#111114] to-[#111114] p-5 md:p-7">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div className="max-w-3xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-[#22c55e]/30 bg-[#22c55e]/10 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.15em] text-[#86efac]">
              <CircleDot className="h-3 w-3" /> Connection boundaries
            </div>
            <h1 className="text-3xl font-semibold tracking-tight text-[#fafafa]">Connect Company Brain to the systems you already run</h1>
            <p className="mt-2 text-sm leading-6 text-[#b4b4bb] md:text-base">{positioning}</p>
          </div>
          <button type="button" onClick={() => void refresh()} disabled={refreshing} className="inline-flex shrink-0 items-center justify-center gap-2 rounded border border-[#2a2a30] bg-[#111114] px-3 py-2 text-sm text-[#e4e4e7] hover:border-[#22c55e]/50 disabled:opacity-50">
            <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh catalog
          </button>
        </div>
        {catalog?.public_base_url && <p className="mt-5 font-mono text-xs text-[#93c5fd]">Public base URL: {catalog.public_base_url}</p>}
      </section>

      <section className="grid items-stretch gap-2 rounded-xl border border-[#1f1f22] bg-[#09090b] p-4 text-center sm:grid-cols-[1fr_auto_1fr_auto_1fr_auto_1fr] sm:gap-3">
        <FlowItem icon={<FileInput className="h-4 w-4" />} label="Company evidence" />
        <ArrowRight className="mx-auto hidden h-4 w-4 self-center text-[#686871] sm:block" />
        <FlowItem icon={<ShieldCheck className="h-4 w-4" />} label="Qwen memory + SAG" active />
        <ArrowRight className="mx-auto hidden h-4 w-4 self-center text-[#686871] sm:block" />
        <FlowItem icon={<Bot className="h-4 w-4" />} label="Agent or workflow" />
        <ArrowRight className="mx-auto hidden h-4 w-4 self-center text-[#686871] sm:block" />
        <FlowItem icon={<UserRound className="h-4 w-4" />} label="Human confirmation" />
      </section>

      {loading ? (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">{[0, 1, 2].map((item) => <div key={item} className="min-h-64 animate-pulse rounded-xl border border-[#1f1f22] bg-[#111114] p-5"><div className="h-5 w-2/3 rounded bg-[#222227]" /><div className="mt-4 h-3 w-full rounded bg-[#1b1b20]" /><div className="mt-4 h-24 rounded bg-[#17171a]" /></div>)}</div>
      ) : error ? (
        <section className="rounded-xl border border-dashed border-[#2a2a30] bg-[#111114] px-5 py-10 text-center"><KeyRound className="mx-auto h-7 w-7 text-[#7c7c8a]" /><h2 className="mt-3 font-medium text-[#e4e4e7]">Connection catalog unavailable</h2><p className="mx-auto mt-1 max-w-lg text-sm text-[#7c7c8a]">{error}</p><button type="button" onClick={() => void refresh()} className="mt-4 text-sm font-medium text-[#86efac] hover:underline">Retry server connection</button></section>
      ) : boundaries.length === 0 ? (
        <section className="rounded-xl border border-dashed border-[#2a2a30] bg-[#111114] px-5 py-10 text-center"><CloudCog className="mx-auto h-7 w-7 text-[#7c7c8a]" /><h2 className="mt-3 font-medium text-[#e4e4e7]">No connection boundaries reported</h2><p className="mx-auto mt-1 max-w-lg text-sm text-[#7c7c8a]">The API responded, but did not return any server-defined connection boundaries.</p></section>
      ) : (
        <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">{boundaries.map((boundary, index) => <BoundaryCard key={boundaryId(boundary, index)} boundary={boundary} index={index} />)}</section>
      )}

      {Object.keys(statusDefinitions).length > 0 && (
        <section className="rounded-xl border border-[#1f1f22] bg-[#111114] p-5">
          <h2 className="text-sm font-semibold text-[#e4e4e7]">Runtime status vocabulary</h2>
          <p className="mt-1 text-xs text-[#7c7c8a]">Definitions below are returned by the server, alongside each connection's current status.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {Object.entries(statusDefinitions).map(([status, definition]) => <div key={status} className="rounded border border-[#1f1f22] bg-[#09090b] p-3"><code className={`inline-flex rounded border px-2 py-1 text-[10px] font-semibold ${statusStyle(status)}`}>{status}</code><p className="mt-2 text-xs leading-5 text-[#a1a1aa]">{definition}</p></div>)}
          </div>
        </section>
      )}

      <section className="rounded-lg border border-[#60a5fa]/25 bg-[#60a5fa]/5 px-4 py-3 text-xs leading-5 text-[#b8c7e5]"><span className="font-semibold text-[#bfdbfe]">Governance boundary: </span>Every listed path creates or returns an auditable decision record. Human confirmation remains outside MCP, and no listed connector executes an external company action.</section>
    </div>
  )
}

function FlowItem({ icon, label, active = false }: { icon: React.ReactNode; label: string; active?: boolean }) {
  return <div className={`flex min-h-14 items-center justify-center gap-2 rounded-lg border px-3 py-3 text-xs font-medium ${active ? "border-[#22c55e]/35 bg-[#22c55e]/10 text-[#86efac]" : "border-[#1f1f22] bg-[#111114] text-[#c4c4ca]"}`}>{icon}{label}</div>
}
