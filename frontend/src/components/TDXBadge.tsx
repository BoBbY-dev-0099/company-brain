import { useState } from "react"
import { Lock, Shield } from "lucide-react"

export type IntegrityInfo = {
  mode?: "tdx" | "rsa" | string
  attested?: boolean
  quote_id?: string
  audit_id?: string
  tdx_quote?: string
  signature?: string
  public_key_fingerprint?: string
  algorithm?: string
}

interface Props {
  integrity?: IntegrityInfo | null
}

export default function TDXBadge({ integrity }: Props) {
  const [open, setOpen] = useState(false)

  if (!integrity) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
        <Shield className="h-3 w-3" /> Unverified
      </span>
    )
  }

  const isTdx = integrity.mode === "tdx" || integrity.attested
  const label = isTdx
    ? `TDX Attested ${(integrity.quote_id || "").slice(0, 8)}`
    : `RSA Audited ${(integrity.public_key_fingerprint || "").slice(0, 8)}`
  const tip = isTdx
    ? integrity.tdx_quote || integrity.quote_id || ""
    : integrity.signature || integrity.public_key_fingerprint || ""

  return (
    <>
      <button
        type="button"
        title={tip}
        onClick={() => setOpen(true)}
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${
          isTdx ? "bg-emerald-100 text-emerald-800" : "bg-sky-100 text-sky-800"
        }`}
      >
        <Lock className="h-3 w-3" />
        {label}
      </button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="max-h-[80vh] w-full max-w-lg overflow-auto rounded-lg bg-white p-4 shadow-xl">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="font-semibold text-slate-900">Decision integrity</h3>
              <button
                type="button"
                className="text-sm text-slate-500"
                onClick={() => setOpen(false)}
              >
                Close
              </button>
            </div>
            <pre className="whitespace-pre-wrap break-all rounded bg-slate-50 p-3 text-xs text-slate-700">
              {JSON.stringify(integrity, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </>
  )
}
