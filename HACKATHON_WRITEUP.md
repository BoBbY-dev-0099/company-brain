# Company Brain — Project Writeup

**Track:** MemoryAgent · Qwen Cloud Global AI Hackathon 2026  
**One-liner:** Operating memory for agent fleets that knows when to stop trusting what it remembers.

---

## Problem (10 seconds)

Agent fleets retrieve past lessons and act on them confidently — even when **live system state** has changed. Wrong refund window. Wrong export chunk size. Wrong rollout %. Memory without applicability is a liability.

## Solution (10 seconds)

**Company Brain** is not a chatbot. It is a **memory-and-governance layer** any agent plugs into via REST or MCP:

1. **Compile** experience → versioned skills (Qwen)
2. **Recall** under limited context
3. **Intercept** before action (keyword + embedding)
4. **SAG** — deterministic `applies_if` / `invalidated_if` vs live `metadata` (no second LLM)
5. **Reinforce / forget** via confidence + decay + suspension
6. **Propagate** to operators over SSE

## The differentiator: Semantic Applicability Gate (SAG)

Same skill. Same decision text. Different live config → different outcome.

| Live metadata | Result |
|---------------|--------|
| `export_chunk_size_mb: 8` | **suspended** — preconditions broken |
| `export_chunk_size_mb: 25` | **auto_execute** — skill still valid |

That flip is the product. Judges should see it in the first 30 seconds.

## 30-second demo script (record this)

1. Open UI → **Brain** (no login; org `integrations-demo`)
2. Live config shows **25MB** → giant badge **GREEN AUTO_EXECUTE**
3. Click **Switch to 8MB** (or press keyboard **`8`**) → badge flips **RED SUSPENDED** instantly
4. Click **Switch to 25MB** (or press **`2`**) → green again
5. Open **Intercepts** → see horror-story seed + fresh toggle audit rows

Narration: *“Most memory systems always trust the top match. We check whether the memory still applies against live config — before the agent acts.”*

## Who it’s for

Teams already running multiple independent AI agents who need shared, governed memory — without building that layer from scratch. Infrastructure, not an application.

## What’s shipped

| Surface | What judges see |
|---------|-----------------|
| Open React UI | Dashboard, Brain (SAG buttons), Intercepts, Agents, Events, Settings, API Keys |
| Three demo agents | Support / Engineering / Product (real Qwen) |
| `integrations/` | Production-shaped connectors (GitHub PR, billing, flags, Zendesk, sessions) |
| MCP | `recall_skills`, `check_intercept`, `compile_experience` + attestation envelope |
| Auth | Open demo org for UI; `X-Brain-Api-Key` for agents |

## Stack

- **LLM / embeddings:** Qwen 3 (`qwen-plus`) + `text-embedding-v3` via DashScope
- **API:** FastAPI + Motor/MongoDB + SSE + FastMCP
- **UI:** React 18 + Vite + Tailwind (no login wall for hackathon)

## Honest scope

- SAG evaluates **metadata you pass** (config, flags, counters) — not automatic world-model scraping
- Intercept returns structured guidance; it does not patch production code by itself
- TEE attestation is a **credible envelope** for demo; full TDX on Alibaba `g8i` is the production path
- Outcome Feedback Loop (demote skills from confirmed real-world outcomes) is roadmap, not this build

## Why Qwen

Compiler, agents, and embeddings all run on Qwen Cloud compatible-mode. The governance layer is model-agnostic at the API boundary; the demo proves the loop with real Qwen calls end-to-end.

## Links

- Repo README: setup, API table, Docker ECS mimic
- `integrations/README.md`: connector suite W1–W5
- `PROJECT_MASTER.md`: deep architecture notes

---

**Closing line for video:**  
*Company Brain turns agent experience into versioned skills — and suspends those skills the moment live reality says they’re stale.*
