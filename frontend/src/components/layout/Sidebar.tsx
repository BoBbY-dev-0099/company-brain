import { useLocation, Link } from "react-router-dom"
import { useAuth, UserButton } from "@clerk/clerk-react"
import {
  Brain,
  LogOut,
  ShieldAlert,
  Users,
  Zap,
  Settings,
  Key,
  Megaphone,
  Sparkles,
} from "lucide-react"
import BrainHealthStatus from "./BrainHealthStatus"

export default function Sidebar() {
  const location = useLocation()
  const { userId, signOut } = useAuth()

  const links = [
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

  const navItem = (item: typeof links[0]) => {
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

  return (
    <aside className="w-60 bg-[#111114] border-r border-[#1f1f22] p-4 flex flex-col justify-between h-screen sticky top-0">
      <div>
        <div className="flex items-center gap-2 mb-6 text-[#22c55e]">
          <Sparkles className="w-5 h-5" />
          <span className="font-semibold text-[#e4e4e7]">Company Brain</span>
        </div>
        <nav className="space-y-1">{links.map(navItem)}</nav>
        <div className="mt-4 border-t border-[#1f1f22] pt-4">
          {settingsLinks.map(navItem)}
        </div>
      </div>
      <div className="space-y-3">
        <BrainHealthStatus />
        <div className="flex items-center gap-2 text-[#7c7c8a] text-xs border-t border-[#1f1f22] pt-3">
          <UserButton afterSignOutUrl="/" />
          <span className="font-mono">{userId ? `${userId.slice(0, 6)}..` : "--"}</span>
        </div>
        <button
          onClick={() => signOut()}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded text-xs font-medium text-[#a1a1aa] hover:text-[#e4e4e7] hover:bg-[#1f1f22] transition-colors"
        >
          <LogOut className="w-3 h-3" />
          Sign Out
        </button>
      </div>
    </aside>
  )
}
