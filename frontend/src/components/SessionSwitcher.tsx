import type { ProductSession } from "../types/schema"

type Props = {
  sessions: ProductSession[]
  activeId: string
  onSelect: (id: string) => void
}

export function SessionSwitcher({ sessions, activeId, onSelect }: Props) {
  return (
    <div className="flex gap-1">
      {sessions.map((s) => {
        const active = s.id === activeId
        return (
          <button
            key={s.id}
            onClick={() => onSelect(s.id)}
            className={`text-[11px] font-mono px-2 py-0.5 transition-colors border-b-2 ${
              active
                ? "text-zinc-100 border-blue-500"
                : "text-zinc-600 border-transparent hover:text-zinc-400"
            }`}
          >
            {s.label}
          </button>
        )
      })}
    </div>
  )
}
