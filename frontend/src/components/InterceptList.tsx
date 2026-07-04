import { ShieldAlert, CheckCircle, AlertTriangle, Ban, Play, PauseCircle } from "lucide-react"

export interface Intercept {
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

type Props = {
  intercepts: Intercept[]
  loading?: boolean
  emptyMessage?: string
  compact?: boolean
}

export default function InterceptList({
  intercepts,
  loading = false,
  emptyMessage = "No decisions logged yet.",
  compact = false,
}: Props) {
  if (loading) {
    return <p className="text-sm text-[#7c7c8a]">Loading…</p>
  }

  if (intercepts.length === 0) {
    return (
      <div className={`text-center text-[#7c7c8a] ${compact ? "py-6" : "py-8"}`}>
        <ShieldAlert className="w-8 h-8 mx-auto mb-2 text-[#22c55e]" />
        <p className="text-sm">{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {intercepts.map((i, idx) => (
        <div
          key={`${i.occurred_at}-${idx}`}
          className="border border-[#1f1f22] rounded p-3 hover:border-[#22c55e]/30 transition-colors"
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                {resultIcons[i.result] || <ShieldAlert className="w-4 h-4 text-[#7c7c8a]" />}
                <span className="text-sm font-medium capitalize">
                  {resultLabels[i.result] || i.result}
                </span>
                <span className="text-xs text-[#7c7c8a]">
                  {(i.confidence * 100).toFixed(0)}% confidence
                </span>
              </div>
              <p className={`text-sm text-[#e4e4e7] ${compact ? "line-clamp-2" : ""}`}>
                {i.decision_text}
              </p>
              {(i.applicability_status === "suspended" || i.result === "suspended") &&
                i.suspension_reason && (
                  <p className="text-xs text-[#f59e0b] mt-1">Reason: {i.suspension_reason}</p>
                )}
              <div className="flex items-center gap-4 mt-2 text-xs text-[#7c7c8a] flex-wrap">
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
  )
}
