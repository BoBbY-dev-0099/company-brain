import { useEffect, useState } from "react"
import { Activity, RefreshCw, Clock } from "lucide-react"
import { Link } from "react-router-dom"
import { apiGet } from "../../lib/api"

export default function BrainHealthStatus() {
  const [health, setHealth] = useState<any>(null)
  const [ts, setTs] = useState<string>("--")

  const fetchHealth = async () => {
    try {
      const data = await apiGet("/health")
      setHealth(data)
      setTs(new Date().toLocaleTimeString())
    } catch {
      setHealth({ status: "degraded" })
    }
  }

  useEffect(() => {
    fetchHealth()
    const id = setInterval(fetchHealth, 30000)
    return () => clearInterval(id)
  }, [])

  const ok = health?.status === "ok"

  return (
    <div className="bg-[#17171a] rounded p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold text-[#7c7c8a] uppercase tracking-wider">
          Brain Health
        </div>
        <button onClick={fetchHealth} className="text-[#22c55e] text-xs flex items-center gap-1">
          <RefreshCw className="w-3 h-3" /> Refresh
        </button>
      </div>
      <div className="flex items-center gap-2 text-sm font-mono">
        <Activity className={`w-4 h-4 ${ok ? "text-[#22c55e]" : "text-[#ef4444]"}`} />
        <span className={ok ? "text-[#22c55e]" : "text-[#ef4444]"}>
          {ok ? "🟢 healthy" : "🔴 degraded"}
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs text-[#7c7c8a] font-mono">
        <Clock className="w-3 h-3" />
        <span>Last check: {ts}</span>
      </div>
      <div className="flex gap-2 mt-1">
        <Link to="/app/brain" className="text-xs text-[#22c55e] hover:underline">View Details</Link>
        <Link to="/app/events" className="text-xs text-[#22c55e] hover:underline">View Logs</Link>
      </div>
    </div>
  )
}
