import { useCallback, useEffect, useState } from "react"
import {
  Check,
  CheckCircle2,
  ChevronRight,
  Clipboard,
  Cloud,
  FileText,
  Github,
  KeyRound,
  Loader2,
  LockKeyhole,
  MessageSquareText,
  Play,
  RefreshCw,
  Save,
  ShieldCheck,
  Sparkles,
} from "lucide-react"
import { Link } from "react-router-dom"
import {
  getNexaFlowOverview,
  getOperatorConfigs,
  getOperatorSetup,
  saveOperatorConfig,
  syncOperatorOSS,
  testOperatorConfig,
  type NexaFlowOverview,
  type OperatorProviderConfig,
  type OperatorSetup,
  type SourceConnection,
} from "../lib/api"

type Provider = "slack" | "alibaba_oss" | "github"
type ProviderSetup = OperatorSetup["providers"][string]

const providerOrder: Provider[] = ["slack", "alibaba_oss", "github"]
const labels: Record<string, string> = {
  team_id: "Workspace ID",
  channel_ids: "#ops-incidents channel ID",
  signing_secret: "Signing secret",
  bot_token: "Bot token (optional, enables auth test)",
  repos: "Repository allowlist (owner/repository)",
  webhook_secret: "Webhook secret",
  token: "Fine-grained token",
  region: "OSS region",
  endpoint: "OSS endpoint",
  bucket: "Bucket name",
  prefix: "Runbook prefix",
  access_key_id: "RAM AccessKey ID",
  access_key_secret: "RAM AccessKey secret",
}
const icons = { slack: MessageSquareText, alibaba_oss: FileText, github: Github }
const providerNames: Record<Provider, string> = {
  slack: "Slack incidents",
  alibaba_oss: "Alibaba OSS runbook",
  github: "GitHub merged PRs",
}
const providerRoles: Record<Provider, string> = {
  slack: "Current operational reality",
  alibaba_oss: "Approved policy and runbook",
  github: "Code changes waiting to ship",
}

function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } } }
  return value.response?.data?.detail || "The server could not complete that setup request."
}

function providerEvidence(connection?: SourceConnection) {
  return connection?.last_success_at
    ? `Evidence received ${new Date(connection.last_success_at).toLocaleString()}`
    : "Waiting for the first real event"
}

