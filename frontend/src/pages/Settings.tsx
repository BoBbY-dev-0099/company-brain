import { useCallback, useEffect, useState } from "react"
import { Link } from "react-router-dom"
import {
  Activity,
  Brain,
  Database,
  Key,
  Loader2,
  RefreshCw,
  Shield,
  Sparkles,
  Zap,
} from "lucide-react"
import { apiGet, apiPost } from "../lib/api"

export default function Settings() {
  const [health, setHealth] = useState<any>(null)
  const [metrics, setMetrics] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [seeding, setSeeding] = useState(false)
  const [seedMsg, setSeedMsg] = useState("")

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [h, m] = await Promise.all([
        apiGet("/health"),
        apiGet("/settings/metrics"),
      ])
      setHealth(h)
      setMetrics(m.metrics)
    } catch {
      setHealth(null)
      setMetrics(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const seedDemo = async () => {
    setSeeding(true)
    setSeedMsg("")
    try {
      const resp = await apiPost("/settings/seed-demo-data", {})
      if (resp.seeded) {
        const emb =
          resp.embeddings_backfilled > 0
            ? ` (${resp.embeddings_backfilled} embeddings backfilled)`
            : ""
        setSeedMsg(`Seeded ${resp.skill_count} skills for org ${resp.org_id}.${emb}`)
      } else {
        const emb =
          resp.embeddings_backfilled > 0
            ? ` Backfilled ${resp.embeddings_backfilled} embeddings.`
            : ""
        setSeedMsg((resp.reason || "Already seeded for this org.") + emb)
      }
      load()
    } catch (e: any) {
      setSeedMsg(e.response?.data?.detail || e.message || "Seed failed")
    } finally {
      setSeeding(false)
    }
  }

  const ok = health?.status === "ok"
  const byResult = metrics?.intercept_by_result || {}

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Settings</h1>
          <p className="text-[#a1a1aa] text-sm mt-1">
            System health, efficiency metrics, and demo configuration.
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-2 text-sm text-[#22c55e] hover:underline disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-4">
          <h2 className="font-medium flex items-center gap-2">
            <Activity className="w-4 h-4 text-[#22c55e]" />
            System Health
          </h2>
          {loading && !health ? (
            <p className="text-sm text-[#7c7c8a]">Loading…</p>
          ) : (
            <div className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-[#7c7c8a]">Status</span>
                <span className={ok ? "text-[#22c55e]" : "text-[#ef4444]"}>
                  {ok ? "healthy" : "degraded"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#7c7c8a]">Version</span>
                <span className="font-mono">{health?.version ?? "—"}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#7c7c8a]">MongoDB</span>
                <span className={health?.db?.connected ? "text-[#22c55e]" : "text-[#ef4444]"}>
                  {health?.db?.connected ? "connected" : "disconnected"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#7c7c8a]">Qwen API</span>
                <span className={health?.qwen_configured ? "text-[#22c55e]" : "text-[#f59e0b]"}>
                  {health?.qwen_configured ? "configured" : "missing key"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#7c7c8a]">Embeddings</span>
                <span className={health?.embedding_healthy ? "text-[#22c55e]" : "text-[#ef4444]"}>
                  {health?.embedding_healthy ? "healthy (1024-dim)" : "unhealthy"}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#7c7c8a]">Skills compiled</span>
                <span className="font-mono">{health?.skills_compiled ?? "—"}</span>
              </div>
            </div>
          )}
        </div>

        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-4">
          <h2 className="font-medium flex items-center gap-2">
            <Zap className="w-4 h-4 text-[#22c55e]" />
            Efficiency Metrics
          </h2>
          {loading && !metrics ? (
            <p className="text-sm text-[#7c7c8a]">Loading…</p>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                <MetricCard
                  label="Governance hits"
                  value={metrics?.governance_hits ?? 0}
                  icon={<Shield className="w-4 h-4" />}
                />
                <MetricCard
                  label="Est. tokens saved"
                  value={(metrics?.est_llm_tokens_saved ?? 0).toLocaleString()}
                  icon={<Sparkles className="w-4 h-4" />}
                />
                <MetricCard
                  label="Total skills"
                  value={metrics?.total_skills ?? 0}
                  icon={<Brain className="w-4 h-4" />}
                />
                <MetricCard
                  label="Total decisions"
                  value={metrics?.total_decisions ?? 0}
                  icon={<Database className="w-4 h-4" />}
                />
              </div>
              {Object.keys(byResult).length > 0 && (
                <div>
                  <div className="text-xs text-[#7c7c8a] uppercase tracking-wider mb-2">
                    Intercepts by result
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(byResult).map(([k, v]) => (
                      <span
                        key={k}
                        className="text-xs font-mono bg-[#050505] border border-[#1f1f22] rounded px-2 py-1"
                      >
                        {k}: {String(v)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-4">
          <h2 className="font-medium flex items-center gap-2">
            <Database className="w-4 h-4 text-[#22c55e]" />
            Demo Data
          </h2>
          <p className="text-sm text-[#7c7c8a]">
            Seed 8 demo skills including the SAG-enabled{" "}
            <span className="font-mono text-[#22c55e]">data-export-large-file-timeout</span> skill.
            Idempotent — skips if your org already has skills.
          </p>
          <button
            onClick={seedDemo}
            disabled={seeding}
            className="px-4 py-2 rounded bg-[#22c55e] text-[#050505] text-sm font-medium hover:bg-[#16a34a] disabled:opacity-50 flex items-center gap-2"
          >
            {seeding ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> Seeding…
              </>
            ) : (
              "Seed Demo Data"
            )}
          </button>
          {seedMsg && <p className="text-sm text-[#a1a1aa]">{seedMsg}</p>}
        </div>

        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-4">
          <h2 className="font-medium flex items-center gap-2">
            <Key className="w-4 h-4 text-[#22c55e]" />
            Integration
          </h2>
          <ul className="text-sm space-y-2 text-[#a1a1aa]">
            <li>
              <Link to="/app/api-keys" className="text-[#22c55e] hover:underline">
                API Keys
              </Link>{" "}
              — issue <span className="font-mono">cb_live_…</span> keys for agent fleets
            </li>
            <li>
              <Link to="/app/brain" className="text-[#22c55e] hover:underline">
                Brain Explorer
              </Link>{" "}
              — SAG demo + attestation tab
            </li>
            <li>
              MCP SSE endpoint:{" "}
              <span className="font-mono text-[#e4e4e7]">/mcp/sse</span>
            </li>
            <li>
              Attestation:{" "}
              <span className="font-mono text-[#e4e4e7]">/mcp/attestation</span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  )
}

function MetricCard({
  label,
  value,
  icon,
}: {
  label: string
  value: string | number
  icon: React.ReactNode
}) {
  return (
    <div className="bg-[#050505] rounded p-3">
      <div className="flex items-center gap-2 text-[#22c55e] mb-1">{icon}</div>
      <div className="text-xs text-[#7c7c8a]">{label}</div>
      <div className="text-xl font-bold">{value}</div>
    </div>
  )
}
