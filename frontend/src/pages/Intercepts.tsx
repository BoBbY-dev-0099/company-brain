import { useEffect, useState } from "react"
import { ShieldAlert, CheckCircle, AlertTriangle, Ban, Play, PauseCircle } from "lucide-react"
import { apiGet } from "../lib/api"

interface Intercept {
  agent_id: string
  decision_text: string
  matched_skill: string | null
  result: string
  confidence: number
  occurred_at: string
  applicability_status?: string | null
  suspension_reason?: string | null
}

const resultIcons: Record<string, React.ReactNode> = {
  clear: <CheckCircle className="w-4 h-4 text-[#22c55e]" />,
  warn: <AlertTriangle className="w-4 h-4 text-[#f59e0b]" />,
  block: <Ban className="w-4 h-4 text-[#ef4444]" />,
  auto_execute: <Play className="w-4 h-4 text-[#3b82f6]" />,
  suspended: <PauseCircle className="w-4 h-4 text-[#f59e0b]" />,
}

const resultLabels: Record<string, string> = {
  clear: "Clear",
  warn: "Warn",
  block: "Block",
  auto_execute: "Auto-execute",
  suspended: "Suspended",
}

export default function Intercepts() {
  const [intercepts, setIntercepts] = useState<Intercept[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const data = await apiGet("/brain/intercepts")
        setIntercepts(data.intercepts || [])
      } catch {
        setIntercepts([])
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Decision Intercepts</h1>
        <div className="text-sm text-[#7c7c8a]">{intercepts.length} logged</div>
      </div>

      <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-3">
        {loading && <p className="text-sm text-[#7c7c8a]">Loading…</p>}
        {!loading && intercepts.length === 0 && (
          <div className="text-center py-8 text-[#7c7c8a]">
            <ShieldAlert className="w-8 h-8 mx-auto mb-2 text-[#22c55e]" />
            <p>No intercepts logged yet.</p>
            <p className="text-xs mt-1">Trigger a decision check to see results here.</p>
          </div>
        )}
        <div className="space-y-2">
          {intercepts.map((i, idx) => (
            <div
              key={idx}
              className="border border-[#1f1f22] rounded p-3 hover:border-[#22c55e]/30 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    {resultIcons[i.result] || <ShieldAlert className="w-4 h-4 text-[#7c7c8a]" />}
                    <span className="text-sm font-medium capitalize">
                      {resultLabels[i.result] || i.result}
                    </span>
                    <span className="text-xs text-[#7c7c8a]">
                      {(i.confidence * 100).toFixed(0)}% confidence
                    </span>
                  </div>
                  <p className="text-sm text-[#e4e4e7] truncate">{i.decision_text}</p>
                  {(i.applicability_status === "suspended" || i.result === "suspended") && i.suspension_reason && (
                    <span className="text-xs text-[#f59e0b]">Reason: {i.suspension_reason}</span>
                  )}
                  <div className="flex items-center gap-4 mt-2 text-xs text-[#7c7c8a]">
                    <span className="font-mono">{i.agent_id}</span>
                    {i.matched_skill && (
                      <span className="font-mono text-[#22c55e]">{i.matched_skill}</span>
                    )}
                    <span>{new Date(i.occurred_at).toLocaleString()}</span>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
