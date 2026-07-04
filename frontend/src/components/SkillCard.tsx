import { motion } from "framer-motion"
import type { SkillSummary } from "../types/schema"

type Props = {
  skill: SkillSummary
  featured?: boolean
  isNew?: boolean
  isReinforced?: boolean
}

const DECAY_COLOR: Record<SkillSummary["decay_rate"], string> = {
  never: "text-violet-300 bg-violet-500/10",
  slow: "text-emerald-300 bg-emerald-500/10",
  medium: "text-amber-300 bg-amber-500/10",
  fast: "text-rose-300 bg-rose-500/10",
}

export function SkillCard({ skill, featured = false, isNew, isReinforced }: Props) {
  const conf = skill.confidence
  const confColor =
    conf >= 0.85 ? "from-emerald-400 to-emerald-300"
      : conf >= 0.70 ? "from-blue-400 to-blue-300"
      : "from-amber-400 to-amber-300"

  const borderClass = isNew
    ? "border-blue-400/60 shadow-[0_0_20px_rgba(96,165,250,0.25)]"
    : isReinforced
    ? "border-emerald-400/60 shadow-[0_0_18px_rgba(52,211,153,0.2)]"
    : "border-[#1f1f22]"

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: -16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.25, ease: [0.4, 0, 0.2, 1] }}
      className={`bg-[#0a0a0c] rounded-md border ${borderClass} p-3 ${
        featured ? "min-h-[140px]" : "min-h-[120px]"
      } relative overflow-hidden`}
    >
      {isNew && (
        <motion.div
          aria-hidden
          initial={{ opacity: 0.7 }}
          animate={{ opacity: [0.7, 0, 0.7] }}
          transition={{ duration: 3, repeat: 0 }}
          className="absolute inset-0 rounded-md border border-blue-400/50 pointer-events-none"
        />
      )}

      <div className="flex items-start justify-between mb-1.5 relative z-10">
        <div className="font-mono text-[13px] font-semibold text-zinc-200 leading-tight pr-2 break-words">
          {skill.name}
        </div>
        {isReinforced ? (
          <motion.span
            key={`v-${skill.version}-${skill.reinforcement_count}`}
            initial={{ scale: 0.6, opacity: 0 }}
            animate={{ scale: [0.6, 1.2, 1], opacity: 1 }}
            transition={{ duration: 0.4 }}
            className="text-[10px] font-mono text-emerald-300 bg-emerald-500/10 px-1.5 py-0.5 rounded shrink-0"
          >
            v{skill.version}
          </motion.span>
        ) : (
          <span className="text-[10px] font-mono text-zinc-500 bg-zinc-500/10 px-1.5 py-0.5 rounded shrink-0">
            v{skill.version}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-1 mb-2">
        <span className="text-[10px] uppercase tracking-wider text-zinc-400 bg-zinc-500/10 px-1.5 py-0.5 rounded">
          {skill.domain}
        </span>
        <span className={`text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded ${DECAY_COLOR[skill.decay_rate]}`}>
          {skill.decay_rate}
        </span>
        <span className="text-[10px] font-mono text-zinc-500 ml-auto">
          ×{skill.reinforcement_count}
        </span>
      </div>

      <div className="h-1.5 bg-[#1f1f22] rounded-full overflow-hidden mb-2">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${Math.min(100, conf * 100)}%` }}
          transition={{ duration: 0.6, ease: [0.4, 0, 0.2, 1] }}
          className={`h-full bg-gradient-to-r ${confColor}`}
        />
      </div>

      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-mono text-zinc-400">{conf.toFixed(2)} conf</span>
        {skill.auto_execute && (
          <span className="text-[9px] uppercase tracking-wider text-emerald-300 bg-emerald-500/15 border border-emerald-500/30 px-1.5 py-0.5 rounded">
            auto
          </span>
        )}
      </div>

      <div className="text-[11px] text-zinc-500 leading-snug line-clamp-2">
        {skill.intercept_message || skill.summary}
      </div>
    </motion.div>
  )
}
