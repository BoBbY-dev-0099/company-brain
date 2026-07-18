import { useEffect, useRef, useState } from "react"

export type SSEHandler = (eventName: string, data: unknown) => void

export function useSSE(url: string | null, onEvent: SSEHandler) {
  const [connected, setConnected] = useState(false)
  const handlerRef = useRef(onEvent)
  handlerRef.current = onEvent

  useEffect(() => {
    const sseUrl = url
    if (!sseUrl) return
    let es: EventSource | null = null
    let cancelled = false
    let backoff = 1000

    function connect() {
      if (cancelled || !sseUrl) return
      es = new EventSource(sseUrl)

      es.addEventListener("open", () => {
        setConnected(true)
        backoff = 1000
      })

      const known = [
        "hello",
        "skill_compiled",
        "skill_reinforced",
        "skill_invalidated",
        "skill_suspended",
        "decision_intercepted",
        "agent_action",
        "agent_registered",
        "config_updated",
        "keepalive",
      ]
      for (const name of known) {
        es.addEventListener(name, (e: MessageEvent) => {
          try {
            const parsed = e.data ? JSON.parse(e.data) : {}
            handlerRef.current(name, parsed)
          } catch {
            handlerRef.current(name, e.data)
          }
        })
      }

      es.addEventListener("error", () => {
        setConnected(false)
        es?.close()
        es = null
        if (cancelled) return
        const wait = Math.min(backoff, 8000)
        backoff = Math.min(backoff * 2, 8000)
        setTimeout(connect, wait)
      })
    }

    connect()
    return () => {
      cancelled = true
      es?.close()
    }
  }, [url])

  return { connected }
}
