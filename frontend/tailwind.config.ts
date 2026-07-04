import type { Config } from "tailwindcss"

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#050505",
        panel: "#0f0f11",
        "panel-border": "#1f1f22",
        "audit-bg": "#020202",
        "active-glow": "#3b82f6",
        "intercept-flash": "#f43f5e",
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      keyframes: {
        "live-pulse": {
          "0%, 100%": { transform: "scale(1)", opacity: "1" },
          "50%": { transform: "scale(1.2)", opacity: "0.7" },
        },
      },
      animation: {
        "live-pulse": "live-pulse 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config
