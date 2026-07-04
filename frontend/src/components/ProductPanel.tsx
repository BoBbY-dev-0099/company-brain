import { motion, AnimatePresence } from "framer-motion"
import type { ProductSession } from "../types/schema"
import { SessionSwitcher } from "./SessionSwitcher"

type Props = {
  sessions: ProductSession[]
  activeSessionId: string
  onSelectSession: (id: string) => void
}

export function ProductPanel({ sessions, activeSessionId, onSelectSession }: Props) {
  const session = sessions.find((s) => s.id === activeSessionId) || sessions[0]
  return (
    <div className="h-full flex flex-col rounded-md border border-[#1f1f22] bg-[#0f0f11] p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="text-[13px] uppercase text-zinc-500 tracking-wider font-medium">
          📋 Product Agent — Cross-Session Memory
        </span>
        <SessionSwitcher
          sessions={sessions}
          activeId={activeSessionId}
          onSelect={onSelectSession}
        />
      </div>

      <div className="flex-1 overflow-y-auto pr-1 space-y-1.5">
        <AnimatePresence mode="popLayout">
          {session?.messages.length === 0 && (
            <div className="text-[12px] text-zinc-500 italic">
              New session — no prior turns. The brain will still surface relevant skills on first ask.
            </div>
          )}
          {session?.messages.map((m, i) => (
            <motion.div
              key={`${session.id}-${i}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[82%] px-3 py-2 rounded-md text-[12.5px] leading-snug ${
                  m.role === "user"
                    ? "bg-[#1f1f22] text-zinc-200"
                    : "bg-[#0a0a0c] border border-[#1f1f22] text-zinc-300"
                }`}
              >
                {m.content}
                {m.reasoning && (
                  <div className="mt-1.5 pt-1.5 border-t border-[#1f1f22] text-[10.5px] font-mono text-zinc-600 leading-snug">
                    {m.reasoning}
                  </div>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {session?.brainUpdated && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          className="text-[11px] text-emerald-400 font-mono mt-2"
        >
          {session.brainUpdated}
        </motion.div>
      )}
    </div>
  )
}
