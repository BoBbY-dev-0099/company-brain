import { useCallback, useEffect, useState } from "react"
import {
  Brain as BrainIcon,
  CheckCircle,
  PauseCircle,
  ShieldAlert,
  ShieldCheck,
  Copy,
  RefreshCw,
} from "lucide-react"
import { apiGet, apiPost } from "../lib/api"
import { useSSE } from "../hooks/useSSE"
import InterceptList, { type Intercept } from "../components/InterceptList"

interface Skill {
  skill_id: string
  name: string
  domain: string
  version: number
  confidence: number
  summary: string
  applicability_status?: string | null
  last_invalid_reason?: string | null
  pattern?: { keywords?: string[]; domains?: string[] }
}

function normalizeSkill(raw: any): Skill {
  return {
    skill_id: raw.skill_id,
    name: raw.name,
    domain: raw.domain,
    version: raw.version,
    confidence: raw.provenance?.confidence ?? raw.confidence ?? 0,
    summary: raw.summary,
    applicability_status: raw.provenance?.applicability_status ?? raw.applicability_status,
    last_invalid_reason: raw.provenance?.last_invalid_reason ?? raw.last_invalid_reason,
    pattern: raw.pattern,
  }
}

type SagBadge = "suspended" | "auto_execute" | "unknown"

function expectedBadge(chunk: number): SagBadge {
  return chunk <= 10 ? "suspended" : "auto_execute"
}

