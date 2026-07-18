import { useState } from "react"
import { Check, Copy, X } from "lucide-react"

interface TraceNode {
  node: string
  args?: any
  result: boolean
  ms?: number
  note?: string
}

interface Props {
  trace?: TraceNode | null
  evaluatedInMs?: number | null
  defaultOpen?: boolean
}

function NodeView({ node, depth = 0 }: { node: TraceNode; depth?: number }) {
  const kids = Array.isArray(node.args)
    ? node.args.filter((a) => a && typeof a === "object" && "node" in a)
    : []

  return (
    <div className="ml-2 border-l border-slate-200 pl-3" style={{ marginLeft: depth * 4 }}>
      <div className="flex items-start gap-2 py-1 text-sm">
        {node.result ? (
          <Check className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
        ) : (
          <X className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" />
        )}
        <div>
          <span className="font-mono font-semibold text-slate-800">{node.node}</span>
          {node.note && (
            <span className="ml-2 rounded bg-amber-100 px-1.5 text-xs text-amber-800">
              {node.note}
            </span>
          )}
          <div className="font-mono text-xs text-slate-500">
            {JSON.stringify(
              Array.isArray(node.args)
                ? node.args.filter((a) => !(a && typeof a === "object" && "node" in a))
                : node.args,
            )}
            {typeof node.ms === "number" ? ` · ${node.ms}ms` : ""}
          </div>
        </div>
      </div>
      {kids.map((child, i) => (
        <NodeView key={i} node={child as TraceNode} depth={depth + 1} />
      ))}
    </div>
  )
}

export default function EvalTrace({ trace, evaluatedInMs, defaultOpen = true }: Props) {
  const [open, setOpen] = useState(defaultOpen)
  const [copied, setCopied] = useState(false)

  if (!trace) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-500">
        No evaluation trace yet — flip the SAG toggle.
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left text-sm font-semibold text-slate-800"
        onClick={() => setOpen((v) => !v)}
      >
        <span>
          Evaluation trace
          {typeof evaluatedInMs === "number" ? (
            <span className="ml-2 font-normal text-slate-500">({evaluatedInMs} ms)</span>
          ) : null}
        </span>
        <span className="text-slate-400">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="border-t border-slate-100 px-2 py-2">
          <div className="mb-2 flex justify-end">
            <button
              type="button"
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
              onClick={async () => {
                await navigator.clipboard.writeText(JSON.stringify(trace, null, 2))
                setCopied(true)
                setTimeout(() => setCopied(false), 1200)
              }}
            >
              <Copy className="h-3 w-3" />
              {copied ? "Copied" : "Copy JSON"}
            </button>
          </div>
          <NodeView node={trace} />
        </div>
      )}
    </div>
  )
}
