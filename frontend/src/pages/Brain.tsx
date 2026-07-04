import { useCallback, useEffect, useState } from "react"
import { useAuth } from "@clerk/clerk-react"
import { Brain as BrainIcon, CheckCircle, PauseCircle, ShieldAlert } from "lucide-react"
import { apiGet, apiPost } from "../lib/api"
import { useSSE } from "../hooks/useSSE"

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

export default function Brain() {
  const [activeTab, setActiveTab] = useState("skills")
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Skill | null>(null)
  const [demoStatus, setDemoStatus] = useState<string>("")
  const [demoBusy, setDemoBusy] = useState(false)
  const [sseUrl, setSseUrl] = useState<string | null>(null)

  const { getToken } = useAuth()

  const loadSkills = useCallback(async () => {
    try {
      const data = await apiGet("/brain/skills")
      const normalized = (data.skills || []).map(normalizeSkill)
      setSkills(normalized)
      setSelected((prev) => {
        if (!prev) return prev
        return normalized.find((s: Skill) => s.skill_id === prev.skill_id) ?? prev
      })
    } catch {
      setSkills([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadSkills()
  }, [loadSkills])

  const handleSSE = useCallback((name: string, data: any) => {
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
    }
  }, [])

  useEffect(() => {
    let active = true
    getToken()
      .then((token) => {
        if (!active || !token) return
        setSseUrl(`/stream?jwt=${encodeURIComponent(token)}`)
      })
      .catch(() => setSseUrl(null))
    return () => {
      active = false
    }
  }, [getToken])
  useSSE(sseUrl, handleSSE)

  const triggerSagDemo = useCallback(async (chunkSize: number) => {
    setDemoBusy(true)
    setDemoStatus(`Sending decision with export_chunk_size_mb=${chunkSize}...`)
    try {
      const resp = await apiPost("/decisions/check", {
        agent_id: "eng-01",
        decision_text: "Increase data export chunk size to improve throughput",
        decision_type: "pr_review",
        metadata: { export_chunk_size_mb: chunkSize },
      })
      setDemoStatus(`Result: ${resp.result} | ${resp.applicability_status || "active"}`)
    } catch (e: any) {
      setDemoStatus(`Error: ${e.message}`)
    } finally {
      setDemoBusy(false)
    }
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Brain Explorer</h1>
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-2">
            {demoStatus && (
              <span className="text-xs text-[#7c7c8a]">{demoStatus}</span>
            )}
            <button
              onClick={() => triggerSagDemo(8)}
              disabled={demoBusy}
              className="px-2 py-1 rounded text-xs border border-[#f59e0b]/40 text-[#f59e0b] hover:bg-[#f59e0b]/10 disabled:opacity-50"
            >
              Simulate: Small Chunk Config (8MB)
            </button>
            <button
              onClick={() => triggerSagDemo(25)}
              disabled={demoBusy}
              className="px-2 py-1 rounded text-xs border border-[#22c55e]/40 text-[#22c55e] hover:bg-[#22c55e]/10 disabled:opacity-50"
            >
              Simulate: Large Chunk Config (25MB)
            </button>
          </div>
          <p className="text-[10px] text-[#7c7c8a]">
            These simulate a live config check against the data-export-large-file-timeout skill's precondition.
          </p>
        </div>
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
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4">
          <h2 className="font-medium flex items-center gap-2 mb-3">
            <CheckCircle className="w-4 h-4 text-[#22c55e]" />
            Decision History
          </h2>
          <p className="text-sm text-[#7c7c8a]">Decision history integration coming soon.</p>
        </div>
      )}

      {activeTab === "attestation" && (
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4">
          <h2 className="font-medium flex items-center gap-2 mb-3">
            <ShieldAlert className="w-4 h-4 text-[#22c55e]" />
            TEE Attestation
          </h2>
          <p className="text-sm text-[#7c7c8a]">Trusted execution environment attestation coming soon.</p>
        </div>
      )}
    </div>
  )
}
