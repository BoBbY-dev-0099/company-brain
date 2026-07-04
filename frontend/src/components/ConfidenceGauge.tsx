import { motion, useMotionValue, useTransform, animate } from "framer-motion"
import { useEffect } from "react"

type Props = {
  value: number
}

export function ConfidenceGauge({ value }: Props) {
  const size = 80
  const stroke = 8
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius

  const motionVal = useMotionValue(0)
  const dashOffset = useTransform(motionVal, (v) => circumference * (1 - v))
  const display = useTransform(motionVal, (v) => v.toFixed(2))

  useEffect(() => {
    const controls = animate(motionVal, value, {
      duration: 0.6,
      ease: [0.4, 0, 0.2, 1],
    })
    return () => controls.stop()
  }, [value, motionVal])

  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="#1f1f22"
          strokeWidth={stroke}
          fill="none"
        />
        <defs>
          <linearGradient id="gauge-grad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#fbbf24" />
            <stop offset="100%" stopColor="#34d399" />
          </linearGradient>
        </defs>
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="url(#gauge-grad)"
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          style={{ strokeDashoffset: dashOffset }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <motion.span className="text-[18px] font-mono text-zinc-100 leading-none">
          {display}
        </motion.span>
        <span className="text-[9px] uppercase tracking-wider text-zinc-500 mt-0.5">conf</span>
      </div>
    </div>
  )
}
