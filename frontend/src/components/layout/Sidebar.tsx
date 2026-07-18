import { useEffect, useState } from "react"
import { useLocation, Link } from "react-router-dom"
import {
  Brain,
  ShieldAlert,
  Users,
  Zap,
  Settings,
  Key,
  Megaphone,
  Sparkles,
  Menu,
  ShieldCheck,
  X,
} from "lucide-react"
import BrainHealthStatus from "./BrainHealthStatus"

export default function Sidebar() {
  const location = useLocation()
  const [open, setOpen] = useState(false)

  useEffect(() => {
    setOpen(false)
  }, [location.pathname])

  const links = [
    { to: "/app/inbox", label: "Operations", icon: ShieldCheck },
    { to: "/app/dashboard", label: "Dashboard", icon: Zap },
    { to: "/app/brain", label: "Brain", icon: Brain },
    { to: "/app/intercepts", label: "Intercepts", icon: ShieldAlert },
    { to: "/app/agents", label: "Agents", icon: Users },
    { to: "/app/events", label: "Events", icon: Megaphone },
    { to: "/app/api-keys", label: "API Keys", icon: Key },
  ]

  const settingsLinks = [
    { to: "/app/settings", label: "Settings", icon: Settings },
  ]

  const navItem = (item: (typeof links)[0]) => {
    const isActive = location.pathname === item.to
    return (
      <Link
        key={item.to}
        to={item.to}
        className={`flex items-center gap-2 px-3 py-2 rounded transition-colors font-medium ${
          isActive
            ? "bg-[#22c55e] text-[#050505]"
            : "text-[#7c7c8a] hover:text-[#e4e4e7] hover:bg-[#111114]"
        }`}
      >
        <item.icon className="w-4 h-4" />
        {item.label}
      </Link>
    )
  }

  const panel = (
    <aside className="w-60 max-w-[85vw] bg-[#111114] border-r border-[#1f1f22] p-4 flex flex-col justify-between h-full">
      <div>
        <div className="flex items-center justify-between gap-2 mb-6">
          <div className="flex items-center gap-2 text-[#22c55e]">
            <Sparkles className="w-5 h-5" />
            <span className="font-semibold text-[#e4e4e7]">Company Brain</span>
          </div>
          <button
            type="button"
            className="md:hidden rounded p-1 text-[#7c7c8a] hover:text-[#e4e4e7]"
            aria-label="Close menu"
            onClick={() => setOpen(false)}
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <nav className="space-y-1">{links.map(navItem)}</nav>
        <div className="mt-4 border-t border-[#1f1f22] pt-4">
          {settingsLinks.map(navItem)}
        </div>
      </div>
      <div className="space-y-3">
        <BrainHealthStatus />
        <div className="text-[#7c7c8a] text-xs border-t border-[#1f1f22] pt-3 space-y-1">
          <div className="font-mono">org: judge-demo-v1</div>
          <div>canonical demo · human-approved actions</div>
        </div>
      </div>
    </aside>
  )

  return (
    <>
      {/* Mobile top bar */}
      <div className="md:hidden fixed top-0 inset-x-0 z-40 flex items-center gap-3 border-b border-[#1f1f22] bg-[#050505]/95 px-3 py-2 backdrop-blur">
        <button
          type="button"
          className="rounded border border-[#1f1f22] p-2 text-[#e4e4e7]"
          aria-label="Open menu"
          onClick={() => setOpen(true)}
        >
          <Menu className="w-5 h-5" />
        </button>
        <span className="text-sm font-semibold text-[#e4e4e7]">Company Brain</span>
        <span className="ml-auto font-mono text-[10px] text-[#7c7c8a]">judge-demo-v1</span>
      </div>

      {/* Desktop sticky sidebar */}
      <div className="hidden md:block sticky top-0 h-screen shrink-0">{panel}</div>

      {/* Mobile drawer */}
      {open && (
        <div className="md:hidden fixed inset-0 z-50 flex">
          <button
            type="button"
            className="absolute inset-0 bg-black/60"
            aria-label="Close overlay"
            onClick={() => setOpen(false)}
          />
          <div className="relative z-10 h-full shadow-xl">{panel}</div>
        </div>
      )}
    </>
  )
}
