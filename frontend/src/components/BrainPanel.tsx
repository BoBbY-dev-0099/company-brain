import { motion, AnimatePresence } from "framer-motion"
import type { SkillSummary } from "../types/schema"
import { ConfidenceGauge } from "./ConfidenceGauge"
import { SkillCard } from "./SkillCard"

type Props = {
  skills: SkillSummary[]
  newSkillIds: Set<string>
  reinforcedSkillIds: Set<string>
}

export function BrainPanel({ skills, newSkillIds, reinforcedSkillIds }: Props) {
  const featured = skills[0]
  const rest = skills.slice(1)
  const avgConfidence =
    skills.length === 0
      ? 0
      : skills.reduce((sum, s) => sum + s.confidence, 0) / skills.length

  return (
    <div className="h-full flex flex-col rounded-md border border-[#1f1f22] bg-[#0f0f11] p-3 relative overflow-hidden">
      <div className="absolute inset-0 pointer-events-none rounded-md border border-blue-500/20 shadow-[0_0_30px_rgba(59,130,246,0.1)_inset]" />

      <div className="flex items-center justify-between mb-3 relative z-10">
        <span className="text-[13px] uppercase text-zinc-400 tracking-wider font-semibold">🧬 Skill Library</span>
        <span className="text-[11px] text-zinc-500 font-mono">{skills.length} active</span>
      </div>

      <div className="flex items-center gap-4 mb-4 relative z-10">
        <ConfidenceGauge value={avgConfidence} />
        <div className="flex-1 flex flex-col gap-1.5">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500">Average Confidence</div>
          <AnimatePresence>
            {avgConfidence >= 0.85 && (
              <motion.div
                initial={{ x: 100, opacity: 0 }}
                animate={{ x: 0, opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ type: "spring", stiffness: 260, damping: 20 }}
                className="bg-emerald-500/15 border border-emerald-500/40 rounded px-2 py-1.5 text-[11px] text-emerald-300 font-medium"
              >
                🟢 AUTO-EXECUTE UNLOCKED
              </motion.div>
            )}
          </AnimatePresence>
          <div className="text-[11px] text-zinc-500 leading-snug">
            Brain learns from agent experiences and propagates skills back to all
            connected agents.
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto pr-1">
        {featured && (
          <div className="mb-3">
            <SkillCard
              skill={featured}
              featured
              isNew={newSkillIds.has(featured.skill_id)}
              isReinforced={reinforcedSkillIds.has(featured.skill_id)}
            />
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <AnimatePresence initial={false}>
            {rest.map((s) => (
              <SkillCard
                key={s.skill_id}
                skill={s}
                isNew={newSkillIds.has(s.skill_id)}
                isReinforced={reinforcedSkillIds.has(s.skill_id)}
              />
            ))}
          </AnimatePresence>
        </div>

        {skills.length === 0 && (
          <div className="text-[12px] text-zinc-500 text-center py-8">
            Brain is empty. Compile a ticket on the left to plant the first skill.
          </div>
        )}
      </div>
    </div>
  )
}
