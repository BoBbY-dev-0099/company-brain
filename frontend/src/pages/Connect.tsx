import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { ArrowLeft, Bot, CheckCircle2, ChevronDown, Cloud, FileText, Github, KeyRound, Loader2, LockKeyhole, MessageSquareText, Play, RefreshCw, Save, ShieldCheck, Webhook } from "lucide-react"
import { Link } from "react-router-dom"
import {
  getIntegrationCatalog,
  getOperatorConfigs,
  getOperatorSetup,
  getSourceConnections,
  saveOperatorConfig,
  testOperatorConfig,
  type OperatorProviderConfig,
  type OperatorSetup,
  type SourceConnection,
} from "../lib/api"
import type { IntegrationBoundary, IntegrationCatalog } from "../types/schema"

type Provider = "slack" | "github" | "google_drive" | "web"

const providerCopy: Record<Provider, { outcome: string; event: string }> = {
  slack: { outcome: "Turn a verified incident message into fresh operational evidence.", event: "Send a synthetic incident message after saving." },
  github: { outcome: "Capture a merged code change and its diff before an agent deploys it.", event: "Merge a tiny test PR after saving." },
  google_drive: { outcome: "Keep a shared policy or runbook current without copying it into prompts.", event: "The worker polls the approved folder every five minutes." },
  web: { outcome: "Fetch explicitly allowlisted external policy or status evidence safely.", event: "Use a write-scoped MCP key to fetch one approved URL." },
}

const label: Record<string, string> = {
  team_id: "Slack workspace ID",
  channel_ids: "Allowed incident channel IDs",
  signing_secret: "Slack signing secret",
  bot_token: "Slack bot token (optional remote test)",
  repos: "GitHub repositories (comma-separated)",
  webhook_secret: "GitHub webhook secret",
  token: "Fine-grained GitHub read token",
  folder_id: "Google Drive folder ID",
  service_account_json: "Google service-account JSON",
  allowed_hosts: "Allowed public HTTPS hosts (comma-separated)",
}

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

function isProvider(value: string): value is Provider {
  return value === "slack" || value === "github" || value === "google_drive" || value === "web"
}

function displayError(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } } }
  return value?.response?.data?.detail || "The server could not complete that connector operation."
}