export default function NexaFlowSetup() {
  const [setup, setSetup] = useState<OperatorSetup | null>(null)
  const [overview, setOverview] = useState<NexaFlowOverview | null>(null)
  const [connections, setConnections] = useState<SourceConnection[]>([])
  const [configs, setConfigs] = useState<Record<string, OperatorProviderConfig>>({})
  const [tokenInput, setTokenInput] = useState("")
  const [token, setToken] = useState("")
  const [selected, setSelected] = useState<Provider>("slack")
  const [values, setValues] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refreshPublic = useCallback(async () => {
    const [setupPayload, overviewPayload] = await Promise.all([getOperatorSetup(), getNexaFlowOverview()])
    setSetup(setupPayload)
    setOverview(overviewPayload)
    setConnections(overviewPayload.connections.filter((item) => providerOrder.includes(item.provider as Provider)))
    if (setupPayload.local_rehearsal) {
      const configPayload = await getOperatorConfigs()
      setConfigs(configPayload.providers)
    }
  }, [])

  useEffect(() => {
    void refreshPublic().catch((reason) => setError(errorText(reason)))
  }, [refreshPublic])

  useEffect(() => {
    setValues(configs[selected]?.public ?? {})
  }, [selected, configs])

  const selectedInfo = setup?.providers[selected]
  const selectedConnection = connections.find((item) => item.provider === selected)
  const configuredCount = connections.filter((item) => item.status === "connected").length
  const evidenceCount = overview?.evidence.filter((item) => providerOrder.includes(item.provider as Provider)).length ?? 0
  const allConfigured = configuredCount === providerOrder.length
  const setupReady = Boolean(setup?.local_rehearsal || token)
  const nextProvider = providerOrder.find((provider) => connections.find((item) => item.provider === provider)?.status !== "connected")

  async function unlock() {
    setBusy(true)
    try {
      const payload = await getOperatorConfigs(tokenInput)
      setConfigs(payload.providers)
      setToken(tokenInput)
      setTokenInput("")
      setNotice("Ready. Add each source once; saved secrets stay encrypted on the server.")
      setError(null)
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setBusy(false)
    }
  }

  async function saveAndVerify() {
    if (!setupReady) return
    setBusy(true)
    setError(null)
    try {
      const saved = await saveOperatorConfig(selected, values, setup?.local_rehearsal ? undefined : token)
      setConfigs((current) => ({ ...current, [selected]: saved.provider }))
      const result = await testOperatorConfig(selected, setup?.local_rehearsal ? undefined : token)
      setNotice(`${providerNames[selected]} is ready. ${result.detail}`)
      await refreshPublic()
      const upcoming = providerOrder.find((provider) => provider !== selected && connections.find((item) => item.provider === provider)?.status !== "connected")
      if (upcoming) setSelected(upcoming)
    } catch (reason) {
      setError(errorText(reason))
      await refreshPublic().catch(() => undefined)
    } finally {
      setBusy(false)
    }
  }

  async function test() {
    if (!setupReady) return
    setBusy(true)
    try {
      const result = await testOperatorConfig(selected, setup?.local_rehearsal ? undefined : token)
      setNotice(result.detail)
      await refreshPublic()
      setError(null)
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setBusy(false)
    }
  }

  async function syncOSS() {
    if (!setupReady) return
    setBusy(true)
    try {
      const result = await syncOperatorOSS(setup?.local_rehearsal ? undefined : token)
      setNotice(`${result.detail} ${result.accepted} new record(s) accepted.`)
      await refreshPublic()
      setError(null)
    } catch (reason) {
      setError(errorText(reason))
    } finally {
      setBusy(false)
    }
  }

  async function copy(value: string) {
    await navigator.clipboard.writeText(value)
    setNotice("Copied to clipboard.")
  }

  return (
    <div className="min-h-screen bg-[#f7f5ef] text-[#1d201e]">
      <header className="border-b border-dashed border-[#d6d1c6] bg-[#f7f5ef]/95">
        <div className="mx-auto flex h-[72px] max-w-6xl items-center justify-between px-5">
          <Link to="/" className="flex items-center gap-3 font-semibold tracking-[-.02em]"><span className="grid h-9 w-9 place-items-center rounded-full bg-[#113d32] text-sm font-bold text-white">B</span><span>Company Brain</span></Link>
          <div className="flex items-center gap-3"><Link to="/" className="hidden text-sm text-[#59645d] transition hover:text-[#113d32] sm:inline-flex">Live console</Link><span className="hidden font-mono text-[10px] font-bold uppercase tracking-[.16em] text-[#16745a] md:inline-flex">Integration studio</span><button type="button" onClick={() => void refreshPublic()} className="inline-flex items-center gap-2 rounded-full border border-[#c9c6bd] bg-[#fffdf8] px-3 py-2 text-xs font-semibold text-[#36423c]"><RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh</button></div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 py-12">
        <p className="font-mono text-[10px] font-bold uppercase tracking-[.24em] text-[#16745a]">Integration studio · source boundaries</p>
        <div className="mt-3 grid gap-7 lg:grid-cols-[1.1fr_.9fr] lg:items-end"><div><h1 className="max-w-3xl text-4xl font-semibold leading-[1.02] tracking-[-.055em] sm:text-5xl">Connect the reality behind every decision.</h1><p className="mt-5 max-w-2xl text-base leading-7 text-[#667069]">Add Slack, Alibaba OSS, and GitHub as read-only evidence sources. Company Brain lets Qwen turn what changed into source-linked memory before SAG checks a release.</p></div><div className="rounded-2xl border border-dashed border-[#c5d2c5] bg-[#edf7eb] p-5"><div className="flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[.16em] text-[#16745a]"><Sparkles className="h-4 w-4" /> What this unlocks</div><p className="mt-2 text-sm leading-6 text-[#385246]">Source event → Qwen memory → deterministic safety check → named human owner.</p><p className="mt-3 text-xs leading-5 text-[#63766b]">Provider secrets are encrypted server-side. The browser never submits an organization ID or invents evidence.</p></div></div>

        <section className="mt-9 grid gap-3 md:grid-cols-3"><ProgressStep number="1" title="Prepare" detail={setupReady ? "Operator access ready" : "Start the local rehearsal"} active={!setupReady} done={setupReady} /><ProgressStep number="2" title="Connect" detail={`${configuredCount}/3 sources configured`} active={setupReady && !allConfigured} done={allConfigured} /><ProgressStep number="3" title="Prove" detail={evidenceCount >= 3 ? "Evidence is ready" : "Wait for real events"} active={setupReady && allConfigured} done={evidenceCount >= 3} /></section>

        {error && <div className="mt-6 rounded-xl border border-rose-200 bg-[#fff8f5] p-4 text-sm text-rose-900">{error}</div>}
        {notice && <div className="mt-6 rounded-xl border border-emerald-200 bg-[#f3faf0] p-4 text-sm text-[#245943]">{notice}</div>}

        {!setup?.enabled && <section className="mt-8 rounded-2xl border border-dashed border-[#d4cbb7] bg-[#fffaf0] p-6"><div className="flex gap-3"><KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-[#9b6d1d]" /><div><h2 className="font-semibold text-[#5f4316]">Start the local rehearsal helper</h2><p className="mt-1 text-sm leading-6 text-[#72592c]">Run <code className="rounded bg-white/80 px-1.5 py-0.5 font-mono text-xs">scripts\start-local.ps1</code> from the repository root, then refresh this page. It generates local operator values and keeps secrets out of the browser.</p></div></div></section>}

        {setup?.enabled && !setup?.local_rehearsal && !token && <section className="mt-8 rounded-2xl border border-dashed border-[#c9c5bb] bg-[#fffdf8] p-6"><div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div><p className="font-mono text-[10px] font-bold uppercase tracking-[.16em] text-[#16745a]">Operator access</p><h2 className="mt-2 font-semibold">Enter the local setup token to continue.</h2><p className="mt-1 text-sm text-[#69736d]">This only configures the NexaFlow rehearsal organization on this machine.</p></div><div className="flex gap-2"><input type="password" aria-label="Operator unlock token" value={tokenInput} onChange={(event) => setTokenInput(event.target.value)} placeholder="Operator token" className="min-w-0 rounded-xl border border-[#c9c6bd] bg-white px-3 py-2 text-sm" /><button type="button" disabled={!tokenInput || busy} onClick={() => void unlock()} className="inline-flex items-center gap-2 rounded-xl bg-[#113d32] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"><LockKeyhole className="h-4 w-4" />Continue</button></div></div></section>}

        {setupReady && <>
          <section className="mt-8 rounded-2xl border border-dashed border-[#c9c5bb] bg-[#fffdf8] p-6"><div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between"><div><p className="font-mono text-[10px] font-bold uppercase tracking-[.18em] text-[#69736d]">Evidence sources</p><h2 className="mt-2 text-2xl font-semibold tracking-[-.035em]">Three read-only boundaries.</h2><p className="mt-2 text-sm leading-6 text-[#69736d]">Choose a source to configure it. The selected source becomes the next input to Qwen.</p></div><p className="font-mono text-[10px] font-bold uppercase tracking-[.14em] text-[#68736c]">{configuredCount}/3 connected</p></div><div className="mt-6 grid gap-3 md:grid-cols-3">{providerOrder.map((provider, index) => { const connection = connections.find((item) => item.provider === provider); const Icon = icons[provider]; const isSelected = provider === selected; return <button key={provider} type="button" onClick={() => setSelected(provider)} className={`rounded-2xl border border-dashed p-4 text-left transition ${isSelected ? "border-[#246650] bg-[#edf7eb]" : "border-[#d6d1c6] bg-[#fbfaf6] hover:border-[#9bb7a7]"}`}><div className="flex items-start justify-between gap-2"><span className="grid h-9 w-9 place-items-center rounded-full bg-[#e8f2e8] text-[#17614b]"><Icon className="h-5 w-5" /></span>{connection?.status === "connected" ? <CheckCircle2 className="h-5 w-5 text-[#16745a]" /> : <span className="font-mono text-[10px] font-bold uppercase tracking-wide text-[#9b6d1d]">Next</span>}</div><p className="mt-4 font-mono text-[10px] font-bold tracking-[.16em] text-[#8a928c]">0{index + 1}</p><p className="mt-1 font-semibold">{providerNames[provider]}</p><p className="mt-1 text-xs text-[#69736d]">{providerRoles[provider]}</p><p className="mt-3 border-t border-dashed border-[#ddd8ce] pt-3 text-xs leading-5 text-[#69736d]">{providerEvidence(connection)}</p></button> })}</div></section>

          {selectedInfo && <ProviderCard provider={selected} info={selectedInfo} connection={selectedConnection} config={configs[selected]} values={values} busy={busy} onChange={(field, value) => setValues((current) => ({ ...current, [field]: value }))} onCopy={(value) => void copy(value)} onSave={() => void saveAndVerify()} onTest={() => void test()} onSync={selected === "alibaba_oss" ? () => void syncOSS() : undefined} />}

          <section className={`mt-8 rounded-2xl border border-dashed p-6 ${allConfigured ? "border-[#b9d2ba] bg-[#f3faf0]" : "border-[#c9c5bb] bg-[#fffdf8]"}`}><div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between"><div className="flex gap-3"><ShieldCheck className={`mt-0.5 h-5 w-5 ${allConfigured ? "text-[#16745a]" : "text-[#69736d]"}`} /><div><p className="font-mono text-[10px] font-bold uppercase tracking-[.16em] text-[#16745a]">Next handoff</p><h2 className="mt-2 font-semibold">{allConfigured ? "Sources connected. Wait for reality, then run the check." : "Connect the next source."}</h2><p className="mt-1 text-sm leading-6 text-[#5d6b62]">{allConfigured ? "Post the Slack incident, sync the OSS runbook, merge the GitHub PR, then open the console." : `Next: ${providerNames[nextProvider ?? "slack"]}.`}</p></div></div><Link to="/" className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#113d32] px-4 py-3 text-sm font-semibold text-white">Open console <ChevronRight className="h-4 w-4" /></Link></div></section>
        </>}
        <footer className="mt-16 border-t border-dashed border-[#ccc7bc] pt-6 text-xs text-[#758078]"><div className="flex flex-wrap items-center justify-between gap-3"><p>Company Brain · integration studio</p><Link to="/" className="hover:text-[#113d32]">Back to live console ↑</Link></div></footer>
      </main>
    </div>
  )
}

function ProgressStep({ number, title, detail, active, done }: { number: string; title: string; detail: string; active: boolean; done: boolean }) {
  return <div className={`rounded-2xl border border-dashed p-4 ${active ? "border-[#9bb7a7] bg-[#edf7eb]" : done ? "border-[#b9d2ba] bg-[#f3faf0]" : "border-[#d6d1c6] bg-[#fbfaf6]"}`}><div className="flex items-center gap-3"><span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-bold ${done ? "bg-[#16745a] text-white" : active ? "bg-[#113d32] text-white" : "bg-[#e7e4dc] text-[#69736d]"}`}>{done ? <Check className="h-4 w-4" /> : number}</span><div><p className="font-semibold">{title}</p><p className="text-xs text-[#69736d]">{detail}</p></div></div></div>
}

function ProviderCard({ provider, info, connection, config, values, busy, onChange, onCopy, onSave, onTest, onSync }: { provider: Provider; info: ProviderSetup; connection?: SourceConnection; config?: OperatorProviderConfig; values: Record<string, string>; busy: boolean; onChange: (field: string, value: string) => void; onCopy: (value: string) => void; onSave: () => void; onTest: () => void; onSync?: () => void }) {
  return <section className="mt-8 rounded-2xl border border-dashed border-[#c9c5bb] bg-[#fffdf8] p-6"><div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-full bg-[#e8f2e8] text-[#17614b]">{provider === "slack" ? <MessageSquareText className="h-5 w-5" /> : provider === "github" ? <Github className="h-5 w-5" /> : <FileText className="h-5 w-5" />}</span><div><p className="font-mono text-[10px] font-bold uppercase tracking-[.17em] text-[#16745a]">{providerRoles[provider]}</p><h2 className="mt-1 text-2xl font-semibold tracking-[-.035em]">{providerNames[provider]}</h2></div></div><p className="mt-4 max-w-2xl text-sm leading-6 text-[#69736d]">{connection?.status === "connected" ? "Connected. Test the boundary or update its allowlist." : "Add the server-side connection details for this read-only boundary."}</p></div><div className="flex items-center gap-2"><span className={`rounded-full border px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-wide ${connection?.status === "connected" ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-amber-200 bg-amber-50 text-amber-900"}`}>{connection?.status === "connected" ? "Connected" : "Needs setup"}</span><button type="button" onClick={() => void onCopy(info.endpoint)} className="inline-flex shrink-0 items-center gap-2 rounded-full border border-dashed border-[#c9c6bd] bg-white px-3 py-2 text-xs font-semibold text-[#36423c]"><Clipboard className="h-4 w-4" />Copy endpoint</button></div></div><div className="mt-6 grid gap-5 lg:grid-cols-[.85fr_1.15fr]"><div className="rounded-xl border border-dashed border-[#d6d1c6] bg-[#fbfaf6] p-4"><p className="font-mono text-[10px] font-bold uppercase tracking-[.14em] text-[#69736d]">Connection checklist</p><ol className="mt-3 space-y-2 text-sm leading-6 text-[#4f5e55]">{info.steps.map((step) => <li key={step} className="flex gap-2"><span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-[#16745a]" />{step}</li>)}</ol><code className="mt-4 block overflow-x-auto rounded-lg bg-[#1f2a25] px-3 py-3 font-mono text-xs text-[#dce7df]">{info.endpoint}</code></div><div className="grid gap-4 md:grid-cols-2">{info.fields.map((field) => <label key={field} className={field === "service_account_json" ? "md:col-span-2" : ""}><span className="font-mono text-[10px] font-bold uppercase tracking-[.12em] text-[#69736d]">{labels[field] ?? field}</span>{field === "service_account_json" ? <textarea value={values[field] ?? ""} onChange={(event) => onChange(field, event.target.value)} placeholder={config?.secrets[field] ? "Saved. Leave blank to keep it." : "Paste JSON once"} className="mt-2 min-h-32 w-full rounded-xl border border-[#c9c6bd] bg-white p-3 font-mono text-xs outline-none ring-[#9bb7a7] focus:ring-2" /> : <input type={field.includes("secret") || field === "token" || field === "bot_token" ? "password" : "text"} value={values[field] ?? ""} onChange={(event) => onChange(field, event.target.value)} placeholder={config?.secrets[field] ? "Saved. Leave blank to keep it." : "Enter value"} className="mt-2 w-full rounded-xl border border-[#c9c6bd] bg-white px-3 py-2 text-sm outline-none ring-[#9bb7a7] focus:ring-2" />}</label>)}</div></div><div className="mt-6 flex flex-wrap gap-3 border-t border-dashed border-[#d6d1c6] pt-5"><button type="button" disabled={busy} onClick={onSave} className="inline-flex items-center gap-2 rounded-xl bg-[#113d32] px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}Save and verify</button><button type="button" disabled={busy || connection?.status !== "connected"} onClick={onTest} className="inline-flex items-center gap-2 rounded-xl border border-dashed border-[#b9c6b9] bg-[#f3faf0] px-4 py-3 text-sm font-semibold text-[#1b5845] disabled:opacity-50"><Play className="h-4 w-4" />Test boundary</button>{onSync && <button type="button" disabled={busy || connection?.status !== "connected"} onClick={onSync} className="inline-flex items-center gap-2 rounded-xl border border-dashed border-[#c9c6bd] bg-white px-4 py-3 text-sm font-semibold text-[#36423c] disabled:opacity-50"><Cloud className="h-4 w-4" />Sync OSS now</button>}</div></section>
}
