import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import { CheckCircle, Copy, Key, Zap } from "lucide-react"
import ApiKeyCreation from "../components/layout/ApiKeyCreation"
import { apiPost } from "../lib/api"

type OnboardStep = "welcome" | "api-key" | "done"

export default function Onboard() {
  const navigate = useNavigate()
  const [step, setStep] = useState<OnboardStep>("welcome")
  const [apiKey, setApiKey] = useState<string>("")
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    async function detectIntegration() {
      try {
        await apiPost("/settings/api-keys", { name: "auto-detect", permissions: "read:skills" })
      } catch {
        // ignore
      }
    }
    void detectIntegration()
  }, [])

  const copyKey = async () => {
    if (!apiKey) return
    await navigator.clipboard.writeText(apiKey)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const onKeyCreated = (data: any) => {
    if (data?.api_key) {
      setApiKey(data.api_key)
      setStep("done")
    }
  }

  if (step === "welcome") {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Welcome to Company Brain</h1>
        <div className="space-y-4 text-[#a1a1aa]">
          <p>
            Company Brain is your operating memory primitive for multi-agent fleets.
            Your agents emit events, the brain compiles them into versioned skills,
            and future decisions are pre-flight intercepted.
          </p>
          <ul className="space-y-2">
            <li className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-[#22c55e]" /> Compile raw events into skills via Qwen 3
            </li>
            <li className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-[#22c55e]" /> Pre-flight intercept decisions before LLM calls
            </li>
            <li className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-[#22c55e]" /> Reinforce confidence over time
            </li>
          </ul>
        </div>
        <button
          onClick={() => setStep("api-key")}
          className="bg-[#22c55e] hover:bg-[#16a34a] text-[#050505] font-medium rounded px-6 py-3"
        >
          Get Started →
        </button>
      </div>
    )
  }

  if (step === "api-key") {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Create an API Key</h1>
        <p className="text-[#a1a1aa]">
          Your agents will use this key to authenticate with the brain.
          You can create multiple keys with different permissions later.
        </p>
        <ApiKeyCreation onCreated={(data: any) => onKeyCreated(data)} />
        <div className="flex items-center gap-2 text-sm text-[#7c7c8a]">
          <Key className="w-4 h-4" />
          <span>Generated keys use the <code className="bg-[#17171a] px-1 rounded">cb_live_*</code> format</span>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 text-[#22c55e]">
        <CheckCircle className="w-8 h-8" />
        <h1 className="text-2xl font-semibold text-[#e4e4e7]">All Set!</h1>
      </div>
      <p className="text-[#a1a1aa]">
        Copy the key below and connect your agent fleet.
      </p>
      {apiKey && (
        <div className="bg-[#17171a] border border-[#1f1f22] rounded p-4 space-y-2">
          <div className="text-sm text-[#7c7c8a]">Your API key (shown only once):</div>
          <div className="flex items-center gap-3">
            <code className="bg-[#050505] border border-[#1f1f22] rounded px-3 py-2 text-xs font-mono text-[#22c55e] flex-1 truncate">
              {apiKey}
            </code>
            <button
              onClick={copyKey}
              className="bg-[#1f1f22] hover:bg-[#2a2a30] text-[#e4e4e7] rounded px-3 py-2 text-sm flex items-center gap-2"
            >
              {copied ? <CheckCircle className="w-4 h-4 text-[#22c55e]" /> : <Copy className="w-4 h-4" />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
      )}
      <button
        onClick={() => navigate("/app/dashboard")}
        className="bg-[#22c55e] hover:bg-[#16a34a] text-[#050505] font-medium rounded px-6 py-3"
      >
        Go to Dashboard
      </button>
      <div className="text-xs text-[#7c7c8a] font-mono">Org: integrations-demo (open demo)</div>
    </div>
  )
}