export default function Connect() {
  const [sources, setSources] = useState<SourceConnection[]>([])
  const [catalog, setCatalog] = useState<IntegrationCatalog | null>(null)
  const [setup, setSetup] = useState<OperatorSetup | null>(null)
  const [configs, setConfigs] = useState<Record<string, OperatorProviderConfig>>({})
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [unlockToken, setUnlockToken] = useState("")
  const [operatorToken, setOperatorToken] = useState("")
  const [unlocking, setUnlocking] = useState(false)
  const [selected, setSelected] = useState<Provider | null>(null)
  const [values, setValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      const [sourcePayload, catalogPayload, setupPayload] = await Promise.all([getSourceConnections(), getIntegrationCatalog(), getOperatorSetup()])
      setSources(sourcePayload.connections)
      setCatalog(catalogPayload)
      setSetup(setupPayload)
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
  const unlocked = Boolean(operatorToken)

  async function unlock() {
    setUnlocking(true)
    setNotice(null)
    try {
      const response = await getOperatorConfigs(unlockToken)
      setConfigs(response.providers)
      setOperatorToken(unlockToken)
      setUnlockToken("")
      setNotice("Operator setup unlocked for this browser session. Secrets are never shown again.")
    } catch (reason) {
      setError(displayError(reason))
    } finally {
      setUnlocking(false)
    }
  }

  function openProvider(provider: Provider) {
    const saved = configs[provider]
    setSelected(provider)
    setValues(saved?.public ?? {})
    setNotice(null)
  }

  async function saveProvider() {
    if (!selected || !operatorToken) return
    setSaving(true)
    setError(null)
    try {
      const response = await saveOperatorConfig(selected, values, operatorToken)
      setConfigs((current) => ({ ...current, [selected]: response.provider }))
      setValues(response.provider.public)
      setNotice(response.message)
      await refresh()
    } catch (reason) {
      setError(displayError(reason))
    } finally {
      setSaving(false)
    }
  }

  async function testProvider() {
    if (!selected || !operatorToken) return
    setTesting(true)
    setError(null)
    try {
      const response = await testOperatorConfig(selected, operatorToken)
      setNotice(response.detail)
      await refresh()
    } catch (reason) {
      setError(displayError(reason))
    } finally {
      setTesting(false)
    }
  }

  return <div className="min-h-screen bg-[#f5f1e8] text-[#17212b]">
    <header className="border-b border-[#d9d3c8] bg-[#f5f1e8]/95"><div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5"><Link to="/" className="inline-flex items-center gap-2 text-sm font-semibold"><ArrowLeft className="h-4 w-4" />Reality Console</Link><div className="flex items-center gap-4"><Link to="/play/integration-lab" className="text-sm font-semibold text-[#2148c7]">Run test company</Link><button type="button" onClick={() => void refresh()} className="inline-flex items-center gap-2 text-sm font-semibold text-[#2148c7]"><RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />Refresh live status</button></div></div></header>
    <main className="mx-auto max-w-7xl px-5 py-10">
      <section className="max-w-3xl"><p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Integration Studio</p><h1 className="mt-3 text-4xl font-semibold tracking-[-0.05em]">Connect the evidence your agents already use.</h1><p className="mt-4 text-base leading-7 text-[#5a6775]">Each connection becomes source-backed Reality Memory. Company Brain then gives your workflow or MCP agent a fresh, explainable DecisionBrief before it acts.</p></section>

      {error && <div className="mt-7 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800">{error}</div>}
      {notice && <div className="mt-7 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">{notice}</div>}

      <section className="mt-9 rounded-2xl border border-[#d9d3c8] bg-[#fffcf7] p-5"><div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between"><div><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">Operator setup</p><p className="mt-1 text-sm leading-6 text-[#536170]">Judges see redacted live status. A deployment operator can unlock this browser session to save encrypted source settings and run read-only connectivity checks.</p></div>{setup?.enabled ? (unlocked ? <span className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs font-semibold text-emerald-800"><CheckCircle2 className="h-4 w-4" />Operator session unlocked</span> : <div className="flex shrink-0 gap-2"><input aria-label="Operator unlock token" type="password" value={unlockToken} onChange={(event) => setUnlockToken(event.target.value)} placeholder="Operator unlock token" className="w-52 rounded-xl border border-[#d9d3c8] bg-white px-3 py-2 text-sm outline-none ring-[#2f5eeb] focus:ring-2" /><button type="button" disabled={!unlockToken || unlocking} onClick={() => void unlock()} className="inline-flex items-center gap-2 rounded-xl bg-[#17212b] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">{unlocking ? <Loader2 className="h-4 w-4 animate-spin" /> : <LockKeyhole className="h-4 w-4" />}Unlock</button></div>) : <span className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800"><KeyRound className="h-4 w-4" />Operator setup needs server enablement</span>}</div></section>

      <section className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">{sources.map((source) => <SourceCard key={source.provider} source={source} setup={setup} unlocked={unlocked} onConfigure={openProvider} />)}</section>
      {selected && setup?.providers[selected] && <OperatorPanel provider={selected} instructions={setup.providers[selected]} config={configs[selected]} values={values} onChange={(name, value) => setValues((current) => ({ ...current, [name]: value }))} saving={saving} testing={testing} onSave={() => void saveProvider()} onTest={() => void testProvider()} onClose={() => setSelected(null)} />}

      <section className="mt-8 grid gap-5 lg:grid-cols-2"><ContractCard title="Connect an agent" icon={<Bot className="h-5 w-5" />} boundary={mcp} /><ContractCard title="Connect a workflow" icon={<ShieldCheck className="h-5 w-5" />} boundary={workflow} /></section>
      <section className="mt-8 rounded-2xl border border-[#d9d3c8] bg-[#fffcf7] p-5"><p className="text-[10px] font-bold uppercase tracking-[0.15em] text-[#718096]">Connection boundary</p><p className="mt-2 text-sm leading-6 text-[#536170]">This is a deployment-operator setup flow for a chosen test workspace, folder, and repository—not a generic connector marketplace. Source adapters are read-only. The resulting decision can recommend an action, but Company Brain never deploys, refunds, changes a flag, or posts to Slack.</p></section>
    </main>
  </div>
}

function SourceCard({ source, setup, unlocked, onConfigure }: { source: SourceConnection; setup: OperatorSetup | null; unlocked: boolean; onConfigure: (provider: Provider) => void }) {
  const Icon = sourceIcon(source.provider)
  const provider = isProvider(source.provider) ? source.provider : null
  return <article className="rounded-2xl border border-[#ded7cb] bg-[#fffcf7] p-5 shadow-[0_12px_32px_rgba(52,45,35,0.04)]"><div className="flex items-start justify-between gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#edf2fb] text-[#2f5eeb]"><Icon className="h-5 w-5" /></span><span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${tone(source.status)}`}>{source.status.replaceAll("_", " ")}</span></div><h2 className="mt-5 font-semibold">{source.title}</h2><p className="mt-2 text-xs leading-5 text-[#637080]">{provider ? providerCopy[provider].outcome : source.allowed_scope.join(" · ")}</p><p className="mt-3 text-[11px] leading-5 text-[#6c7886]">Scope: {source.allowed_scope.join(" · ")}</p><div className="mt-5 flex items-center justify-between gap-2">{provider && setup?.enabled && unlocked ? <button type="button" onClick={() => onConfigure(provider)} className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#2148c7]"><KeyRound className="h-3.5 w-3.5" />Configure & test</button> : <span className="text-xs font-medium text-[#718096]">{setup?.enabled ? "Unlock to configure" : "Server setup required"}</span>}<details><summary className="cursor-pointer text-xs font-semibold text-[#42556b]">Proof</summary><div className="mt-3 space-y-2 rounded-xl border border-[#e3ded4] bg-[#faf7f0] p-3 text-xs leading-5 text-[#596778]"><p className="break-all">Endpoint: <code className="text-[#2148c7]">{source.endpoint ?? "server-defined"}</code></p>{Object.entries(source.configuration ?? {}).map(([key, value]) => <p key={key} className="flex gap-1.5"><CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#5d7d72]" />{key.replaceAll("_", " ")}: {String(value)}</p>)}{source.last_success_at && <p>Last healthy event: {new Date(source.last_success_at).toLocaleString()}</p>}</div></details></div></article>
}

function OperatorPanel({ provider, instructions, config, values, onChange, saving, testing, onSave, onTest, onClose }: { provider: Provider; instructions: { fields: string[]; endpoint: string; steps: string[] }; config?: OperatorProviderConfig; values: Record<string, string>; onChange: (name: string, value: string) => void; saving: boolean; testing: boolean; onSave: () => void; onTest: () => void; onClose: () => void }) {
  return <section className="mt-6 rounded-3xl border border-[#b9c9ee] bg-[#f8faff] p-6"><div className="flex flex-col justify-between gap-4 md:flex-row"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-[#2f5eeb]">Configure {provider.replaceAll("_", " ")}</p><h2 className="mt-2 text-2xl font-semibold tracking-[-0.04em]">{providerCopy[provider].outcome}</h2><p className="mt-2 max-w-2xl text-sm leading-6 text-[#5a6775]">{providerCopy[provider].event} Saved secret fields are masked; leave a secret field blank to keep it unchanged.</p></div><button type="button" onClick={onClose} className="self-start text-sm font-semibold text-[#536170]">Close</button></div><div className="mt-6 grid gap-6 lg:grid-cols-[0.75fr_1.25fr]"><ol className="space-y-3 rounded-2xl border border-[#d7e1f5] bg-white p-5 text-sm leading-6 text-[#536170]">{instructions.steps.map((step, index) => <li key={step} className="flex gap-3"><span className="grid h-6 w-6 shrink-0 place-items-center rounded-full bg-[#e7efff] text-xs font-bold text-[#2148c7]">{index + 1}</span>{step}</li>)}<li className="mt-4 border-t border-[#e2e8f5] pt-4 text-xs">Incoming endpoint: <code className="break-all text-[#2148c7]">{instructions.endpoint}</code></li></ol><div className="grid gap-4 sm:grid-cols-2">{instructions.fields.map((field) => <Field key={field} field={field} value={values[field] ?? ""} saved={Boolean(config?.secrets[field])} onChange={onChange} />)}</div></div><div className="mt-6 flex flex-wrap gap-3"><button type="button" disabled={saving} onClick={onSave} className="inline-flex items-center gap-2 rounded-xl bg-[#17212b] px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}Save encrypted configuration</button><button type="button" disabled={testing || saving} onClick={onTest} className="inline-flex items-center gap-2 rounded-xl border border-[#aabce7] bg-white px-4 py-2.5 text-sm font-semibold text-[#2148c7] disabled:opacity-50">{testing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}Run read-only test</button></div></section>
}

function Field({ field, value, saved, onChange }: { field: string; value: string; saved: boolean; onChange: (name: string, value: string) => void }) {
  const secret = field.includes("secret") || field === "token" || field === "service_account_json"
  const shared = "mt-1 w-full rounded-xl border border-[#cbd6e8] bg-white px-3 py-2.5 text-sm outline-none ring-[#2f5eeb] focus:ring-2"
  return <label className={field === "service_account_json" ? "sm:col-span-2" : ""}><span className="text-xs font-semibold text-[#42556b]">{label[field] ?? field.replaceAll("_", " ")}{saved && <span className="ml-2 text-[10px] font-normal text-emerald-700">saved</span>}</span>{field === "service_account_json" ? <textarea value={value} onChange={(event) => onChange(field, event.target.value)} placeholder={saved ? "Saved. Leave blank to preserve it." : "Paste JSON only after operator unlock."} rows={5} className={`${shared} font-mono text-xs`} /> : <input type={secret ? "password" : "text"} value={value} onChange={(event) => onChange(field, event.target.value)} placeholder={saved && secret ? "Saved. Leave blank to preserve it." : label[field] ?? field} className={shared} />}</label>
}

function ContractCard({ title, icon, boundary }: { title: string; icon: ReactNode; boundary?: IntegrationBoundary }) {
  if (!boundary) return <article className="rounded-2xl border border-[#ded7cb] bg-[#fffcf7] p-5">No server contract was reported.</article>
  const tools = Array.isArray(boundary.tools) ? boundary.tools : []
  const contracts = Array.isArray(boundary.contracts) ? boundary.contracts : []
  return <article className="rounded-2xl border border-[#d3ddf0] bg-[#f8faff] p-5"><div className="flex items-start justify-between gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-[#e6edff] text-[#2148c7]">{icon}</span><span className={`rounded-full border px-2 py-1 text-[10px] font-bold uppercase tracking-wide ${tone(String(boundary.status ?? "preview"))}`}>{String(boundary.status ?? "preview").replaceAll("_", " ")}</span></div><h2 className="mt-5 font-semibold">{title}</h2><p className="mt-2 text-sm leading-6 text-[#536170]">{boundary.description}</p><p className="mt-4 rounded-lg border border-[#dbe3f2] bg-white px-3 py-2 font-mono text-xs text-[#2148c7] break-all">{boundary.endpoint}</p>{(tools.length > 0 || contracts.length > 0) && <details className="mt-4 rounded-xl border border-[#dbe3f2] bg-white px-3 py-2"><summary className="flex cursor-pointer items-center justify-between text-xs font-semibold text-[#42556b]">Published contract <ChevronDown className="h-4 w-4" /></summary><div className="mt-3 space-y-2">{[...tools, ...contracts].map((item, index) => <code key={index} className="block rounded bg-[#f5f7fb] p-2 text-[11px] leading-5 text-[#536170]">{typeof item === "string" ? item : `${item.method ?? ""} ${item.path ?? item.name ?? ""} ${item.permission ?? ""} ${item.purpose ?? ""}`}</code>)}</div></details>}</article>
}
