import { useEffect, useState } from "react"
import { apiGet, apiDelete } from "../lib/api"
import ApiKeyCreation from "../components/layout/ApiKeyCreation"

export default function ApiKeys() {
  const [keys, setKeys] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  const loadKeys = async () => {
    setLoading(true)
    try {
      const data = await apiGet("/settings/api-keys")
      setKeys(data.keys || [])
    } catch {
      setKeys([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadKeys()
  }, [])

  const revoke = async (key_id: string) => {
    if (!window.confirm("Revoke this API key? This cannot be undone.")) return
    try {
      await apiDelete(`/settings/api-keys/${key_id}`)
      loadKeys()
    } catch {
      alert("Failed to revoke key")
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">API Keys</h1>
        <p className="text-[#a1a1aa]">Manage keys for your agent fleet.</p>
      </div>

      <ApiKeyCreation onCreated={loadKeys} />

      <div className="border-t border-[#1f1f22] pt-4">
      {loading && <p className="text-sm text-[#7c7c8a]">Loading…</p>}
      {!loading && keys.length === 0 && (
        <p className="text-sm text-[#7c7c8a]">No active API keys.</p>
      )}
      <div className="space-y-2">
        {keys.map((k: any) => (
          <div
            key={k.key_id}
            className="bg-[#111114] border border-[#1f1f22] rounded p-3 flex items-center justify-between"
          >
            <div className="space-y-1">
              <div className="font-medium text-sm">{k.name}</div>
              <div className="text-xs text-[#7c7c8a] font-mono">{k.key_id}</div>
              <div className="text-xs text-[#7c7c8a]">{k.permissions}</div>
            </div>
            <button
              onClick={() => revoke(k.key_id)}
              className="text-[#ef4444] hover:text-[#dc2626] text-sm px-3 py-1 rounded hover:bg-[#2a0a0a] transition-colors"
            >
              Revoke
            </button>
          </div>
        ))}
      </div>
      </div>
    </div>
  )
}
