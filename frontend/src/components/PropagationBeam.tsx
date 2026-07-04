import { motion } from "framer-motion"

type Props = {
  triggerKey: number | null
}

/**
 * Two dashed beams: one going from the Brain (this panel) to the Support panel
 * on the left and one to the Engineering panel on the right. They animate
 * stroke-dashoffset on each `triggerKey` change.
 *
 * The beams are absolute-positioned over the brain panel, but extend visually
 * through the gap (the gap is 16px on each side; the panel sits between
 * SupportPanel and EngineeringPanel inside the same flex row).
 */
export function PropagationBeam({ triggerKey }: Props) {
  if (!triggerKey) return null

  return (
    <svg
      className="absolute pointer-events-none"
      style={{
        top: "30%",
        left: "-32px",
        right: "-32px",
        width: "calc(100% + 64px)",
        height: 32,
        zIndex: 30,
      }}
    >
      <motion.line
        key={`l-${triggerKey}`}
        x1="32"
        y1="16"
        x2="0"
        y2="16"
        stroke="#a78bfa"
        strokeWidth={2}
        strokeDasharray="6 4"
        initial={{ strokeDashoffset: 200, opacity: 0.9 }}
        animate={{ strokeDashoffset: 0, opacity: 0 }}
        transition={{ duration: 0.8, ease: "linear" }}
      />
      <motion.line
        key={`r-${triggerKey}`}
        x1="calc(100% - 32px)"
        y1="16"
        x2="100%"
        y2="16"
        stroke="#a78bfa"
        strokeWidth={2}
        strokeDasharray="6 4"
        initial={{ strokeDashoffset: 200, opacity: 0.9 }}
        animate={{ strokeDashoffset: 0, opacity: 0 }}
        transition={{ duration: 0.8, ease: "linear" }}
      />
    </svg>
  )
}
