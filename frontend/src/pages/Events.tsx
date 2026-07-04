import { useCallback, useEffect, useState } from "react"
import {
  Brain,
  Clock,
  Loader2,
  Megaphone,
  Plus,
  RefreshCw,
  Sparkles,
  User,
} from "lucide-react"
import { apiGet, apiPost } from "../lib/api"

interface BrainEvent {
  event_id: string
  agent_id: string
  event_type: string
  content: string
  outcome?: string
  occurred_at: string
  skill_compiled?: string | null
  metadata?: Record<string, unknown>
}

const EVENT_TYPES = [
  "ticket_resolved",
  "pr_reviewed",
  "incident_postmortem",
  "policy_decision",
  "feature_shipped",
]

export default function Events() {
  const [events, setEvents] = useState<BrainEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState("")
  const [success, setSuccess] = useState("")
  const [showForm, setShowForm] = useState(false)

  const [agentId, setAgentId] = useState("support-agent-1")
  const [eventType, setEventType] = useState("ticket_resolved")
  const [content, setContent] = useState(
    "Customer refund denied after 20 days on annual plan — applied prorated refund per SaaS policy.",
  )
  const [outcome, setOutcome] = useState("Resolved with prorated credit issued.")

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await apiGet("/brain/events?limit=50")
      setEvents(data.events || [])
    } catch {
      setEvents([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const submitEvent = async () => {
    if (!content.trim()) return
    setSubmitting(true)
    setError("")
    setSuccess("")
    try {
      const eventId = `evt-${Date.now().toString(36)}`
      const resp = await apiPost("/events", {
        event_id: eventId,
        agent_id: agentId,
        event_type: eventType,
        content: content.trim(),
        outcome: outcome.trim(),
      })
      setSuccess(
        `Compiled skill ${resp.skill_id} (v${resp.version}) — ${resp.name}`,
      )
      setShowForm(false)
      load()
    } catch (e: any) {
      const detail = e.response?.data?.detail
      setError(typeof detail === "string" ? detail : e.message || "Submit failed")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Events</h1>
          <p className="text-[#a1a1aa] text-sm mt-1">
            Raw agent experiences compiled into durable skills via Qwen.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={load}
            disabled={loading}
            className="flex items-center gap-2 text-sm text-[#22c55e] hover:underline disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
          <button
            onClick={() => setShowForm((v) => !v)}
            className="flex items-center gap-2 px-3 py-1.5 rounded bg-[#22c55e] text-[#050505] text-sm font-medium hover:bg-[#16a34a]"
          >
            <Plus className="w-4 h-4" />
            Compile Event
          </button>
        </div>
      </div>

      {success && (
        <div className="flex items-center gap-2 text-sm text-[#22c55e] bg-[#22c55e]/10 border border-[#22c55e]/30 rounded px-3 py-2">
          <Sparkles className="w-4 h-4 shrink-0" />
          {success}
        </div>
      )}

      {showForm && (
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-4">
          <h2 className="font-medium flex items-center gap-2">
            <Megaphone className="w-4 h-4 text-[#22c55e]" />
            Submit Raw Event
          </h2>
          <p className="text-xs text-[#7c7c8a]">
            POST /events — Qwen compiles this into a skill and propagates it to the fleet.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-[#7c7c8a] uppercase tracking-wider">Agent ID</label>
              <input
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                className="mt-1 w-full bg-[#050505] border border-[#1f1f22] rounded p-2 text-sm font-mono focus:outline-none focus:border-[#22c55e]/50"
              />
            </div>
            <div>
              <label className="text-xs text-[#7c7c8a] uppercase tracking-wider">Event type</label>
              <select
                value={eventType}
                onChange={(e) => setEventType(e.target.value)}
                className="mt-1 w-full bg-[#050505] border border-[#1f1f22] rounded p-2 text-sm focus:outline-none focus:border-[#22c55e]/50"
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="text-xs text-[#7c7c8a] uppercase tracking-wider">Content</label>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={4}
              className="mt-1 w-full bg-[#050505] border border-[#1f1f22] rounded p-3 text-sm focus:outline-none focus:border-[#22c55e]/50"
            />
          </div>
          <div>
            <label className="text-xs text-[#7c7c8a] uppercase tracking-wider">Outcome</label>
            <textarea
              value={outcome}
              onChange={(e) => setOutcome(e.target.value)}
              rows={2}
              className="mt-1 w-full bg-[#050505] border border-[#1f1f22] rounded p-3 text-sm focus:outline-none focus:border-[#22c55e]/50"
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={submitEvent}
              disabled={submitting || !content.trim()}
              className="px-4 py-2 rounded bg-[#22c55e] text-[#050505] text-sm font-medium hover:bg-[#16a34a] disabled:opacity-50 flex items-center gap-2"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" /> Compiling…
                </>
              ) : (
                "Compile to Skill"
              )}
            </button>
            <button
              onClick={() => setShowForm(false)}
              className="text-sm text-[#7c7c8a] hover:text-[#e4e4e7]"
            >
              Cancel
            </button>
          </div>
          {error && <p className="text-sm text-[#ef4444]">{error}</p>}
        </div>
      )}

      <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-medium flex items-center gap-2">
            <Clock className="w-4 h-4 text-[#22c55e]" />
            Event Timeline
          </h2>
          <span className="text-xs text-[#7c7c8a]">{events.length} events</span>
        </div>

        {loading && <p className="text-sm text-[#7c7c8a]">Loading…</p>}

        {!loading && events.length === 0 && (
          <div className="text-center py-10 text-[#7c7c8a]">
            <Megaphone className="w-8 h-8 mx-auto mb-2 text-[#22c55e]" />
            <p className="text-sm">No events yet.</p>
            <p className="text-xs mt-1">
              Submit a raw experience or run an agent with compile_experience.
            </p>
          </div>
        )}

        <div className="space-y-3">
          {events.map((ev) => (
            <div
              key={ev.event_id}
              className="border border-[#1f1f22] rounded p-4 hover:border-[#22c55e]/30 transition-colors"
            >
              <div className="flex items-start justify-between gap-4 flex-wrap">
                <div className="flex-1 min-w-0 space-y-2">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-xs font-mono bg-[#050505] border border-[#1f1f22] rounded px-2 py-0.5 text-[#22c55e]">
                      {ev.event_type}
                    </span>
                    {ev.skill_compiled && (
                      <span className="flex items-center gap-1 text-xs text-[#22c55e]">
                        <Brain className="w-3 h-3" />
                        <span className="font-mono">{ev.skill_compiled}</span>
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-[#e4e4e7] leading-relaxed">{ev.content}</p>
                  {ev.outcome && (
                    <p className="text-xs text-[#a1a1aa]">
                      <span className="text-[#7c7c8a]">Outcome:</span> {ev.outcome}
                    </p>
                  )}
                  <div className="flex items-center gap-4 text-xs text-[#7c7c8a] flex-wrap">
                    <span className="flex items-center gap-1">
                      <User className="w-3 h-3" />
                      <span className="font-mono">{ev.agent_id}</span>
                    </span>
                    <span className="font-mono">{ev.event_id}</span>
                    <span>{new Date(ev.occurred_at).toLocaleString()}</span>
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
