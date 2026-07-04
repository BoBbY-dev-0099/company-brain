import { useState } from "react"
import { Bot, Loader2, ShieldAlert, Wrench, Headphones, Package } from "lucide-react"
import { apiPost } from "../lib/api"

type AgentKind = "engineering" | "support" | "product"

interface AgentDef {
  kind: AgentKind
  id: string
  name: string
  description: string
  icon: React.ReactNode
  endpoint: string
  defaultMessage: string
  defaultMetadata: string
  metadataHint?: string
}

const AGENTS: AgentDef[] = [
  {
    kind: "engineering",
    id: "engineering-agent-1",
    name: "Engineering Agent",
    description: "Reviews PRs with brain pre-flight intercept + SAG metadata support.",
    icon: <Wrench className="w-5 h-5" />,
    endpoint: "/agents/engineering/run",
    defaultMessage:
      "Increase data export chunk size to 8MB to improve throughput on large exports.",
    defaultMetadata: '{"export_chunk_size_mb": 8}',
    metadataHint: "Set export_chunk_size_mb to flip SAG (8 → suspended, 25 → active).",
  },
  {
    kind: "support",
    id: "support-agent-1",
    name: "Support Agent",
    description: "Resolves tickets using recall_skills and compile_experience.",
    icon: <Headphones className="w-5 h-5" />,
    endpoint: "/agents/support/run",
    defaultMessage:
      "Customer says their annual SaaS refund was denied after 20 days — what is our policy?",
    defaultMetadata: "{}",
  },
  {
    kind: "product",
    id: "product-agent-1",
    name: "Product Agent",
    description: "Cross-session memory for product decisions and feature tradeoffs.",
    icon: <Package className="w-5 h-5" />,
    endpoint: "/agents/product/run",
    defaultMessage:
      "Should we ship rate limiting as token bucket or fixed window for our public API?",
    defaultMetadata: '{"session_id": "demo-product-session"}',
  },
]

interface RunResult {
  response: string
  skills_used: string[]
  intercepted: boolean
  intercept_skill: string | null
  iterations: number
  session_id?: string | null
}

export default function Agents() {
  const [selected, setSelected] = useState<AgentKind>("engineering")
  const [message, setMessage] = useState(AGENTS[0].defaultMessage)
  const [metadataJson, setMetadataJson] = useState(AGENTS[0].defaultMetadata)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState("")
  const [result, setResult] = useState<RunResult | null>(null)

  const agent = AGENTS.find((a) => a.kind === selected)!

  const selectAgent = (kind: AgentKind) => {
    const def = AGENTS.find((a) => a.kind === kind)!
    setSelected(kind)
    setMessage(def.defaultMessage)
    setMetadataJson(def.defaultMetadata)
    setResult(null)
    setError("")
  }

  const runAgent = async () => {
    setBusy(true)
    setError("")
    setResult(null)
    try {
      let metadata: Record<string, unknown> = {}
      if (metadataJson.trim()) {
        metadata = JSON.parse(metadataJson)
      }
      const body: Record<string, unknown> = {
        agent_id: agent.id,
        user_message: message,
        metadata,
      }
      if (selected === "product") {
        body.user_id = "demo-user"
        if (typeof metadata.session_id === "string") {
          body.session_id = metadata.session_id
        }
      }
      const resp = await apiPost(agent.endpoint, body)
      setResult(resp)
    } catch (e: any) {
      const detail = e.response?.data?.detail
      setError(typeof detail === "string" ? detail : e.message || "Agent run failed")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Agents</h1>
        <p className="text-[#a1a1aa] text-sm mt-1">
          Run demo agents against the live brain via MCP tools (recall → intercept → compile).
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {AGENTS.map((a) => (
          <button
            key={a.kind}
            onClick={() => selectAgent(a.kind)}
            className={`text-left p-4 rounded border transition-colors ${
              selected === a.kind
                ? "border-[#22c55e] bg-[#22c55e]/10"
                : "border-[#1f1f22] bg-[#111114] hover:border-[#22c55e]/40"
            }`}
          >
            <div className="flex items-center gap-2 text-[#22c55e] mb-2">
              {a.icon}
              <span className="font-medium text-[#e4e4e7]">{a.name}</span>
            </div>
            <p className="text-xs text-[#7c7c8a] leading-relaxed">{a.description}</p>
            <p className="text-[10px] font-mono text-[#7c7c8a] mt-2">{a.id}</p>
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-4">
          <h2 className="font-medium flex items-center gap-2">
            <Bot className="w-4 h-4 text-[#22c55e]" />
            Run {agent.name}
          </h2>
          <div>
            <label className="text-xs text-[#7c7c8a] uppercase tracking-wider">Message</label>
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
              className="mt-1 w-full bg-[#050505] border border-[#1f1f22] rounded p-3 text-sm text-[#e4e4e7] focus:outline-none focus:border-[#22c55e]/50"
            />
          </div>
          <div>
            <label className="text-xs text-[#7c7c8a] uppercase tracking-wider">
              Metadata (JSON)
            </label>
            <textarea
              value={metadataJson}
              onChange={(e) => setMetadataJson(e.target.value)}
              rows={3}
              className="mt-1 w-full bg-[#050505] border border-[#1f1f22] rounded p-3 text-sm font-mono text-[#e4e4e7] focus:outline-none focus:border-[#22c55e]/50"
            />
            {agent.metadataHint && (
              <p className="text-[10px] text-[#7c7c8a] mt-1">{agent.metadataHint}</p>
            )}
          </div>
          <button
            onClick={runAgent}
            disabled={busy || !message.trim()}
            className="w-full py-2 rounded bg-[#22c55e] text-[#050505] font-medium text-sm hover:bg-[#16a34a] disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {busy ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" /> Running…
              </>
            ) : (
              "Run Agent"
            )}
          </button>
          {error && <p className="text-sm text-[#ef4444]">{error}</p>}
        </div>

        <div className="bg-[#111114] border border-[#1f1f22] rounded p-4 space-y-4 min-h-[280px]">
          <h2 className="font-medium">Response</h2>
          {!result && !busy && (
            <p className="text-sm text-[#7c7c8a]">
              Agent output appears here. Engineering agent runs SAG pre-flight before the LLM call.
            </p>
          )}
          {result && (
            <>
              {result.intercepted && (
                <div className="flex items-center gap-2 text-sm text-[#f59e0b] bg-[#f59e0b]/10 border border-[#f59e0b]/30 rounded px-3 py-2">
                  <ShieldAlert className="w-4 h-4 shrink-0" />
                  Pre-flight intercept
                  {result.intercept_skill && (
                    <span className="font-mono text-xs">({result.intercept_skill})</span>
                  )}
                </div>
              )}
              <div className="text-sm text-[#e4e4e7] whitespace-pre-wrap leading-relaxed max-h-[40vh] overflow-y-auto">
                {result.response}
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div className="bg-[#050505] rounded p-2">
                  <div className="text-[#7c7c8a]">Iterations</div>
                  <div>{result.iterations}</div>
                </div>
                <div className="bg-[#050505] rounded p-2">
                  <div className="text-[#7c7c8a]">Skills used</div>
                  <div className="font-mono text-[#22c55e] truncate">
                    {result.skills_used.length ? result.skills_used.join(", ") : "—"}
                  </div>
                </div>
              </div>
              {result.session_id && (
                <p className="text-xs text-[#7c7c8a] font-mono">session: {result.session_id}</p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
