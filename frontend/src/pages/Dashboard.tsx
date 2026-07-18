import { useEffect, useState } from "react"
import { Brain, CheckCircle, Clock, ShieldAlert } from "lucide-react"
import { apiGet } from "../lib/api"
import { useSSE } from "../hooks/useSSE"

export default function Dashboard() {
  const [metrics, setMetrics] = useState<any>(null)
  const [recentEvents, setRecentEvents] = useState<any[]>([])
  const [topSkills, setTopSkills] = useState<any[]>([])
  const [liveEvents, setLiveEvents] = useState<any[]>([])

  useEffect(() => {
    async function load() {
      try {
        const m = await apiGet("/settings/metrics")
        setMetrics(m.metrics)
      } catch {
        // ignore
      }
      try {
        const events = await apiGet("/brain/skills")
        setTopSkills(events.skills?.slice(0, 5) || [])
      } catch {
        // ignore
      }
      try {
        const ev = await apiGet("/settings/metrics")
        setRecentEvents(ev.last_event ? [ev.last_event] : [])
      } catch {
        // ignore
      }
    }
    load()
  }, [])

  const handleSSE = (name: string, data: unknown) => {
    setLiveEvents((prev) => [{ name, data, ts: Date.now() }, ...prev].slice(0, 50))
  }

  // SSE requires a long-lived agent API key (EventSource cannot send headers).
  // We'll keep the feed UI but only connect when a key is available.
  useSSE(null, handleSSE)

  return (
    <div className="space-y-6">
      <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <p className="text-sm text-[#7c7c8a] mt-1">
            Operating memory for agent fleets — demo org is clean and seeded for SAG.
          </p>
        </div>
        <a
          href="/app/brain"
          className="text-sm text-[#22c55e] hover:underline font-medium"
        >
          → 30s demo: Brain · 8MB suspend / 25MB auto
        </a>
      </div>

      <div className="rounded border border-[#1f1f22] bg-[#111114] px-4 py-3 text-sm text-[#a1a1aa]">
        <span className="text-[#e4e4e7] font-medium">Judge script: </span>
        Brain → ① 8MB (suspended) → ② 25MB (auto_execute) → Intercepts → Agents Engineering.
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4">
          <div className="flex items-center gap-2 text-[#22c55e] mb-2">
            <Brain className="w-5 h-5" />
            <div className="text-sm font-medium">Total Skills</div>
          </div>
          <div className="text-2xl font-bold">{metrics?.total_skills ?? "--"}</div>
        </div>
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4">
          <div className="flex items-center gap-2 text-[#22c55e] mb-2">
            <CheckCircle className="w-5 h-5" />
            <div className="text-sm font-medium">Active Skills</div>
          </div>
          <div className="text-2xl font-bold">{metrics?.active_skills ?? "--"}</div>
        </div>
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4">
          <div className="flex items-center gap-2 text-[#22c55e] mb-2">
            <ShieldAlert className="w-5 h-5" />
            <div className="text-sm font-medium">Decisions Today</div>
          </div>
          <div className="text-2xl font-bold">{metrics?.decisions_today ?? "--"}</div>
        </div>
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4">
          <div className="flex items-center gap-2 text-[#22c55e] mb-2">
            <Clock className="w-5 h-5" />
            <div className="text-sm font-medium">Avg Confidence</div>
          </div>
          <div className="text-2xl font-bold">
            {metrics?.avg_confidence != null
              ? `${(metrics.avg_confidence * 100).toFixed(0)}%`
              : "--"}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-3">
          <h2 className="font-medium">Top Skills</h2>
          {topSkills.length === 0 && <p className="text-sm text-[#7c7c8a]">No skills yet.</p>}
          <div className="space-y-2">
            {topSkills.map((s: any) => (
              <div key={s.skill_id} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[#22c55e]">{s.skill_id}</span>
                  <span className="text-[#a1a1aa]">{s.name}</span>
                </div>
                <span className="font-mono text-[#7c7c8a]">v{s.version}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-3">
          <h2 className="font-medium">Recent Events</h2>
          {recentEvents.length === 0 && <p className="text-sm text-[#7c7c8a]">No recent events.</p>}
          <div className="space-y-2">
            {recentEvents.map((e: any, i: number) => (
              <div key={i} className="text-sm text-[#a1a1aa] font-mono truncate">
                {JSON.stringify(e)}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-3">
        <h2 className="font-medium">Live SSE Feed</h2>
        <div className="h-40 overflow-y-auto space-y-1 text-xs font-mono">
          {liveEvents.length === 0 && <p className="text-[#7c7c8a]">Waiting for events…</p>}
          {liveEvents.map((e, i) => (
            <div key={e.ts + i} className="flex items-center gap-2">
              <span className="text-[#22c55e]">{e.name}</span>
              <span className="text-[#7c7c8a] truncate">{JSON.stringify(e.data)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
