import { Link, useLocation } from "react-router-dom"
import { Brain, KeyRound, Menu, ShieldCheck, Workflow } from "lucide-react"
import { useState } from "react"

const links = [
  { to: "/", label: "Reality Console", icon: ShieldCheck },
  { to: "/app/connect", label: "Integration Studio", icon: Workflow },
  { to: "/app/memory", label: "Memory Ledger", icon: Brain },
  { to: "/app/audit", label: "Decision Audit", icon: ShieldCheck },
  { to: "/app/api-keys", label: "API Keys", icon: KeyRound },
]

export default function Sidebar() {
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const panel = <aside className="h-full w-64 border-r border-[#d9d3c8] bg-[#fffcf7] p-4"><Link to="/" className="flex items-center gap-2 font-semibold"><span className="grid h-8 w-8 place-items-center rounded-lg bg-[#17212b] text-white"><Brain className="h-4 w-4" /></span>Company Brain</Link><p className="mt-2 px-1 text-xs leading-5 text-[#708090]">Technical proof</p><nav className="mt-5 space-y-1">{links.map((item) => { const Icon = item.icon; const active = location.pathname === item.to; return <Link onClick={() => setOpen(false)} key={item.to} to={item.to} className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium ${active ? "bg-[#17212b] text-white" : "text-[#52606d] hover:bg-[#f0ece4]"}`}><Icon className="h-4 w-4" />{item.label}</Link> })}</nav><p className="mt-8 border-t border-[#e5ddd0] pt-4 text-[10px] leading-5 text-[#8190a0]">Sources are read-only. MCP returns decisions only. Humans own external actions.</p></aside>
  return <><button onClick={() => setOpen(true)} className="fixed left-3 top-3 z-40 rounded-lg border border-[#d9d3c8] bg-[#fffcf7] p-2 text-[#17212b] md:hidden" aria-label="Open navigation"><Menu className="h-5 w-5" /></button><div className="sticky top-0 hidden h-screen shrink-0 md:block">{panel}</div>{open && <div className="fixed inset-0 z-50 flex md:hidden"><button className="absolute inset-0 bg-black/30" onClick={() => setOpen(false)} aria-label="Close navigation" /><div className="relative z-10 h-full shadow-xl">{panel}</div></div>}</>
}
