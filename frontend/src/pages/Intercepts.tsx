import { useEffect, useState } from "react"
import { apiGet } from "../lib/api"
import InterceptList, { type Intercept } from "../components/InterceptList"

export default function Intercepts() {
  const [intercepts, setIntercepts] = useState<Intercept[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const data = await apiGet("/brain/intercepts")
        setIntercepts(data.intercepts || [])
      } catch {
        setIntercepts([])
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Decision Intercepts</h1>
        <div className="text-sm text-[#7c7c8a]">{intercepts.length} logged</div>
      </div>
      <p className="text-sm text-[#7c7c8a]">
        Each row: SAG decision · agent · skill · timestamp · reason. Toggle Brain live config to append a fresh audit entry.
      </p>

      <div className="bg-[#111114] border border-[#1f1f22] rounded p-4">
        <InterceptList
          intercepts={intercepts}
          loading={loading}
          emptyMessage="No intercepts logged yet. Switch Brain live config to 8MB to see SAG suspension."
        />
      </div>
    </div>
  )
}
