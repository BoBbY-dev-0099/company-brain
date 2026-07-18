import { Link } from "react-router-dom"
import { ArrowRight, Brain, ShieldAlert, Sparkles, Zap } from "lucide-react"

export default function Landing() {
  return (
    <div className="min-h-screen bg-[#050505] text-[#e4e4e7]">
      <header className="border-b border-[#1f1f22] bg-[#050505]/80 backdrop-blur fixed w-full z-10">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2 text-[#22c55e]">
            <Sparkles className="w-5 h-5" />
            <span className="font-semibold">Company Brain</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <a href="#demo" className="text-[#a1a1aa] hover:text-[#e4e4e7]">
              30s demo
            </a>
            <Link to="/app/inbox" className="text-[#22c55e] hover:underline">
              Open Inbox
            </Link>
          </nav>
        </div>
      </header>

      <section className="pt-28 pb-16 px-4 max-w-4xl mx-auto">
        <p className="text-[#22c55e] text-sm font-mono mb-4">
          Qwen Cloud Hackathon 2026 · MemoryAgent
        </p>
        <h1 className="text-4xl md:text-5xl font-bold mb-4 leading-tight">
          Company Brain
        </h1>
        <p className="text-xl md:text-2xl text-[#e4e4e7] mb-4 font-medium">
          Most agents remember. This one knows when to{" "}
          <span className="text-[#f59e0b]">stop trusting</span> what it remembers.
        </p>
        <p className="text-base text-[#a1a1aa] mb-8 max-w-2xl">
          A memory-and-governance layer for agent fleets: compile experience into
          versioned skills, intercept decisions before the LLM acts, and suspend
          skills when live config proves them stale — no second LLM call.
        </p>
        <div className="flex flex-wrap items-center gap-4">
          <Link
            to="/app/inbox"
            className="bg-[#22c55e] hover:bg-[#16a34a] text-[#050505] font-medium rounded px-6 py-3 flex items-center gap-2"
          >
            Open the risk inbox <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            to="/app/dashboard"
            className="border border-[#1f1f22] hover:border-[#22c55e] text-[#e4e4e7] rounded px-6 py-3"
          >
            Technical dashboard
          </Link>
        </div>
      </section>

      <section id="demo" className="py-12 px-4 max-w-4xl mx-auto border-t border-[#1f1f22]">
        <h2 className="text-xl font-semibold mb-4">First 30 seconds (judges)</h2>
        <ol className="space-y-3 text-[#a1a1aa] text-sm md:text-base list-decimal list-inside">
          <li>
            Open <span className="text-[#e4e4e7]">Operations</span> and inspect a
            source-backed workflow card with its server-returned decision.
          </li>
          <li>
            Select <span className="text-[#22c55e]">Why this decision?</span> to
            follow evidence, Qwen inference, memory, and the deterministic SAG trace.
          </li>
          <li>
            Record a human next step. Demo fixtures remain labeled and isolated from canonical memory.
          </li>
        </ol>
        <Link
          to="/app/inbox"
          className="inline-flex mt-6 text-[#22c55e] hover:underline items-center gap-1 text-sm"
        >
          Open Operations <ArrowRight className="w-3 h-3" />
        </Link>
      </section>

      <section className="py-16 px-4 max-w-6xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="border border-[#1f1f22] rounded p-6 space-y-2">
            <Brain className="w-7 h-7 text-[#22c55e]" />
            <h3 className="font-semibold">Compile</h3>
            <p className="text-sm text-[#a1a1aa]">
              Qwen turns agent events into versioned skills with embeddings.
            </p>
          </div>
          <div className="border border-[#1f1f22] rounded p-6 space-y-2">
            <ShieldAlert className="w-7 h-7 text-[#22c55e]" />
            <h3 className="font-semibold">Intercept + SAG</h3>
            <p className="text-sm text-[#a1a1aa]">
              Pre-flight check vs live metadata before block / warn / auto-execute.
            </p>
          </div>
          <div className="border border-[#1f1f22] rounded p-6 space-y-2">
            <Zap className="w-7 h-7 text-[#22c55e]" />
            <h3 className="font-semibold">Plug in via MCP</h3>
            <p className="text-sm text-[#a1a1aa]">
              Any fleet calls REST or MCP — demo agents are just three examples.
            </p>
          </div>
        </div>
      </section>

      <footer className="border-t border-[#1f1f22] py-8 text-center text-sm text-[#7c7c8a]">
        © 2026 Company Brain — Qwen Cloud Hackathon
      </footer>
    </div>
  )
}
