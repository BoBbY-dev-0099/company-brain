import { motion } from "framer-motion"
import type { Ticket } from "../types/schema"

type Props = {
  tickets: Ticket[]
  onCompile: (ticketId: string) => void
  recentSkillIds: string[]
}

const STATUS_BORDER: Record<Ticket["status"], string> = {
  resolved: "border-emerald-500",
  escalated: "border-amber-500",
  processing: "border-blue-500",
}

const STATUS_PILL: Record<Ticket["status"], string> = {
  resolved: "bg-emerald-500/20 text-emerald-400",
  escalated: "bg-amber-500/20 text-amber-400",
  processing: "bg-blue-500/20 text-blue-400",
}

export function SupportPanel({ tickets, onCompile, recentSkillIds: _r }: Props) {
  return (
    <div className="h-full flex flex-col rounded-md border border-[#1f1f22] bg-[#0f0f11] p-3">
      <div className="flex items-center justify-between mb-3">
        <span className="text-[13px] uppercase text-zinc-500 tracking-wider font-medium">🎧 Support Agent</span>
        <span className="text-[10px] text-zinc-600 font-mono">3 tickets</span>
      </div>

      <div className="flex-1 flex flex-col gap-3 overflow-y-auto pr-1">
        {tickets.map((t) => (
          <TicketCard key={t.id} t={t} onCompile={onCompile} />
        ))}
      </div>

      <div className="mt-3">
        <input
          type="text"
          placeholder="Inject context..."
          className="w-full bg-[#050505] border border-[#1f1f22] rounded px-2 py-1.5 text-[12px] text-zinc-300 placeholder:text-zinc-600 focus:outline-none focus:border-blue-500/40"
        />
      </div>
    </div>
  )
}

function TicketCard({ t, onCompile }: { t: Ticket; onCompile: (id: string) => void }) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={`relative bg-[#0a0a0c] border-l-[3px] ${STATUS_BORDER[t.status]} border-t border-r border-b border-[#1f1f22] rounded p-2.5`}
      style={{ minHeight: 100 }}
    >
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-mono text-zinc-600">{t.id}</span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] uppercase tracking-wider ${STATUS_PILL[t.status]}`}>
          {t.status}
        </span>
      </div>
      <div className="text-[13px] text-zinc-200 font-medium mb-1 leading-tight">{t.title}</div>
      <div className="text-[12px] text-zinc-400 leading-snug line-clamp-2 mb-2">{t.body}</div>
      <button
        onClick={() => onCompile(t.id)}
        className="w-full bg-blue-600 hover:bg-blue-500 transition-colors text-white text-[11px] uppercase tracking-wider rounded py-1 font-medium"
      >
        {t.compiledSkillVersion ? `✓ Compiled ${t.compiledSkillVersion}` : "Compile to Brain"}
      </button>
    </motion.div>
  )
}
