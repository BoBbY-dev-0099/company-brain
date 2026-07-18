import { Link } from "react-router-dom"
import { ArrowRight, Bot, FileSearch, ShieldCheck, Sparkles, UserRound } from "lucide-react"

export default function Landing() {
  return (
    <div className="min-h-screen bg-[#050505] text-[#e4e4e7]">
      <header className="fixed z-10 w-full border-b border-[#1f1f22] bg-[#050505]/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <div className="flex items-center gap-2 text-[#22c55e]"><Sparkles className="h-5 w-5" /><span className="font-semibold">Company Brain</span></div>
          <nav className="flex items-center gap-4 text-sm"><Link to="/app/connect" className="text-[#a1a1aa] hover:text-[#e4e4e7]">How it connects</Link><Link to="/app/inbox" className="font-medium text-[#86efac] hover:underline">Decision Queue</Link></nav>
        </div>
      </header>

      <main>
        <section className="mx-auto max-w-5xl px-4 pb-16 pt-28 md:pb-24 md:pt-36">
          <p className="mb-4 text-sm font-mono text-[#86efac]">Qwen Cloud Hackathon 2026 / Governed operational memory</p>
          <h1 className="max-w-4xl text-4xl font-bold leading-tight tracking-tight text-[#fafafa] md:text-6xl">Company Brain stops unsafe company actions when reality changes.</h1>
          <p className="mt-6 max-w-3xl text-lg leading-8 text-[#b4b4bb] md:text-xl">It turns source-backed evidence into governed memory, checks that memory against live context, and brings the right person in before a release, refund, or rollout proceeds.</p>
          <div className="mt-8 flex flex-wrap items-center gap-3"><Link to="/app/inbox" className="inline-flex items-center gap-2 rounded bg-[#22c55e] px-5 py-3 font-semibold text-[#050505] hover:bg-[#4ade80]">See why a release was stopped <ArrowRight className="h-4 w-4" /></Link><Link to="/app/connect" className="rounded border border-[#2a2a30] bg-[#111114] px-5 py-3 font-medium text-[#e4e4e7] hover:border-[#22c55e]/50">How it connects</Link></div>
          <p className="mt-5 text-xs text-[#7c7c8a]">Qwen compiles evidence into memory. SAG checks the live condition deterministically. Humans approve every external action.</p>
        </section>

        <section className="border-y border-[#1f1f22] bg-[#09090b]">
          <div className="mx-auto max-w-5xl px-4 py-12 md:py-16"><div className="max-w-2xl"><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#86efac]">Judge route</p><h2 className="mt-2 text-2xl font-semibold text-[#f4f4f5]">One clear story in the first 90 seconds</h2></div><div className="mt-8 grid gap-4 md:grid-cols-3"><JourneyStep number="1" icon={<FileSearch className="h-5 w-5" />} title="See the evidence" text="A merged PR and live runtime signal make a previously safe release assumption false." /><JourneyStep number="2" icon={<ShieldCheck className="h-5 w-5" />} title="See why it stopped" text="Qwen memory is separated from source facts, then SAG shows the deterministic safety verdict." /><JourneyStep number="3" icon={<UserRound className="h-5 w-5" />} title="See who owns it" text="The next action goes to a named human owner. Sandbox outcomes stay isolated from canonical memory." /></div></div>
        </section>

        <section className="mx-auto max-w-5xl px-4 py-16 md:py-20"><div className="grid gap-8 md:grid-cols-[0.9fr_1.1fr]"><div><p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#86efac]">Built for existing operations</p><h2 className="mt-2 text-2xl font-semibold text-[#f4f4f5]">A governed checkpoint, not another agent silo.</h2><p className="mt-3 text-sm leading-6 text-[#a1a1aa]">Companies can connect evidence, call a workflow contract, or let an agent ask for a DecisionBrief through MCP. The product is explicit about which paths are connected, ready, fixtures, or previews.</p><Link to="/app/connect" className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-[#86efac] hover:underline">Explore connection boundaries <ArrowRight className="h-4 w-4" /></Link></div><div className="rounded-2xl border border-[#1f1f22] bg-[#111114] p-5"><div className="grid gap-3 sm:grid-cols-[1fr_auto_1fr]"><MiniFlow icon={<FileSearch className="h-4 w-4" />} label="Company source" /><ArrowRight className="mx-auto hidden h-4 w-4 self-center text-[#686871] sm:block" /><MiniFlow icon={<Bot className="h-4 w-4" />} label="Agent or workflow" /></div><div className="my-3 border-l border-dashed border-[#2a2a30] pl-4 text-xs leading-5 text-[#a1a1aa]"><span className="font-semibold text-[#86efac]">Company Brain</span><br />Evidence freshness, Qwen memory, deterministic SAG, and a human-owned decision brief.</div><div className="grid gap-3 sm:grid-cols-[1fr_auto_1fr]"><MiniFlow icon={<ShieldCheck className="h-4 w-4" />} label="Safe recommendation" /><ArrowRight className="mx-auto hidden h-4 w-4 self-center text-[#686871] sm:block" /><MiniFlow icon={<UserRound className="h-4 w-4" />} label="Human confirmation" /></div></div></div></section>
      </main>

      <footer className="border-t border-[#1f1f22] py-8 text-center text-sm text-[#7c7c8a]">Company Brain / Qwen Cloud Hackathon 2026</footer>
    </div>
  )
}

function JourneyStep({ number, icon, title, text }: { number: string; icon: React.ReactNode; title: string; text: string }) {
  return <article className="rounded-xl border border-[#1f1f22] bg-[#111114] p-5"><div className="flex items-center gap-3"><span className="flex h-7 w-7 items-center justify-center rounded-full bg-[#22c55e]/10 text-xs font-semibold text-[#86efac]">{number}</span><span className="text-[#86efac]">{icon}</span></div><h3 className="mt-4 font-semibold text-[#f4f4f5]">{title}</h3><p className="mt-2 text-sm leading-6 text-[#a1a1aa]">{text}</p></article>
}

function MiniFlow({ icon, label }: { icon: React.ReactNode; label: string }) {
  return <div className="flex items-center justify-center gap-2 rounded-lg border border-[#1f1f22] bg-[#09090b] px-3 py-3 text-xs font-medium text-[#c4c4ca]"><span className="text-[#86efac]">{icon}</span>{label}</div>
}
