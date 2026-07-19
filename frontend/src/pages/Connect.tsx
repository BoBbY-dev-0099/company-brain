import { useCallback, useEffect, useMemo, useState } from "react"
import { ArrowLeft, Bot, CheckCircle2, ChevronDown, Cloud, FileText, Github, MessageSquareText, RefreshCw, ShieldCheck, Webhook } from "lucide-react"
import { Link } from "react-router-dom"
import { getIntegrationCatalog, getSourceConnections, type SourceConnection } from "../lib/api"
import type { IntegrationBoundary, IntegrationCatalog } from "../types/schema"

function sourceIcon(provider: string) {
  if (provider === "slack") return MessageSquareText
  if (provider === "github") return Github
  if (provider === "google_drive") return FileText
  if (provider === "web") return Cloud
  return Webhook
}

function tone(status: string) {
  if (status === "connected") return "border-emerald-200 bg-emerald-50 text-emerald-800"
  if (status === "contract_ready") return "border-blue-200 bg-blue-50 text-blue-800"
  if (status === "setup_required") return "border-amber-200 bg-amber-50 text-amber-800"
  return "border-slate-200 bg-slate-50 text-slate-600"
}

function boundaries(catalog: IntegrationCatalog | null) {
  return catalog?.connection_boundaries ?? catalog?.connections ?? []
}

export default function Connect() {
  const [sources, setSources] = useState<SourceConnection[]>([])
  const [catalog, setCatalog] = useState<IntegrationCatalog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [sourcePayload, catalogPayload] = await Promise.all([getSourceConnections(), getIntegrationCatalog()])
      setSources(sourcePayload.connections)
      setCatalog(catalogPayload)
      setError(null)
    } catch {
      setError("The server could not load its integration status. The browser does not infer connection claims.")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void refresh() }, [refresh])
  const mcp = useMemo(() => boundaries(catalog).find((item) => item.id === "agent"), [catalog])
  const workflow = useMemo(() => boundaries(catalog).find((item) => item.id === "workflow"), [catalog])

  return <div className="min-h-screen bg-[#f5f1e8] text-[#17212b]">
    <header className="border-b border-[#d9d3c8] bg-[#f5f1e8]/95"><div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5"><Link to="/" className="inline-flex items-center gap-2 text-sm font-semibold"><ArrowLeft className="h-4 w-4" />Reality Console</Link><button type="button" onClick={() => void refresh()} className="inline-flex items-center gap-2 text-sm font-semibold text-[#2148c7]"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />Refresh status</button></div></header>
    <main className="mx-auto max-w-7xl px-5 py-10"><section className="max-w-3xl"><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Integration Studio</p><h1 className="mt-3 text-4xl font-semibold tracking-[-0.05em]">Connect evidence. Keep action authority outside.</h1><p className="mt-4 text-base leading-7 text-[#5a6775]">Company Brain is the governed memory checkpoint inside an existing company workflow. It reads only the configured evidence boundaries and returns a DecisionBrief to the workflow or agent.</p></section>

      {error && <div className="mt-7 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div>}
      <section className="mt-9 grid gap-4 md:grid-cols-2 xl:grid-cols-4">{sources.map((source) => <SourceCard key={source.provider} source={source} />)}</section>
      <section className="mt-8 grid gap-5 lg:grid-cols-2"><ContractCard title="Connect an agent" icon={<Bot className="h-5 w-5" />} boundary={mcp} /><ContractCard title="Connect a workflow" icon={<ShieldCheck className="h-5 w-5" />} boundary={workflow} /></section>
      <section className="mt-8 rounded-2xl border border-[#d9d3c8] bg-[#fffcf7] p-5"><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">Deployment boundary</p><p className="mt-2 text-sm leading-6 text-[#536170]">Credentials are server-only environment configuration. The public product never accepts a Slack token, Google service-account file, or GitHub secret. OAuth self-service onboarding and a managed secret vault are roadmap items, not current claims.</p></section>
    </main>
  </div>
}

function SourceCard({ source }: { source: SourceConnection }) {
  const Icon = sourceIcon(source.provider)
  return <article className="rounded-2xl border border-[#ded7cb] bg-[#fffcf7] p-5 shadow-[0_12px_32px_rgba(52,45,35,0.04)]"><div className="flex items-start justify-between gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf2fb] text-[#2f5eeb]"><Icon className="h-5 w-5" /></span><span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${tone(source.status)}`}>{source.status.replaceAll("_", " ")}</span></div><h2 className="mt-5 font-semibold">{source.title}</h2><p className="mt-2 text-xs leading-5 text-[#637080]">{source.allowed_scope.join(" · ")}</p><details className="mt-4 rounded-xl border border-[#e3ded4] bg-[#faf7f0] px-3 py-2"><summary className="cursor-pointer text-xs font-semibold text-[#42556b]">Setup and health</summary><div className="mt-3 space-y-2 text-xs leading-5 text-[#596778]"><p>Endpoint: <code className="break-all text-[#2148c7]">{source.endpoint ?? "server-defined"}</code></p>{Object.entries(source.configuration ?? {}).map(([key, value]) => <p key={key} className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-[#5d7d72]" />{key.replaceAll("_", " ")}: {String(value)}</p>)}{source.last_success_at && <p>Last healthy source event: {new Date(source.last_success_at).toLocaleString()}</p>}</div></details></article>
}

function ContractCard({ title, icon, boundary }: { title: string; icon: React.ReactNode; boundary?: IntegrationBoundary }) {
  if (!boundary) return <article className="rounded-2xl border border-[#ded7cb] bg-[#fffcf7] p-5">No server contract was reported.</article>
  const tools = Array.isArray(boundary.tools) ? boundary.tools : []
  const contracts = Array.isArray(boundary.contracts) ? boundary.contracts : []
  return <article className="rounded-2xl border border-[#d3ddf0] bg-[#f8faff] p-5"><div className="flex items-start justify-between gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#e6edff] text-[#2148c7]">{icon}</span><span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${tone(String(boundary.status ?? "preview"))}`}>{String(boundary.status ?? "preview").replaceAll("_", " ")}</span></div><h2 className="mt-5 font-semibold">{title}</h2><p className="mt-2 text-sm leading-6 text-[#536170]">{boundary.description}</p><p className="mt-4 rounded-lg border border-[#dbe3f2] bg-white px-3 py-2 font-mono text-xs text-[#2148c7] break-all">{boundary.endpoint}</p>{(tools.length > 0 || contracts.length > 0) && <details className="mt-4 rounded-xl border border-[#dbe3f2] bg-white px-3 py-2"><summary className="flex cursor-pointer items-center justify-between text-xs font-semibold text-[#42556b]">Published contract <ChevronDown className="h-4 w-4" /></summary><div className="mt-3 space-y-2">{[...tools, ...contracts].map((item, index) => <code key={index} className="block rounded bg-[#f5f7fb] p-2 text-[11px] leading-5 text-[#536170]">{typeof item === "string" ? item : `${item.method ?? ""} ${item.path ?? item.name ?? ""} ${item.permission ?? ""} ${item.purpose ?? ""}`}</code>)}</div></details>}</article>
}
