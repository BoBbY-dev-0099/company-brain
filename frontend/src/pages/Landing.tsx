import { useEffect, useState } from "react"
import { ArrowRight, Boxes, CircleAlert, FlaskConical, ShieldCheck, Sparkles } from "lucide-react"
import { Link } from "react-router-dom"
import { getDemoModules, type DemoModule } from "../lib/api"

const iconByModule: Record<string, typeof Sparkles> = {
  workflow: FlaskConical,
  "release-safety": ShieldCheck,
  "money-safety": CircleAlert,
  "rollout-safety": Boxes,
}

function moduleTone(module: DemoModule): string {
  if (module.kind === "playground") return "border-[#2f5eeb]/30 bg-[#e7edff] text-[#2148c7]"
  if (module.id === "money-safety") return "border-[#c77a17]/30 bg-[#fff0d6] text-[#9a590b]"
  if (module.id === "rollout-safety") return "border-[#8c3e82]/25 bg-[#f7e7f2] text-[#6f2b67]"
  return "border-[#b84036]/25 bg-[#fce9e6] text-[#96332b]"
}

export default function Landing() {
  const [modules, setModules] = useState<DemoModule[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void getDemoModules()
      .then((payload) => setModules(payload.modules))
      .catch(() => setError("The judge modules are unavailable. Please retry the server connection."))
  }, [])

  return (
    <div className="min-h-screen bg-[#f5f1e8] text-[#17212b]">
      <header className="border-b border-[#d9d3c8] bg-[#f5f1e8]/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
          <Link to="/" className="flex items-center gap-2 font-semibold tracking-tight text-[#17212b]"><span className="flex h-8 w-8 items-center justify-center rounded-lg bg-[#17212b] text-[#f5f1e8]"><Sparkles className="h-4 w-4" /></span>Company Brain</Link>
          <Link to="/app/connect" className="text-sm font-medium text-[#39506a] hover:text-[#17212b]">Technical proof</Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-5 pb-14 pt-12 md:pt-20">
        <section className="max-w-3xl">
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#2f5eeb]">Governed operational memory</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.045em] text-[#17212b] md:text-6xl">Stop unsafe actions when reality changes.</h1>
          <p className="mt-5 max-w-2xl text-lg leading-8 text-[#52606d]">Choose a real operational decision. Company Brain checks evidence, Qwen memory, and live conditions before a human acts.</p>
        </section>

        {error ? <div className="mt-10 rounded-2xl border border-[#b84036]/30 bg-[#fce9e6] p-5 text-sm text-[#96332b]">{error}</div> : (
          <section aria-label="Judge modules" className="mt-10 grid gap-4 md:grid-cols-2">
            {modules.length === 0 ? Array.from({ length: 4 }).map((_, index) => <div key={index} className="min-h-56 animate-pulse rounded-3xl border border-[#ddd6cb] bg-white/60 p-6" />) : modules.map((module) => {
              const Icon = iconByModule[module.id] ?? Sparkles
              return <Link key={module.id} to={module.route} className="group flex min-h-60 flex-col rounded-3xl border border-[#ddd6cb] bg-[#fffcf7] p-6 shadow-[0_18px_55px_rgba(52,45,35,0.08)] transition hover:-translate-y-1 hover:border-[#a6b5d5] hover:shadow-[0_22px_60px_rgba(47,94,235,0.12)]">
                <div className="flex items-start justify-between gap-4"><span className={`flex h-11 w-11 items-center justify-center rounded-2xl border ${moduleTone(module)}`}><Icon className="h-5 w-5" /></span><span className="rounded-full border border-[#ded7cb] bg-[#f8f5ef] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-[#687383]">{module.status.replaceAll("_", " ")}</span></div>
                <div className="mt-7"><h2 className="text-2xl font-semibold tracking-tight text-[#17212b]">{module.title}</h2><p className="mt-2 max-w-md text-sm leading-6 text-[#586575]">{module.summary}</p></div>
                <span className="mt-auto inline-flex items-center gap-2 pt-8 text-sm font-semibold text-[#2148c7]">{module.primary_action}<ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" /></span>
              </Link>
            })}
          </section>
        )}

        <p className="mt-8 text-xs text-[#6b7280]">Qwen compiles evidence into an ephemeral memory candidate. Deterministic SAG checks live context. Every external action remains human-approved.</p>
      </main>
    </div>
  )
}
