import { useCallback, useEffect, useState } from "react"
import {
  ArrowLeft,
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

function errorText(error: unknown) {
  const value = error as { response?: { data?: { detail?: string } } }
  return value.response?.data?.detail || "The server could not complete that setup request."
}

function providerStatus(connection?: SourceConnection) {
  if (connection?.status === "connected") return "Settings saved"
  return "Needs setup"
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
    <div className="min-h-screen bg-[#f6f4ef] text-[#17212b]">
      <header className="border-b border-[#ddd8ce]">
        <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-5">
          <Link to="/" className="inline-flex items-center gap-2 text-sm font-semibold">
            <ArrowLeft className="h-4 w-4" /> NexaFlow console
          </Link>
          <button type="button" onClick={() => void refreshPublic()} className="inline-flex items-center gap-2 text-sm font-semibold text-[#174ea6]">
            <RefreshCw className="h-4 w-4" /> Refresh status
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-5 py-9">
        <p className="text-xs font-bold uppercase tracking-[.18em] text-[#2364d2]">Get set · connect · go</p>
        <h1 className="mt-3 max-w-3xl text-4xl font-semibold tracking-[-.05em]">Connect NexaFlow in three moves.</h1>
        <p className="mt-3 max-w-2xl text-base leading-7 text-[#5c6a7b]">Connect the three read-only sources, then run one release-safety check.</p>

        <section className="mt-7 grid gap-3 md:grid-cols-3">
          <ProgressStep number="1" title="Get set" detail={setupReady ? "Ready to connect" : "Start local setup"} active={!setupReady} done={setupReady} />
          <ProgressStep number="2" title="Connect" detail={`${configuredCount}/3 sources configured`} active={setupReady && !allConfigured} done={allConfigured} />
          <ProgressStep number="3" title="Go" detail={evidenceCount >= 3 ? "Evidence is ready" : "Run after real events arrive"} active={setupReady && allConfigured} done={evidenceCount >= 3} />
        </section>

        {error && <div className="mt-6 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900">{error}</div>}
        {notice && <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900">{notice}</div>}

        {!setup?.enabled && (
          <section className="mt-7 rounded-2xl border border-amber-200 bg-[#fffaf0] p-6">
            <div className="flex gap-3">
              <KeyRound className="mt-0.5 h-5 w-5 shrink-0 text-amber-700" />
              <div>
                <h2 className="font-semibold text-amber-950">Start the local rehearsal helper</h2>
                <p className="mt-1 text-sm leading-6 text-amber-900">From the repository root, run <code className="rounded bg-white/80 px-1.5 py-0.5">scripts\start-local.ps1</code>. It generates the local unlock values, starts the API and worker, and keeps secrets out of the browser.</p>
                <p className="mt-3 text-xs text-amber-800">After it finishes, click Refresh status. Production deployments must provide their own operator credentials.</p>
              </div>
            </div>
          </section>
        )}

        {setup?.enabled && !setup?.local_rehearsal && !token && (
          <section className="mt-7 rounded-2xl border border-[#d7dbe1] bg-[#fffdfa] p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h2 className="font-semibold">Unlock local operator setup</h2>
                <p className="mt-1 text-sm text-[#647284]">This unlock only configures the NexaFlow test company on this machine.</p>
              </div>
              <div className="flex gap-2">
                <input type="password" aria-label="Operator unlock token" value={tokenInput} onChange={(event) => setTokenInput(event.target.value)} placeholder="Operator token" className="min-w-0 rounded-xl border border-[#d7dbe1] bg-white px-3 py-2 text-sm" />
                <button type="button" disabled={!tokenInput || busy} onClick={() => void unlock()} className="inline-flex items-center gap-2 rounded-xl bg-[#17212b] px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"><LockKeyhole className="h-4 w-4" />Unlock</button>
              </div>
            </div>
          </section>
        )}

        {setupReady && (
          <>
            <section className="mt-7 rounded-2xl border border-[#ddd8ce] bg-[#fffdfa] p-5">
              <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <p className="text-xs font-bold uppercase tracking-[.14em] text-[#718096]">Connect sources</p>
                  <h2 className="mt-1 text-2xl font-semibold">Add each source once.</h2>
                </div>
                <p className="text-sm text-[#647284]">{configuredCount} of 3 configured</p>
              </div>
              <div className="mt-5 grid gap-3 md:grid-cols-3">
                {providerOrder.map((provider) => {
                  const connection = connections.find((item) => item.provider === provider)
                  const Icon = icons[provider]
                  const isSelected = provider === selected
                  return (
                    <button key={provider} type="button" onClick={() => setSelected(provider)} className={`rounded-2xl border p-4 text-left transition ${isSelected ? "border-[#2d67b4] bg-[#f0f6ff] shadow-sm" : "border-[#ddd8ce] bg-[#fffdfa] hover:border-[#9bb6da]"}`}>
                      <div className="flex items-start justify-between gap-2"><span className="grid h-9 w-9 place-items-center rounded-xl bg-[#eef3fb] text-[#265ba9]"><Icon className="h-5 w-5" /></span>{connection?.status === "connected" ? <CheckCircle2 className="h-5 w-5 text-emerald-700" /> : <span className="text-xs font-semibold text-[#8a6b24]">Setup next</span>}</div>
                      <p className="mt-4 font-semibold">{providerNames[provider]}</p>
                      <p className="mt-1 text-xs text-[#697585]">{providerStatus(connection)}</p>
                      <p className="mt-3 text-xs leading-5 text-[#697585]">{providerEvidence(connection)}</p>
                    </button>
                  )
                })}
              </div>
            </section>

            {selectedInfo && (
              <ProviderCard
                provider={selected}
                info={selectedInfo}
                connection={selectedConnection}
                config={configs[selected]}
                values={values}
                busy={busy}
                onChange={(field, value) => setValues((current) => ({ ...current, [field]: value }))}
                onCopy={(value) => void copy(value)}
                onSave={() => void saveAndVerify()}
                onTest={() => void test()}
                onSync={selected === "alibaba_oss" ? () => void syncOSS() : undefined}
              />
            )}

            <section className={`mt-7 rounded-2xl border p-5 ${allConfigured ? "border-emerald-200 bg-[#f4fbf6]" : "border-[#d7dbe1] bg-[#fffdfa]"}`}>
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex gap-3"><ShieldCheck className={`mt-0.5 h-5 w-5 ${allConfigured ? "text-emerald-700" : "text-[#657384]"}`} /><div><h2 className="font-semibold">{allConfigured ? "Sources are connected." : "Finish the three connections."}</h2><p className="mt-1 text-sm text-[#5d6b7b]">{allConfigured ? "Now create the Slack incident, sync OSS, merge the GitHub PR, and run the release check." : `Next up: ${providerNames[nextProvider ?? "slack"]}.`}</p></div></div>
                <Link to="/" className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#16386e] px-4 py-3 text-sm font-semibold text-white">Open console <ChevronRight className="h-4 w-4" /></Link>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  )
}

function ProgressStep({ number, title, detail, active, done }: { number: string; title: string; detail: string; active: boolean; done: boolean }) {
  return <div className={`rounded-2xl border p-4 ${active ? "border-[#2d67b4] bg-[#f0f6ff]" : done ? "border-emerald-200 bg-[#f4fbf6]" : "border-[#ddd8ce] bg-[#fffdfa]"}`}><div className="flex items-center gap-3"><span className={`grid h-7 w-7 place-items-center rounded-full text-xs font-bold ${done ? "bg-emerald-700 text-white" : active ? "bg-[#16386e] text-white" : "bg-[#edf0f4] text-[#647284]"}`}>{done ? <Check className="h-4 w-4" /> : number}</span><div><p className="font-semibold">{title}</p><p className="text-xs text-[#697585]">{detail}</p></div></div></div>
}

function ProviderCard({ provider, info, connection, config, values, busy, onChange, onCopy, onSave, onTest, onSync }: { provider: Provider; info: ProviderSetup; connection?: SourceConnection; config?: OperatorProviderConfig; values: Record<string, string>; busy: boolean; onChange: (field: string, value: string) => void; onCopy: (value: string) => void; onSave: () => void; onTest: () => void; onSync?: () => void }) {
  return <section className="mt-7 rounded-2xl border border-[#ddd8ce] bg-[#fffdfa] p-6"><div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between"><div><div className="flex items-center gap-2"><span className="grid h-9 w-9 place-items-center rounded-xl bg-[#eef3fb] text-[#265ba9]">{provider === "slack" ? <MessageSquareText className="h-5 w-5" /> : provider === "github" ? <Github className="h-5 w-5" /> : <FileText className="h-5 w-5" />}</span><p className="text-xs font-bold uppercase tracking-[.14em] text-[#718096]">{providerNames[provider]}</p></div><h2 className="mt-4 text-2xl font-semibold">{connection?.status === "connected" ? "Connected. Test or update it." : "Add this source"}</h2><ol className="mt-3 list-decimal space-y-1 pl-5 text-sm leading-6 text-[#5d6b7b]">{info.steps.map((step) => <li key={step}>{step}</li>)}</ol></div><button type="button" onClick={() => void onCopy(info.endpoint)} className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-[#d7dbe1] bg-white px-3 py-2 text-xs font-semibold text-[#23466f]"><Clipboard className="h-4 w-4" />Copy endpoint</button></div><code className="mt-5 block overflow-x-auto rounded-xl bg-[#17212b] px-4 py-3 text-xs text-[#e6eefb]">{info.endpoint}</code><div className="mt-6 grid gap-4 md:grid-cols-2">{info.fields.map((field) => <label key={field} className={field === "service_account_json" ? "md:col-span-2" : ""}><span className="text-xs font-semibold text-[#536170]">{labels[field] ?? field}</span>{field === "service_account_json" ? <textarea value={values[field] ?? ""} onChange={(event) => onChange(field, event.target.value)} placeholder={config?.secrets[field] ? "Saved. Leave blank to keep it." : "Paste JSON once"} className="mt-1.5 min-h-32 w-full rounded-xl border border-[#d7dbe1] bg-white p-3 font-mono text-xs" /> : <input type={field.includes("secret") || field === "token" || field === "bot_token" ? "password" : "text"} value={values[field] ?? ""} onChange={(event) => onChange(field, event.target.value)} placeholder={config?.secrets[field] ? "Saved. Leave blank to keep it." : "Enter value"} className="mt-1.5 w-full rounded-xl border border-[#d7dbe1] bg-white px-3 py-2 text-sm" />}</label>)}</div><div className="mt-5 flex flex-wrap gap-3"><button type="button" disabled={busy} onClick={onSave} className="inline-flex items-center gap-2 rounded-xl bg-[#16386e] px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}Save and verify</button><button type="button" disabled={busy || connection?.status !== "connected"} onClick={onTest} className="inline-flex items-center gap-2 rounded-xl border border-[#c7d3e2] bg-white px-4 py-3 text-sm font-semibold text-[#23466f] disabled:opacity-50"><Play className="h-4 w-4" />Test again</button>{onSync && <button type="button" disabled={busy || connection?.status !== "connected"} onClick={onSync} className="inline-flex items-center gap-2 rounded-xl border border-[#c7d3e2] bg-white px-4 py-3 text-sm font-semibold text-[#23466f] disabled:opacity-50"><Cloud className="h-4 w-4" />Sync OSS now</button>}</div></section>
}
