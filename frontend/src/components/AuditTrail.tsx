import { AnimatePresence, motion } from "framer-motion"
import type { AuditEntry } from "../types/schema"

type Props = {
  entries: AuditEntry[]
}

const KIND_COLOR: Record<AuditEntry["kind"], string> = {
  compile: "text-blue-400",
  propagate: "text-violet-400",
  intercept: "text-rose-400",
  agent: "text-emerald-400",
  info: "text-zinc-500",
}

const KIND_ICON: Record<AuditEntry["kind"], string> = {
  compile: "⚙",
  propagate: "↯",
  intercept: "⛔",
  agent: "▸",
  info: "•",
}

export function AuditTrail({ entries }: Props) {
  return (
    <div className="h-[60px] bg-[#020202] border-t border-[#1f1f22] flex items-center px-3 overflow-hidden shrink-0">
      <div className="flex flex-row gap-4 overflow-x-auto whitespace-nowrap">
        <AnimatePresence initial={false}>
          {entries.map((e) => (
            <motion.div
              key={e.id}
              initial={{ opacity: 0, x: 30 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.25 }}
              className={`text-[11px] font-mono ${KIND_COLOR[e.kind]} flex items-center gap-1.5 shrink-0`}
            >
              <span>{KIND_ICON[e.kind]}</span>
              <span className="text-zinc-400">{e.text}</span>
            </motion.div>
          ))}
        </AnimatePresence>
        {entries.length === 0 && (
          <div className="text-[11px] font-mono text-zinc-600">
            audit trail · waiting for brain events…
          </div>
        )}
      </div>
    </div>
  )
}
