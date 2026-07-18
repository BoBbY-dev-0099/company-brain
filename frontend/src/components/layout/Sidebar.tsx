import { useEffect, useState } from "react"
import { Link, useLocation } from "react-router-dom"
import {
  Brain,
  Key,
  Megaphone,
  Menu,
  PlugZap,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Users,
  X,
  Zap,
} from "lucide-react"
import BrainHealthStatus from "./BrainHealthStatus"

type NavigationItem = {
  to: string
  label: string
  icon: typeof Brain
}

export default function Sidebar() {
  const location = useLocation()
  const [open, setOpen] = useState(false)

  useEffect(() => { setOpen(false) }, [location.pathname])

  const primaryLinks: NavigationItem[] = [
    { to: "/app/inbox", label: "Decision Queue", icon: ShieldCheck },
    { to: "/app/connect", label: "Connect", icon: PlugZap },
  ]
  const technicalLinks: NavigationItem[] = [
    { to: "/app/dashboard", label: "System dashboard", icon: Zap },
    { to: "/app/brain", label: "Brain", icon: Brain },
    { to: "/app/intercepts", label: "Audit history", icon: ShieldAlert },
    { to: "/app/agents", label: "Agents", icon: Users },
    { to: "/app/events", label: "Events", icon: Megaphone },
    { to: "/app/api-keys", label: "API Keys", icon: Key },
  ]
  const settingsLinks: NavigationItem[] = [{ to: "/app/settings", label: "Settings", icon: Settings }]

  const navItem = (item: NavigationItem) => {
    const isActive = location.pathname === item.to
    return <Link key={item.to} to={item.to} className={`flex items-center gap-2 rounded px-3 py-2 font-medium transition-colors ${isActive ? "bg-[#22c55e] text-[#050505]" : "text-[#7c7c8a] hover:bg-[#111114] hover:text-[#e4e4e7]"}`}><item.icon className="h-4 w-4" />{item.label}</Link>
  }

  const panel = <aside className="flex h-full w-60 max-w-[85vw] flex-col justify-between border-r border-[#1f1f22] bg-[#111114] p-4"><div><div className="mb-6 flex items-center justify-between gap-2"><div className="flex items-center gap-2 text-[#22c55e]"><Sparkles className="h-5 w-5" /><span className="font-semibold text-[#e4e4e7]">Company Brain</span></div><button type="button" className="rounded p-1 text-[#7c7c8a] hover:text-[#e4e4e7] md:hidden" aria-label="Close menu" onClick={() => setOpen(false)}><X className="h-5 w-5" /></button></div><nav className="space-y-1">{primaryLinks.map(navItem)}</nav><div className="mt-5 border-t border-[#1f1f22] pt-4"><p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.14em] text-[#686871]">Technical proof</p><nav className="space-y-1">{technicalLinks.map(navItem)}</nav></div><div className="mt-4 border-t border-[#1f1f22] pt-4"><nav className="space-y-1">{settingsLinks.map(navItem)}</nav></div></div><div className="space-y-3"><BrainHealthStatus /><div className="space-y-1 border-t border-[#1f1f22] pt-3 text-xs text-[#7c7c8a]"><div className="font-mono">fixture: judge-demo-v1</div><div>canonical evidence to sandbox replays</div></div></div></aside>

  return <><div className="fixed inset-x-0 top-0 z-40 flex items-center gap-3 border-b border-[#1f1f22] bg-[#050505]/95 px-3 py-2 backdrop-blur md:hidden"><button type="button" className="rounded border border-[#1f1f22] p-2 text-[#e4e4e7]" aria-label="Open menu" onClick={() => setOpen(true)}><Menu className="h-5 w-5" /></button><span className="text-sm font-semibold text-[#e4e4e7]">Company Brain</span><span className="ml-auto font-mono text-[10px] text-[#7c7c8a]">judge-demo-v1</span></div><div className="sticky top-0 hidden h-screen shrink-0 md:block">{panel}</div>{open && <div className="fixed inset-0 z-50 flex md:hidden"><button type="button" className="absolute inset-0 bg-black/60" aria-label="Close overlay" onClick={() => setOpen(false)} /><div className="relative z-10 h-full shadow-xl">{panel}</div></div>}</>
}
