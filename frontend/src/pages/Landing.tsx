import { Link } from "react-router-dom"
import { useAuth, useUser } from "@clerk/clerk-react"
import { ArrowRight, BarChart3, Brain, ShieldAlert, Sparkles, Zap } from "lucide-react"

export default function Landing() {
  const { isSignedIn, signOut } = useAuth()
  const { user } = useUser()

  return (
    <div className="min-h-screen bg-[#050505] text-[#e4e4e7]">
      <header className="border-b border-[#1f1f22] bg-[#050505]/80 backdrop-blur fixed w-full z-10">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2 text-[#22c55e]">
            <Sparkles className="w-5 h-5" />
            <span className="font-semibold">Company Brain</span>
          </div>
          <nav className="flex items-center gap-4 text-sm">
            <a href="#features" className="text-[#a1a1aa] hover:text-[#e4e4e7]">Features</a>
            <a href="#open-source" className="text-[#a1a1aa] hover:text-[#e4e4e7]">Open Source</a>
            {isSignedIn ? (
              <>
                <Link to="/app/dashboard" className="text-[#22c55e] hover:underline">
                  Dashboard
                </Link>
                <button
                  onClick={() => signOut()}
                  className="text-[#a1a1aa] hover:text-[#e4e4e7]"
                >
                  Sign Out {user?.firstName ? `(${user.firstName})` : ""}
                </button>
              </>
            ) : (
              <Link to="/sign-in" className="text-[#22c55e] hover:underline">Sign In</Link>
            )}
          </nav>
        </div>
      </header>

      <section className="pt-32 pb-20 px-4 text-center max-w-3xl mx-auto">
        <h1 className="text-4xl md:text-5xl font-bold mb-6">
          The operating memory primitive for agent fleets
        </h1>
        <p className="text-lg text-[#a1a1aa] mb-8">
          Company Brain compiles every agent interaction into versioned, decaying skills,
          then pre-flight intercepts risky decisions before your LLM calls.
        </p>
        <div className="flex items-center justify-center gap-4">
          <Link
            to="/sign-up"
            className="bg-[#22c55e] hover:bg-[#16a34a] text-[#050505] font-medium rounded px-6 py-3 flex items-center gap-2"
          >
            Get Started <ArrowRight className="w-4 h-4" />
          </Link>
          <a
            href="#features"
            className="border border-[#1f1f22] hover:border-[#22c55e] text-[#e4e4e7] rounded px-6 py-3"
          >
            Live Demo
          </a>
        </div>
      </section>

      <section id="features" className="py-20 px-4 max-w-6xl mx-auto">
        <h2 className="text-2xl font-semibold text-center mb-12">What Company Brain Does</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-[#111114] border border-[#1f1f22] rounded p-6 space-y-3">
            <Brain className="w-8 h-8 text-[#22c55e]" />
            <h3 className="font-semibold">Compile to Skills</h3>
            <p className="text-sm text-[#a1a1aa]">
              Every agent event is compiled into a versioned skill via Qwen 3,
              complete with embeddings for semantic retrieval.
            </p>
          </div>
          <div className="bg-[#111114] border border-[#1f1f22] rounded p-6 space-y-3">
            <ShieldAlert className="w-8 h-8 text-[#22c55e]" />
            <h3 className="font-semibold">Pre-flight Intercept</h3>
            <p className="text-sm text-[#a1a1aa]">
              Before the LLM is called, the brain checks if a prior skill
              should block, warn, or auto-execute the decision.
            </p>
          </div>
          <div className="bg-[#111114] border border-[#1f1f22] rounded p-6 space-y-3">
            <Zap className="w-8 h-8 text-[#22c55e]" />
            <h3 className="font-semibold">Decay & Reinforce</h3>
            <p className="text-sm text-[#a1a1aa]">
              Skills decay over time, but every non-clear interception
              reinforces confidence. Cross-session memory persists.
            </p>
          </div>
          <div className="bg-[#111114] border border-[#1f1f22] rounded p-6 space-y-3">
            <BarChart3 className="w-8 h-8 text-[#22c55e]" />
            <h3 className="font-semibold">Real-time Dashboard</h3>
            <p className="text-sm text-[#a1a1aa]">
              Monitor skills, agents, intercepts, and events in real-time
              via SSE live feed and metrics cards.
            </p>
          </div>
          <div className="bg-[#111114] border border-[#1f1f22] rounded p-6 space-y-3">
            <Sparkles className="w-8 h-8 text-[#22c55e]" />
            <h3 className="font-semibold">TEE Attestation</h3>
            <p className="text-sm text-[#a1a1aa]">
              Enterprise deployments can run inside Intel TDX enclaves
              with remote attestation for trusted execution.
            </p>
          </div>
          <div className="bg-[#111114] border border-[#1f1f22] rounded p-6 space-y-3">
            <Brain className="w-8 h-8 text-[#22c55e]" />
            <h3 className="font-semibold">Multi-tenant SaaS</h3>
            <p className="text-sm text-[#a1a1aa]">
              Clerk auth, org-scoped data, agent API keys, and a
              production React frontend with onboarding wizard.
            </p>
          </div>
        </div>
      </section>

      <section id="open-source" className="py-20 px-4 max-w-3xl mx-auto text-center">
        <h2 className="text-2xl font-semibold mb-4">Open Source</h2>
        <p className="text-[#a1a1aa] mb-6">
          Built during the Qwen Cloud Global AI Hackathon 2026 (MemoryAgent track).
          MIT licensed — fork it, run it, extend it.
        </p>
        <Link
          to="/sign-up"
          className="bg-[#22c55e] hover:bg-[#16a34a] text-[#050505] font-medium rounded px-6 py-3 inline-flex items-center gap-2"
        >
          Get Started <ArrowRight className="w-4 h-4" />
        </Link>
      </section>

      <footer className="border-t border-[#1f1f22] py-8 text-center text-sm text-[#7c7c8a]">
        © 2026 Company Brain — Qwen Cloud Hackathon
      </footer>
    </div>
  )
}
