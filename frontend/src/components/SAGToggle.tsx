type SagBadge = "suspended" | "auto_execute" | "unknown"

interface Props {
  chunkMb: number
  sagBadge: SagBadge
  busy?: boolean
  onToggle: (next: 8 | 25) => void
  skillId?: string
}

export default function SAGToggle({
  chunkMb,
  sagBadge,
  busy,
  onToggle,
  skillId = "data-export-large-file-timeout",
}: Props) {
  const suspended = sagBadge === "suspended" || chunkMb <= 10

  return (
    <div className="flex flex-col items-center gap-4 py-2">
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={busy}
          onClick={() => onToggle(8)}
          className={`rounded-md px-4 py-2 text-sm font-semibold transition duration-300 ${
            suspended
              ? "bg-rose-600 text-white shadow"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          8MB
        </button>

        <button
          type="button"
          disabled={busy}
          aria-label="Toggle SAG chunk size"
          onClick={() => onToggle(suspended ? 25 : 8)}
          className={`relative h-10 w-20 rounded-full transition duration-300 ${
            suspended ? "bg-rose-500" : "bg-emerald-500"
          }`}
        >
          <span
            className={`absolute top-1 h-8 w-8 rounded-full bg-white shadow transition duration-300 ${
              suspended ? "left-1" : "left-11"
            }`}
          />
        </button>

        <button
          type="button"
          disabled={busy}
          onClick={() => onToggle(25)}
          className={`rounded-md px-4 py-2 text-sm font-semibold transition duration-300 ${
            !suspended
              ? "bg-emerald-600 text-white shadow"
              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
          }`}
        >
          25MB
        </button>
      </div>

      <div
        className={`rounded-md px-4 py-1.5 text-sm font-bold tracking-wide transition duration-300 ${
          suspended ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"
        }`}
      >
        {suspended ? "SUSPENDED" : "AUTO_EXECUTE"}
      </div>
      <p className="text-xs text-slate-500">Skill: {skillId}</p>
    </div>
  )
}
