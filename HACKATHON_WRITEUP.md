# Company Brain — Project Writeup

**Track:** MemoryAgent · Qwen Cloud Global AI Hackathon 2026  
**One-liner:** Operating memory for agent fleets that knows when to stop trusting what it remembers.

**Live demo (Alibaba Cloud ECS):** http://8.218.174.77  
**Repo:** https://github.com/BoBbY-dev-0099/company-brain · **License:** MIT

---

## Problem (10 seconds)

Agent fleets retrieve past lessons and act on them confidently — even when **live system state** has changed. Wrong refund window. Wrong export chunk size. Wrong rollout %. Memory without applicability is a liability.

## Solution (10 seconds)

**Company Brain** is not a chatbot. It is a **memory-and-governance layer** any agent plugs into via REST or MCP:

1. **Compile** experience → versioned skills (Qwen)
2. **Recall** under limited context
3. **Intercept** before action (keyword + embedding)
4. **SAG** — deterministic `applies_if` / `invalidated_if` vs live `metadata` (no second LLM)
5. **Attest** the decision — Intel TDX quote when available, else **RSA-PSS audit**
6. **Reinforce / forget** via confidence + decay + suspension
7. **Propagate** to operators over SSE

## The differentiator: Semantic Applicability Gate (SAG)

Same skill. Same decision text. Different live config → different outcome.

| Live metadata | Result |
|---------------|--------|
| `export_chunk_size_mb: 8` | **SUSPENDED** — preconditions broken |
| `export_chunk_size_mb: 25` | **AUTO_EXECUTE** — skill still valid |

Every evaluation returns an **AST trace** (operators + timings) so judges can see *why* the gate fired — typically under a millisecond, not an LLM round-trip.

That flip is the product. Judges should see it in the first 30 seconds.

## 30-second demo script (record this)

**URL:** http://8.218.174.77/app/brain (no login; org `integrations-demo`)

1. Open **Brain** — live config **25MB**, giant badge **GREEN AUTO_EXECUTE**
2. Click the **8MB** toggle (or press keyboard **`8`**) → badge flips **RED SUSPENDED** instantly
3. Expand **Evaluation trace** → see `lte` / `gt` / `and` / `not` tree
4. Note the integrity badge: **RSA Audited** on the current r9i host (honest — not fake TDX)
5. Click **25MB** (or press **`2`**) → green again
6. Open **Intercepts** → horror-story seed + fresh toggle audit rows

Narration: *“Most memory systems always trust the top match. We check whether the memory still applies against live config — before the agent acts. And we cryptographically bind that decision.”*

## Who it’s for

Teams already running multiple independent AI agents who need shared, governed memory — without building that layer from scratch. Infrastructure, not an application.

## What’s shipped

| Surface | What judges see |
|---------|-----------------|
| Open React UI | Dashboard, Brain (SAG toggle + eval trace + integrity badge), Intercepts, Agents, Events, Settings |
| Three demo agents | Support / Engineering / Product (real Qwen) |
| `integrations/` | Production-shaped connectors + real GitHub PR webhook → skill compile |
| MCP | `recall_skills`, `check_intercept`, `compile_experience` + attestation status |
| Integrity | `POST /attestation/quote` (TDX) · `POST /audit/sign` (RSA fallback) · `POST /sag/evaluate` (trace) |
| Auth | Open demo org for UI; `X-Brain-Api-Key` for agents |
| Docs | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) + [`docs/architecture.png`](docs/architecture.png) |

## Stack

- **LLM / embeddings:** Qwen (`qwen-plus`) + `text-embedding-v3` via DashScope international
- **API:** FastAPI + Motor/MongoDB + SSE + FastMCP
- **UI:** React 18 + Vite + Tailwind (no login wall)
- **Cloud:** Alibaba Cloud ECS + Docker Compose (nginx → API → Mongo)
- **Integrity:** Intel TDX on Confidential VM (`g7t`/`g8i`); RSA-PSS-SHA256 fallback otherwise

## Deployment & attestation (honest)

| Host | Attestation mode |
|------|------------------|
| Current demo ECS (`ecs.r9i.xlarge`, `8.218.174.77`) | **RSA audit fallback** — no `/dev/tdx_guest` |
| Target Confidential VM (`g8i` / `g7t`) | **Hardware TDX quotes** via Alibaba quote-generation binary |

We do **not** claim TDX on the r9i demo host. The UI shows **RSA Audited**; the attestation tab narrates the fallback. Moving the same stack onto g8i enables real quotes without changing the SAG product.

## Honest scope

- SAG evaluates **metadata you pass** (config, flags, counters) — not automatic world-model scraping
- Intercept returns structured guidance; it does not patch production code by itself
- Outcome Feedback Loop (demote skills from confirmed real-world outcomes) is roadmap, not this build

## Why Qwen

Compiler, agents, and embeddings all run on Qwen Cloud compatible-mode. The governance layer is model-agnostic at the API boundary; the demo proves the loop with real Qwen calls end-to-end on Alibaba Cloud.

## Links

| Asset | Path |
|-------|------|
| Live demo | http://8.218.174.77 |
| Architecture diagram | [`docs/architecture.png`](docs/architecture.png) |
| Architecture writeup | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Submission checklist | [`docs/SUBMISSION_CHECKLIST.md`](docs/SUBMISSION_CHECKLIST.md) |
| Judging alignment | [`docs/JUDGING_ALIGNMENT.md`](docs/JUDGING_ALIGNMENT.md) |
| README / quick start | [`README.md`](README.md) |
| Integrations | [`integrations/README.md`](integrations/README.md) |
| ECS visual E2E | [`E2E_ECS_VISUAL_REPORT.md`](E2E_ECS_VISUAL_REPORT.md) — **ECS READY TO RECORD** |

---

**Closing line for video:**  
*Company Brain turns agent experience into versioned skills — suspends those skills the moment live reality says they’re stale — and binds that decision with cryptographic integrity.*