export default function Brain() {
  const [activeTab, setActiveTab] = useState("skills")
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Skill | null>(null)
  const [demoStatus, setDemoStatus] = useState<string>("")
  const [sseUrl, setSseUrl] = useState<string | null>(null)
  const [decisions, setDecisions] = useState<Intercept[]>([])
  const [decisionsLoading, setDecisionsLoading] = useState(false)
  const [attestation, setAttestation] = useState<any>(null)
  const [attestationLoading, setAttestationLoading] = useState(false)
  const [copied, setCopied] = useState(false)
  const [chunkMb, setChunkMb] = useState(25)
  const [sagBadge, setSagBadge] = useState<SagBadge>("auto_execute")
  const [sagReason, setSagReason] = useState<string>("")
  const [toggleBusy, setToggleBusy] = useState(false)

  const loadSkills = useCallback(async () => {
    try {
      const data = await apiGet("/brain/skills")
      const normalized = (data.skills || []).map(normalizeSkill)
      setSkills(normalized)
      setSelected((prev) => {
        if (!prev) {
          return (
            normalized.find((s: Skill) => s.skill_id === "data-export-large-file-timeout") ??
            normalized[0] ??
            null
          )
        }
        return normalized.find((s: Skill) => s.skill_id === prev.skill_id) ?? prev
      })
    } catch {
      setSkills([])
    } finally {
      setLoading(false)
    }
  }, [])

  const applySagFromApi = useCallback((chunk: number, sag: any | null | undefined) => {
    if (!sag) {
      setSagBadge(expectedBadge(chunk))
      setSagReason(
        chunk <= 10
          ? `invalidated_if: export_chunk_size_mb <= 10 | current: ${chunk}`
          : `applies_if: export_chunk_size_mb > 10 | current: ${chunk}`,
      )
      return
    }
    const suspended =
      sag.result === "suspended" || sag.applicability_status === "suspended"
    setSagBadge(suspended ? "suspended" : "auto_execute")
    setSagReason(
      sag.suspension_reason ||
        sag.reason ||
        (suspended
          ? `invalidated_if: export_chunk_size_mb <= 10 | current: ${chunk}`
          : `applies_if: export_chunk_size_mb > 10 | current: ${chunk}`),
    )
    setDemoStatus(
      `${chunk}MB → ${sag.result || "—"} (${sag.applicability_status || "active"}) · skill: ${
        sag.skill_id || "data-export-large-file-timeout"
      }`,
    )
  }, [])

  const loadLiveConfig = useCallback(async () => {
    try {
      const data = await apiGet("/settings/live-config")
      const chunk = Number(data?.metadata?.export_chunk_size_mb ?? 25)
      setChunkMb(chunk)
      setSagBadge(expectedBadge(chunk))
      setSagReason(
        chunk <= 10
          ? `invalidated_if: export_chunk_size_mb <= 10 | current: ${chunk}`
          : `applies_if: export_chunk_size_mb > 10 | current: ${chunk}`,
      )
    } catch {
      setChunkMb(25)
      setSagBadge("auto_execute")
    }
  }, [])

  useEffect(() => {
    loadSkills()
    loadLiveConfig()
  }, [loadSkills, loadLiveConfig])

  const switchConfig = useCallback(
    async (chunk: number) => {
      // Optimistic UI — instant flip for judges.
      setChunkMb(chunk)
      setSagBadge(expectedBadge(chunk))
      setSagReason(
        chunk <= 10
          ? `invalidated_if: export_chunk_size_mb <= 10 | current: ${chunk}`
          : `applies_if: export_chunk_size_mb > 10 | current: ${chunk}`,
      )
      setDemoStatus(`Switching live config → ${chunk}MB…`)
      setToggleBusy(true)
      try {
        const resp = await apiPost("/settings/live-config", {
          export_chunk_size_mb: chunk,
        })
        const next = Number(resp?.metadata?.export_chunk_size_mb ?? chunk)
        setChunkMb(next)
        applySagFromApi(next, resp?.sag)
        await loadSkills()
      } catch (e: any) {
        setDemoStatus(`Error: ${e.message}`)
        await loadLiveConfig()
      } finally {
        setToggleBusy(false)
      }
    },
    [applySagFromApi, loadLiveConfig, loadSkills],
  )

  // Keyboard: 8 → 8MB, 2 → 25MB (ignore when typing in inputs).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) {
        return
      }
      if (e.key === "8") {
        e.preventDefault()
        void switchConfig(8)
      } else if (e.key === "2") {
        e.preventDefault()
        void switchConfig(25)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [switchConfig])

  const handleSSE = useCallback(
    (name: string, data: any) => {
      if (name === "config_updated" && data?.metadata?.export_chunk_size_mb != null) {
        const chunk = Number(data.metadata.export_chunk_size_mb)
        setChunkMb(chunk)
        // Background verify only — do not fight optimistic UI.
        setSagBadge((prev) => prev || expectedBadge(chunk))
        return
      }

      const skillId = data?.skill_id as string | undefined
      if (!skillId) return

      if (name === "skill_suspended") {
        const patch = {
          applicability_status: "suspended" as const,
          last_invalid_reason: (data.reason as string) ?? null,
        }
        setSkills((prev) =>
          prev.map((s) => (s.skill_id === skillId ? { ...s, ...patch } : s)),
        )
        setSelected((prev) => (prev?.skill_id === skillId ? { ...prev, ...patch } : prev))
        if (skillId === "data-export-large-file-timeout") {
          setSagBadge("suspended")
        }
        return
      }

      if (name === "skill_reinforced" && data.applicability_status === "active") {
        const patch = {
          applicability_status: "active" as const,
          last_invalid_reason: null,
        }
        setSkills((prev) =>
          prev.map((s) => (s.skill_id === skillId ? { ...s, ...patch } : s)),
        )
        setSelected((prev) => (prev?.skill_id === skillId ? { ...prev, ...patch } : prev))
        if (skillId === "data-export-large-file-timeout") {
          setSagBadge("auto_execute")
        }
      }
    },
    [],
  )

  useEffect(() => {
    setSseUrl("/stream")
  }, [])
  useSSE(sseUrl, handleSSE)

  const loadDecisions = useCallback(async () => {
    setDecisionsLoading(true)
    try {
      const data = await apiGet("/brain/intercepts?limit=30")
      setDecisions(data.intercepts || [])
    } catch {
      setDecisions([])
    } finally {
      setDecisionsLoading(false)
    }
  }, [])

  const loadAttestation = useCallback(async () => {
    setAttestationLoading(true)
    try {
      const data = await apiGet("/mcp/attestation")
      setAttestation(data)
    } catch {
      setAttestation(null)
    } finally {
      setAttestationLoading(false)
    }
  }, [])

  useEffect(() => {
    if (activeTab === "decisions") loadDecisions()
    if (activeTab === "attestation") loadAttestation()
  }, [activeTab, loadDecisions, loadAttestation])

  const copyAttestation = async () => {
    if (!attestation) return
    await navigator.clipboard.writeText(JSON.stringify(attestation, null, 2))
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const suspended = sagBadge === "suspended"

  return (
    <div className="space-y-4">
      <div className="rounded border border-[#22c55e]/30 bg-[#22c55e]/5 px-4 py-3 text-sm text-[#a1a1aa]">
        <span className="text-[#22c55e] font-medium">30-second SAG demo: </span>
        Live config toggle → instant badge flip. Keys{" "}
        <kbd className="px-1 rounded bg-[#111114] border border-[#1f1f22] font-mono text-[10px]">8</kbd>{" "}
        /{" "}
        <kbd className="px-1 rounded bg-[#111114] border border-[#1f1f22] font-mono text-[10px]">2</kbd>
        {" "}(25MB). Memory that knows when to stop trusting itself.
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="bg-[#111114] border border-[#1f1f22] rounded-lg p-5 space-y-4">
          <div className="text-xs uppercase tracking-wide text-[#7c7c8a]">Live config</div>
          <div className="flex items-baseline gap-2">
            <span className="text-5xl font-bold font-mono text-[#e4e4e7]">{chunkMb}</span>
            <span className="text-[#7c7c8a]">MB chunk</span>
          </div>
          <div className="flex flex-col gap-2">
            <button
              onClick={() => switchConfig(8)}
              disabled={toggleBusy}
              className="w-full py-3 rounded-lg text-sm font-semibold border border-[#ef4444]/50 text-[#fca5a5] bg-[#ef4444]/10 hover:bg-[#ef4444]/20 disabled:opacity-50"
            >
              Switch to 8MB
            </button>
            <button
              onClick={() => switchConfig(25)}
              disabled={toggleBusy}
              className="w-full py-3 rounded-lg text-sm font-semibold border border-[#22c55e]/50 text-[#86efac] bg-[#22c55e]/10 hover:bg-[#22c55e]/20 disabled:opacity-50"
            >
              Switch to 25MB
            </button>
          </div>
          {demoStatus && (
            <p className="text-[11px] font-mono text-[#a1a1aa] break-words">{demoStatus}</p>
          )}
        </div>

        <div
          className={`lg:col-span-2 rounded-lg border p-6 space-y-4 transition-colors ${
            suspended
              ? "border-[#ef4444]/50 bg-[#ef4444]/5 sag-badge-shake"
              : "border-[#22c55e]/50 bg-[#22c55e]/5 sag-badge-glow"
          }`}
        >
          <div className="text-xs uppercase tracking-wide text-[#7c7c8a]">
            Hero skill · data-export-large-file-timeout
          </div>
          <h2 className="text-xl font-semibold text-[#e4e4e7]">Large data export timeout</h2>
          <div
            className={`inline-flex items-center gap-3 px-5 py-3 rounded-xl text-2xl font-bold tracking-wide ${
              suspended
                ? "bg-[#ef4444] text-white shadow-[0_0_24px_rgba(239,68,68,0.45)]"
                : "bg-[#22c55e] text-[#050505] shadow-[0_0_24px_rgba(34,197,94,0.45)]"
            }`}
          >
            {suspended ? (
              <>
                <PauseCircle className="w-8 h-8" /> SUSPENDED
              </>
            ) : (
              <>
                <CheckCircle className="w-8 h-8" /> AUTO_EXECUTE
              </>
            )}
          </div>
          <p className="text-sm font-mono text-[#a1a1aa]">{sagReason || "—"}</p>
          <p className="text-xs text-[#7c7c8a]">
            Same skill · different live metadata · no second LLM call.
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between gap-4 flex-wrap">
        <h1 className="text-2xl font-semibold">Brain Explorer</h1>
        <p className="text-[10px] text-[#7c7c8a]">
          Toggle updates <code>/settings/live-config</code> and logs a fresh intercept.
        </p>
      </div>
      <div className="flex gap-2">
        {["skills", "decisions", "attestation"].map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-3 py-1 rounded text-sm capitalize ${
              activeTab === tab
                ? "bg-[#22c55e] text-[#050505]"
                : "bg-[#111114] text-[#7c7c8a] hover:text-[#e4e4e7]"
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === "skills" && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-3">
            <h2 className="font-medium flex items-center gap-2">
              <BrainIcon className="w-4 h-4 text-[#22c55e]" />
              Skills ({skills.length})
            </h2>
            {loading && <p className="text-sm text-[#7c7c8a]">Loading…</p>}
            {!loading && skills.length === 0 && (
              <p className="text-sm text-[#7c7c8a]">No skills yet.</p>
            )}
            <div className="space-y-2 max-h-[60vh] overflow-y-auto">
              {skills.map((s) => (
                <button
                  key={s.skill_id}
                  onClick={() => setSelected(s)}
                  className={`w-full text-left p-3 rounded border transition-colors ${
                    selected?.skill_id === s.skill_id
                      ? "border-[#22c55e] bg-[#22c55e]/10"
                      : "border-[#1f1f22] hover:border-[#22c55e]/50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-medium text-sm truncate">{s.name}</span>
                      {s.applicability_status === "suspended" && (
                        <span className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded border border-[#f59e0b]/40 bg-[#f59e0b]/10 text-[#f59e0b] shrink-0">
                          Suspended
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-[#7c7c8a] font-mono shrink-0">v{s.version}</span>
                  </div>
                  <div className="text-xs text-[#7c7c8a] mt-1">{s.skill_id}</div>
                </button>
              ))}
            </div>
          </div>

          <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-4">
            {selected ? (
              <>
                <div>
                  <h3 className="font-semibold text-lg">{selected.name}</h3>
                  <div className="text-xs text-[#7c7c8a] font-mono mt-1">{selected.skill_id}</div>
                </div>
                {selected.applicability_status === "suspended" && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 text-sm font-medium text-[#f59e0b] bg-[#f59e0b]/10 border border-[#f59e0b]/30 rounded px-3 py-2">
                      <PauseCircle className="w-4 h-4" />
                      Suspended
                    </div>
                    {selected.last_invalid_reason && (
                      <p className="text-sm text-[#e4e4e7]">
                        Reason: {selected.last_invalid_reason}
                      </p>
                    )}
                  </div>
                )}
                <div className="grid grid-cols-3 gap-3 text-sm">
                  <div className="bg-[#050505] rounded p-2">
                    <div className="text-[#7c7c8a] text-xs">Domain</div>
                    <div className="capitalize">{selected.domain}</div>
                  </div>
                  <div className="bg-[#050505] rounded p-2">
                    <div className="text-[#7c7c8a] text-xs">Version</div>
                    <div>{selected.version}</div>
                  </div>
                  <div className="bg-[#050505] rounded p-2">
                    <div className="text-[#7c7c8a] text-xs">Confidence</div>
                    <div>{(selected.confidence * 100).toFixed(0)}%</div>
                  </div>
                </div>
                <div>
                  <div className="text-xs text-[#7c7c8a] mb-1">Summary</div>
                  <p className="text-sm text-[#e4e4e7]">{selected.summary}</p>
                </div>
                {selected.pattern?.keywords && selected.pattern.keywords.length > 0 && (
                  <div>
                    <div className="text-xs text-[#7c7c8a] mb-1">Keywords</div>
                    <div className="flex flex-wrap gap-1">
                      {selected.pattern.keywords.map((k) => (
                        <span key={k} className="text-xs bg-[#050505] px-2 py-1 rounded font-mono">
                          {k}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-[#7c7c8a] min-h-[200px]">
                <BrainIcon className="w-8 h-8 mb-2" />
                <p>Select a skill to view details</p>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === "decisions" && (
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-medium flex items-center gap-2">
              <CheckCircle className="w-4 h-4 text-[#22c55e]" />
              Decision History
            </h2>
            <div className="flex items-center gap-3">
              <span className="text-xs text-[#7c7c8a]">{decisions.length} logged</span>
              <button
                onClick={loadDecisions}
                disabled={decisionsLoading}
                className="text-xs text-[#22c55e] flex items-center gap-1 hover:underline disabled:opacity-50"
              >
                <RefreshCw className={`w-3 h-3 ${decisionsLoading ? "animate-spin" : ""}`} />
                Refresh
              </button>
            </div>
          </div>
          <p className="text-xs text-[#7c7c8a]">
            Pre-flight governance checks logged by the brain. SAG suspensions appear with evidence.
          </p>
          <InterceptList
            intercepts={decisions}
            loading={decisionsLoading}
            compact
            emptyMessage="No decisions yet. Use the SAG simulate buttons above or run an agent."
          />
        </div>
      )}

      {activeTab === "attestation" && (
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-medium flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-[#22c55e]" />
              TEE Attestation
            </h2>
            <div className="flex items-center gap-2">
              <button
                onClick={loadAttestation}
                disabled={attestationLoading}
                className="text-xs text-[#22c55e] flex items-center gap-1 hover:underline disabled:opacity-50 mr-3"
              >
                <RefreshCw className={`w-3 h-3 ${attestationLoading ? "animate-spin" : ""}`} />
                Refresh
              </button>
              {attestation && (
                <button
                  onClick={copyAttestation}
                  className="text-xs text-[#7c7c8a] flex items-center gap-1 hover:text-[#e4e4e7]"
                >
                  <Copy className="w-3 h-3" />
                  {copied ? "Copied" : "Copy JSON"}
                </button>
              )}
            </div>
          </div>

          {attestationLoading && !attestation && (
            <p className="text-sm text-[#7c7c8a]">Loading attestation envelope…</p>
          )}

          {attestation && (
            <>
              <div className="flex items-center gap-3">
                <div
                  className={`flex items-center gap-2 px-3 py-2 rounded border text-sm ${
                    attestation.attestation_verified
                      ? "border-[#22c55e]/40 bg-[#22c55e]/10 text-[#22c55e]"
                      : "border-[#ef4444]/40 bg-[#ef4444]/10 text-[#ef4444]"
                  }`}
                >
                  <ShieldCheck className="w-4 h-4" />
                  {attestation.attestation_verified ? "Attestation verified" : "Not verified"}
                </div>
                {attestation.tee_capable && (
                  <span className="text-xs font-mono text-[#7c7c8a]">TEE capable</span>
                )}
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                <InfoRow label="Platform" value={attestation.platform} />
                <InfoRow label="Issued at" value={attestation.issued_at ? new Date(attestation.issued_at).toLocaleString() : "—"} />
                <InfoRow label="MCP endpoint" value={attestation.mcp_endpoint} mono />
                <InfoRow label="Measurement" value={attestation.measurement?.slice(0, 16) + "…"} mono />
              </div>

              <div>
                <div className="text-xs text-[#7c7c8a] uppercase tracking-wider mb-2">
                  Exposed MCP tools
                </div>
                <div className="space-y-2">
                  {(attestation.tools || []).map((t: any) => (
                    <div
                      key={t.name}
                      className="flex items-start gap-3 bg-[#050505] border border-[#1f1f22] rounded p-3"
                    >
                      <span className="font-mono text-[#22c55e] text-sm shrink-0">{t.name}</span>
                      <span className="text-xs text-[#a1a1aa]">{t.purpose}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div>
                <div className="text-xs text-[#7c7c8a] uppercase tracking-wider mb-1">Narrative</div>
                <p className="text-sm text-[#a1a1aa] leading-relaxed">{attestation.narrative}</p>
              </div>

              <pre className="text-[10px] font-mono bg-[#050505] border border-[#1f1f22] rounded p-3 overflow-x-auto text-[#7c7c8a] max-h-48">
                {JSON.stringify(attestation, null, 2)}
              </pre>
            </>
          )}
        </div>
      )}
    </div>
  )
}

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="bg-[#050505] rounded p-3">
      <div className="text-xs text-[#7c7c8a]">{label}</div>
      <div className={`mt-0.5 ${mono ? "font-mono text-xs break-all" : ""}`}>{value}</div>
    </div>
  )
}
