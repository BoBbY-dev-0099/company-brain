import { useState } from "react"
import { Plus, Copy, Check } from "lucide-react"
import { apiPost } from "../../lib/api"

interface ApiKeyCreationProps {
  onCreated?: (data: any) => void
}

export default function ApiKeyCreation({ onCreated }: ApiKeyCreationProps) {
  const [name, setName] = useState("")
  const [perms, setPerms] = useState("read:skills read:events")
  const [keyData, setKeyData] = useState<any>(null)
  const [copied, setCopied] = useState(false)
  const [creating, setCreating] = useState(false)

  const handleCreate = async () => {
    if (!name.trim()) return
    setCreating(true)
    try {
      const res = await apiPost("/settings/api-keys", {
        name: name.trim(),
        permissions: perms,
      })
      setKeyData(res)
      setName("")
      onCreated?.(res)
    } finally {
      setCreating(false)
    }
  }

  const copyKey = async () => {
    if (!keyData?.api_key) return
    await navigator.clipboard.writeText(keyData.api_key)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-end gap-3">
        <div className="flex-1">
          <label className="block text-xs text-[#7c7c8a] mb-1">Key Name</label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Production Agent Key"
            className="w-full bg-[#17171a] border border-[#1f1f22] rounded px-3 py-2 text-sm text-[#e4e4e7] placeholder:text-[#5c5c66] focus:border-[#22c55e] focus:outline-none"
          />
        </div>
        <div className="flex-1">
          <label className="block text-xs text-[#7c7c8a] mb-1">Permissions</label>
          <input
            value={perms}
            onChange={(e) => setPerms(e.target.value)}
            placeholder="read:skills read:events"
            className="w-full bg-[#17171a] border border-[#1f1f22] rounded px-3 py-2 text-sm text-[#e4e4e7] placeholder:text-[#5c5c66] focus:border-[#22c55e] focus:outline-none"
          />
        </div>
        <button
          onClick={handleCreate}
          disabled={creating || !name.trim()}
          className="bg-[#22c55e] hover:bg-[#16a34a] text-[#050505] font-medium text-sm rounded px-4 py-2 flex items-center gap-2 disabled:opacity-50"
        >
          <Plus className="w-4 h-4" />
          {creating ? "Creating…" : "Create"}
        </button>
      </div>

      {keyData?.api_key && (
        <div className="bg-[#17171a] border border-[#1f1f22] rounded p-4 space-y-2">
          <div className="text-sm text-[#7c7c8a]">
            Your API key (shown only once):
          </div>
          <div className="flex items-center gap-3">
            <code className="bg-[#050505] border border-[#1f1f22] rounded px-3 py-2 text-xs font-mono text-[#22c55e] flex-1 truncate">
              {keyData.api_key}
            </code>
            <button
              onClick={copyKey}
              className="bg-[#1f1f22] hover:bg-[#2a2a30] text-[#e4e4e7] rounded px-3 py-2 text-sm flex items-center gap-2"
            >
              {copied ? <Check className="w-4 h-4 text-[#22c55e]" /> : <Copy className="w-4 h-4" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
