# Company Brain — Project Master Context

**Qwen Cloud Global AI Hackathon 2026 · MemoryAgent track**  
**Author:** BoBbY-dev-0099 · **Repo:** https://github.com/BoBbY-dev-0099/company-brain  
**Last updated:** July 4, 2026 (UI complete + visual E2E verified)

> **One line:** Most agents remember. Company Brain knows **when to stop trusting** what it remembers.

**Local commits:** `3eb282df` initial · `3620840d` SAG→MCP · `cc42f8cb` Qwen cache+metrics · UI pages (uncommitted)

---

## Table of contents

1. [What this is (and is not)](#1-what-this-is-and-is-not)
2. [The problem we solve](#2-the-problem-we-solve)
3. [Architecture overview](#3-architecture-overview)
4. [The core loop — end to end](#4-the-core-loop--end-to-end)
5. [Semantic Applicability Gate (SAG)](#5-semantic-applicability-gate-sag)
6. [Surfaces — how the world connects](#6-surfaces--how-the-world-connects)
7. [Auth, org isolation, and production onboarding](#7-auth-org-isolation-and-production-onboarding)
8. [Demo agents (proof, not product)](#8-demo-agents-proof-not-product)
9. [Tech stack and Qwen Cloud usage](#9-tech-stack-and-qwen-cloud-usage)
10. [Deploy and run](#10-deploy-and-run)
11. [What makes this a top-1 submission](#11-what-makes-this-a-top-1-submission)
12. [Hackathon requirements checklist](#12-hackathon-requirements-checklist)
13. [Demo script (record this)](#13-demo-script-record-this)
14. [Judge Q&A cheat sheet](#14-judge-qa-cheat-sheet)
15. [Verified test results](#15-verified-test-results)
16. [Fixes shipped during verification](#16-fixes-shipped-during-verification)
17. [Known gaps (honest)](#17-known-gaps-honest)
18. [Efficiency metric (Track 3 angle)](#18-efficiency-metric-track-3-angle)
19. [Roadmap to win live Q&A](#19-roadmap-to-win-live-qa)
20. [Code map](#20-code-map)
21. [Command cheat sheet](#21-command-cheat-sheet)

---

## 1. What this is (and is not)

### What it IS

**Company Brain is infrastructure** — a memory-and-governance layer that any AI agent (yours, ours, or a third party's) plugs into via **MCP** or **REST**.

Agents call in **before acting**. The brain answers:
- Does this planned action match something the fleet already learned?
- Does that lesson **still hold** given the **live state** of the system right now?

### What it is NOT

| Misread | Reality |
|---------|---------|
| A chatbot | No chat UI is the product. Chat is how demo agents talk to Qwen. |
| An agent platform | We built three tiny demo agents only to prove the loop works. |
| Vector RAG | We compile events into **executable skills** with preconditions, not just embeddings. |
| Static guardrails | SAG checks **runtime metadata**, not hardcoded rules at deploy time. |

### Who this is for

Teams running **multiple independent AI agents** who want shared, decaying, precondition-checked memory **without building the governance layer from scratch**.

---

## 2. The problem we solve

Today's agent "memory" layers retrieve similar past text. None of them ask:

> *"The lesson we learned was true when chunk size was 25MB — is it still true now that config says 8MB?"*

### Failure mode (concrete)

| Stale memory says | Live system state | Bad outcome |
|-------------------|-------------------|-------------|
| "Large async exports are safe" | `export_chunk_size_mb = 8` | Agent auto-executes a pattern that now times out |
| "Add NOT NULL in one migration" | Table now has 50M rows | Agent recommends a pattern that locks writes |
| "Refund annual plans prorated" | Policy changed last week | Agent applies outdated policy confidently |

### Our insight

**Retrieval is not governance.** Governance requires:
1. **Compile** experience into structured, versioned skills
2. **Intercept** before action (not after)
3. **Verify** preconditions against live context (SAG)
4. **Reinforce** confidence when the fleet keeps seeing the same pattern
5. **Propagate** changes to every connected agent in real time

---

## 3. Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        COMPANY BRAIN                            │
│                                                                 │
│  ┌──────────┐   ┌─────────────┐   ┌──────────────────────────┐  │
│  │ Compiler │──▶│ Skill Store │◀──│ Interceptor + SAG Gate   │  │
│  │ (Qwen)   │   │ (MongoDB)   │   │ (keyword + embedding)    │  │
│  └──────────┘   └──────┬──────┘   └────────────┬─────────────┘  │
│                        │                        │               │
│                        ▼                        ▼               │
│                 ┌─────────────┐         ┌─────────────┐         │
│                 │ Propagator  │────────▶│ SSE /stream │         │
│                 │ (broadcast) │         └──────┬──────┘         │
│                 └─────────────┘                │                │
└────────────────────────────────────────────────┼────────────────┘
         ▲                    ▲                 ▼
         │                    │          ┌─────────────┐
    REST /events         MCP tools      │ React UI    │
    /decisions/check     /mcp/sse       │ (Clerk)     │
         │                    │          └─────────────┘
         ▼                    ▼
   ┌──────────┐         ┌──────────┐
   │ Your     │         │ Demo     │
   │ agents   │         │ agents   │
   └──────────┘         └──────────┘
```

### Layer responsibilities

| Layer | File(s) | Job |
|-------|---------|-----|
| API | `backend/main.py` | Routes, auth, SSE, MCP mount |
| Compiler | `backend/core/compiler.py` | Event → skill via Qwen + embedding |
| Interceptor | `backend/core/interceptor.py` | Pre-flight scoring + SAG dispatch |
| Applicability | `backend/core/applicability.py` | Deterministic precondition eval (no LLM) |
| Store | `backend/brain/store.py` | MongoDB CRUD, atomic reinforce |
| Propagator | `backend/core/propagator.py` | SSE fan-out |
| MCP | `backend/mcp/server.py`, `tools.py` | External agent plug-in surface |
| Frontend | `frontend/src/` | Human ops UI + SAG demo buttons |
| Auth | `backend/middleware/clerk_auth.py` | Clerk JWT + API keys → org_id |

---

## 4. The core loop — end to end

### Phase 1 — COMPILE (learn)

```
Agent resolves something → POST /events  (or MCP compile_experience)
  → Qwen qwen-plus extracts structured skill JSON
  → text-embedding-v3 fingerprints the skill (1024-dim)
  → MongoDB upsert (org-scoped, versioned)
  → SSE skill_compiled → all UIs/agents see it
```

**Initial confidence:** 0.60  
**Auto-execute threshold:** 0.85 (after enough reinforcements)

### Phase 2 — INTERCEPT (govern)

```
Agent about to act → POST /decisions/check  (or MCP check_intercept)
  → Load org's active skills
  → Score: 0.6 × keyword + 0.4 × cosine similarity
  → RELEVANCE_FLOOR gate (default 0.35) — below = clear
  → SAG: evaluate applies_if / invalidated_if against metadata
  → Trust tier on confidence:
       ≥ 0.85 + auto_execute flag → auto_execute
       ≥ 0.70                  → block
       ≥ RELEVANCE_FLOOR       → warn
  → Log intercept, maybe reinforce
  → SSE broadcast
```

### Phase 3 — REINFORCE (trust grows)

Every non-clear, non-suspended intercept:
- `reinforcement_count += 1`
- `confidence += 0.05` (capped at 1.0)
- At 0.85 → `executable.auto_execute = true`

**Implementation:** single atomic MongoDB aggregation-pipeline update — no race window.

### Phase 4 — PROPAGATE (fleet sync)

`GET /stream` — Server-Sent Events. No polling. Skill cards flip live in the Brain UI when SAG suspends or reactivates a skill.

---

## 5. Semantic Applicability Gate (SAG)

**The demo moment. The differentiator. The judge hook.**

### What it is

Deterministic, **zero LLM calls**. Evaluates skill preconditions against keys in request `metadata`.

### Example skill (`data-export-large-file-timeout`)

```yaml
applies_if:
  - key: export_chunk_size_mb
    operator: gt
    value: 10
invalidated_if:
  - key: export_chunk_size_mb
    operator: lte
    value: 10
```

### Same decision, different live config → opposite outcome

| Request metadata | Result | Why |
|----------------|--------|-----|
| `{ "export_chunk_size_mb": 25 }` | `auto_execute` | Precondition holds, high confidence |
| `{ "export_chunk_size_mb": 8 }` | `suspended` | `invalidated_if` matched — skill visible but won't block/auto |
| `{}` (no metadata) | `auto_execute` | Backward compatible — no keys to invalidate |

### Where SAG works (as of commit `3620840d`)

| Entry point | Metadata support |
|-------------|------------------|
| `POST /decisions/check` | ✅ |
| MCP `check_intercept` | ✅ |
| Engineering agent pre-flight | ✅ (forwards request metadata) |
| Brain UI simulate buttons | ✅ |

### MCP example

```json
{
  "agent_id": "eng-01",
  "decision_text": "Increase data export chunk size to improve throughput",
  "metadata": { "export_chunk_size_mb": 8 }
}
```

Response includes: `result`, `applicability_status`, `suspension_reason`, `suspension_evidence`.

### What SAG does NOT do yet

The brain does **not auto-fetch** config from your infrastructure. Agents (or your orchestrator) must **supply** live context in `metadata`. That is an integration step, not a missing wire.

---

## 6. Surfaces — how the world connects

### REST API (agents + integrations)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/events` | Compile experience → skill |
| POST | `/decisions/check` | Pre-flight intercept + SAG |
| GET | `/brain/skills` | List org skills |
| GET | `/brain/intercepts` | Intercept audit log |
| GET | `/brain/events` | Event compile timeline |
| GET | `/health` | `embedding_healthy`, skill count |
| GET | `/stream` | SSE live updates |
| GET | `/settings/metrics` | Governance hits, est. tokens saved |
| POST | `/settings/seed-demo-data` | Seed 8 demo skills (Clerk JWT) |
| POST | `/settings/api-keys` | Create `cb_live_...` key |

Full list in `README.md`.

### MCP (recommended for agent fleets)

**Endpoint:** `https://your-domain/mcp/sse`

| Tool | When |
|------|------|
| `recall_skills` | Before planning — surface fleet memory |
| `check_intercept` | Before acting — governance + SAG |
| `compile_experience` | After resolving — write lesson back |

**Attestation:** `GET /mcp/attestation` — mock Intel TDX envelope with MCP tool manifest, measurement hash, and narrative (Brain UI **Attestation** tab).

Works with: Cursor, Claude Desktop, LangGraph nodes, any MCP client.

### React UI (human operators) — fully implemented

| Page | Path | Purpose |
|------|------|---------|
| Dashboard | `/app/dashboard` | Skill counts, top skills, SSE feed |
| Brain Explorer | `/app/brain` | Skills + SAG simulate + **Decisions** + **Attestation** tabs |
| Intercepts | `/app/intercepts` | Intercept audit trail |
| Agents | `/app/agents` | Run Support / Engineering / Product with metadata JSON |
| Events | `/app/events` | Event timeline + **Compile Event** form |
| Settings | `/app/settings` | Health, efficiency metrics, demo seed, integration links |
| API Keys | `/app/api-keys` | Create / revoke agent credentials |
| Onboard | `/app/onboard` | First-run API key creation |

**Shared component:** `frontend/src/components/InterceptList.tsx` — used by Intercepts page and Brain → Decisions tab.

---

## 7. Auth, org isolation, and production onboarding

### Two auth paths

| Actor | Auth | Resolves to |
|-------|------|-------------|
| Human (UI) | Clerk JWT | `org_id` from JWT org claim (fallback: `user_id`) |
| Machine (agent) | `Authorization: Bearer cb_live_...` | `org_id` on key record |

Every skill, intercept log, and reinforcement is **org-scoped**. Company A never sees Company B's data.

### Day-1 company setup

```
1. Admin signs up (Clerk) → lands on /app/onboard
2. Creates API key: cb_live_...
3. Seeds demo data (optional): POST /settings/seed-demo-data
4. Points agent MCP client at /mcp/sse with Bearer token
5. Agent loop:
     recall_skills → check_intercept(+metadata) → act → compile_experience
```

### Security fix (important for judges)

**Bug found during verification:** `reinforce_skill()` and `log_intercept()` were called without `org_id` → all reinforcement and logs wrote to `default` org regardless of caller. **Fixed:** `org_id` threaded through entire interceptor path.

---

## 8. Demo agents (proof, not product)

| Agent | Proves |
|-------|--------|
| **Support** | recall → resolve → compile back to brain |
| **Engineering** | **Pre-flight intercept BEFORE LLM call** + SAG via metadata |
| **Product** | Cross-session memory bridge |

All three use Qwen Chat Completions + in-process MCP tool dispatch (`backend/agents/base.py`).

**Run:** `POST /agents/{support|engineering|product}/run`

---

## 9. Tech stack and Qwen Cloud usage

### Stack

| Layer | Technology |
|-------|------------|
| LLM | Qwen 3 `qwen-plus` via DashScope international |
| Embeddings | `text-embedding-v3` (1024-dim) |
| Database | MongoDB 7 replica set (Motor async) |
| Backend | FastAPI + sse-starlette + FastMCP |
| Frontend | React 18 + Vite + Tailwind + Clerk |
| Cloud | Alibaba ECS + nginx + systemd |

### Hackathon compliance (mandatory)

| Rule | Status |
|------|--------|
| Must use Qwen Cloud API (not self-hosted Qwen) | ✅ `dashscope-intl.aliyuncs.com` |
| LangChain/LangGraph OK if Qwen is the LLM | ✅ We use raw OpenAI-compatible client |
| Alibaba Cloud deploy is bonus | ✅ Config in `deploy/` (ECS + nginx + systemd) |

### Qwen advanced features (Technical Depth scoring)

| Feature | Implementation | Judge talking point |
|---------|----------------|---------------------|
| Explicit context cache | `cache_control: ephemeral` on frozen compiler prefix (`compiler.py`) | Repeat compiles hit cache at 10% input cost |
| Strict JSON schema | `json_schema` + `strict: true` on compile; fallback to `json_object` | Zero malformed skills from Qwen |
| Parallel tool calls | `parallel_tool_calls=True` on agent loop (`base.py`) | recall + intercept in one completion when useful |
| Hybrid intercept | keyword 60% + embedding 40% in-process (no extra LLM) | Governance without added latency |

### Qwen models used

| Call | Model | Purpose |
|------|-------|---------|
| Compile event → skill | `qwen-plus` | Structured JSON extraction |
| Agent reasoning | `qwen-plus` | Tool loop (function calling) |
| Intercept matching | `text-embedding-v3` | Cosine similarity vs skill embeddings |

**Health check:** `GET /health` → `"embedding_healthy": true` proves semantic matching is live, not keyword-only fallback.

---

## 10. Deploy and run

### Local (dev)

```bash
docker compose up -d
docker compose exec mongodb mongosh --quiet --eval \
  "rs.status().ok || rs.initiate({_id:'rs0', members:[{_id:0, host:'localhost:27017'}]})"

.\.venv\Scripts\Activate.ps1
uvicorn backend.main:app --host 0.0.0.0 --port 8000

cd frontend && npm run dev   # http://localhost:5173 or :5174
```

### ECS (production)

```bash
# On server at /opt/company-brain
sudo cp deploy/companybrain.service /etc/systemd/system/
sudo cp deploy/nginx.conf /etc/nginx/sites-available/companybrain
sudo systemctl enable --now companybrain
```

**Critical:** nginx must disable proxy buffering on `/stream` and `/mcp/sse` or SSE freezes.

### Environment (`.env`)

```
QWEN_API_KEY=sk-ws-...
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_EMBEDDING_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
MONGODB_URI=mongodb://localhost:27017/companybrain?replicaSet=rs0&directConnection=true
VITE_CLERK_PUBLISHABLE_KEY=pk_test_...
CLERK_SECRET_KEY=sk_test_...
```

Never commit `.env`. Template: `.env.example`.

---

## 11. What makes this a top-1 submission

### vs typical hackathon projects

| Typical | Company Brain |
|---------|---------------|
| Single chatbot with memory | Infrastructure any agent plugs into |
| RAG retrieval | Governance — changes what agent **does** |
| Static rules | Runtime precondition check (SAG) |
| One agent | Three agents share one brain via MCP |
| localhost demo | ECS deploy config + live health endpoint |
| Hidden limitations | Documented gaps + fixes surfaced in verification |

### The sentence that wins

> *"They retrieve. We verify."*

Same skill. Same decision text. Same confidence. Only the live config value changes — and the outcome flips from `auto_execute` to `suspended` with an explained reason. **Live on screen via SSE. No refresh.**

### Research backing (contradiction resolution gap)

We audited five reference memory systems (gbrain, Hermes Agent, Claude Code, Codex, Cursor). **None solve contradiction resolution** when multiple skills match. We document this honestly and position it as our next milestone — judges respect teams that know the field.

---

## 12. Hackathon requirements checklist

From the Qwen Cloud Global AI Hackathon build session:

| Requirement | Status | Evidence |
|---------------|--------|----------|
| Qwen Cloud API usage (mandatory) | ✅ | `qwen-plus` + `text-embedding-v3` via DashScope |
| MCP integration (called out as bonus) | ✅ | 3 tools at `/mcp/sse` |
| Multi-agent system | ✅ | Support + Engineering + Product share one brain |
| Alibaba Cloud deployment (plus) | ⚠️ | `deploy/` exists; re-verify live URL before recording |
| Measurable efficiency (Track 3) | ✅ | `GET /settings/metrics` + Settings UI; governance_hits × 2k tokens |
| Full operator UI | ✅ | Brain (3 tabs), Agents, Events, Settings — visually verified Jul 4 |
| Do NOT self-host Qwen | ✅ | All calls via `dashscope-intl.aliyuncs.com` |

---

## 13. Demo script (record this)

**Target: 2–3 minutes. No slides. Live UI + one API call.**

### Setup (before camera)
- Backend running, `embedding_healthy: true`
- Signed in as Clerk user with seeded org (8 skills)
- Brain Explorer open at `/app/brain`

### Script

| Time | Action | Say |
|------|--------|-----|
| 0:00 | Show Brain UI, 8 skills | *"This is Company Brain — shared memory for agent fleets. Not a chatbot. Infrastructure."* |
| 0:20 | Select `data-export-large-file-timeout` | *"Every event compiles into a versioned skill with preconditions."* |
| 0:40 | Click **Simulate: Large Chunk Config (25MB)** | *"Same decision text. Chunk is 25MB. Skill applies. Auto-execute."* |
| 1:00 | Card flips ACTIVE via SSE | *"No refresh — SSE propagates to every connected agent."* |
| 1:15 | Click **Simulate: Small Chunk Config (8MB)** | *"Same skill. Same text. Only the live config changed."* |
| 1:30 | Card flips SUSPENDED, reason visible | *"Precondition failed. Suspended — not deleted, not silently ignored."* |
| 1:45 | Open **Intercepts** or Brain → **Decisions** tab | *"Full audit trail. Org-scoped. Suspension evidence visible."* |
| 2:00 | Brain → **Attestation** tab | *"MCP tool manifest + mock TEE envelope for enterprise path."* |
| 2:15 | **Agents** → Run Engineering with chunk=8 | *"Pre-flight SAG before the LLM call — not after."* |
| 2:30 | **Settings** → governance hits | *"Measurable efficiency — hits × 2k tokens saved."* |
| 2:45 | Close | *"No other memory layer we researched does this. They retrieve. We verify."* |

---

## 14. Judge Q&A cheat sheet

| Question | Answer |
|----------|--------|
| Is this a chatbot? | No. Infrastructure. Three demo agents prove the mechanism. |
| How do I integrate? | MCP at `/mcp/sse` or REST with `cb_live_` API key. See onboarding flow above. |
| Does SAG work on MCP? | Yes — pass `metadata` to `check_intercept`. |
| Who supplies live context? | The agent/orchestrator passes config in metadata. Brain evaluates; doesn't fetch config yet. |
| Multi-tenant safe? | Yes. org_id on every read/write. Fixed a real leak during verification. |
| Why Qwen? | Compile, embed, and agent reasoning — all via DashScope compatible-mode. |
| What if two skills conflict? | Highest score wins. Open problem — we researched 5 systems, none solve it. |
| Embeddings working? | `GET /health` → `embedding_healthy: true` |
| What's the efficiency gain? | Settings page or `GET /settings/metrics` → `governance_hits`, `est_llm_tokens_saved` (hits × 2k). |
| Is the UI complete? | Yes — Brain (skills/decisions/attestation), Agents, Events, Settings, Intercepts, API Keys. |
| TEE attestation real? | Mock envelope at `/mcp/attestation` demonstrating integration shape; production uses Alibaba `g8i` TDX. |

---

## 15. Verified test results

**Environment:** Local (Jul 3–4, 2026)  
**Embeddings:** 1024-dim, `embedding_healthy: true`  
**Full report:** `E2E_VERIFICATION_REPORT_RERUN.md`

### SAG side-by-side (the demo moment)

**TEST 1 — chunk=25MB:**
```json
{ "result": "auto_execute", "applicability_status": "active" }
```

**TEST 2 — chunk=8MB (same text):**
```json
{ "result": "suspended", "applicability_status": "suspended",
  "suspension_reason": "invalidated_if condition matched: export_chunk_size_mb <= 10" }
```

### Other verified
- ✅ UI card flip ACTIVE ↔ SUSPENDED via SSE (no refresh) — **Jul 4 visual browser test**
- ✅ Intercept log shows suspended with reason (15+ entries in test session)
- ✅ Brain → **Decisions** tab, **Attestation** tab, **Agents**, **Events**, **Settings** pages — all wired to live APIs
- ✅ Reinforcement count climbs (skill now v13+ over test history)
- ✅ F.3/F.4/F.5 interceptor regression pass
- ✅ 30 unit tests pass (interceptor, applicability, MCP)
- ✅ MCP metadata → SAG (commit `3620840d`)
- ✅ Qwen explicit cache + strict JSON schema (commit `cc42f8cb`)

### Not yet verified
- ⚠️ Clean onboarding on ECS (new account → seed → 8 skills → SAG buttons)
- ⚠️ ECS live URL post-all commits
- ⚠️ Push commits `3620840d` + `cc42f8cb` + UI work to GitHub

---

## 16. Fixes shipped during verification

These are not band-aids — textbook patterns for the failure modes they address.

| Fix | Pattern | Why |
|-----|---------|-----|
| Atomic reinforcement | MongoDB aggregation-pipeline update | No race between read-modify-write |
| Explicit Qwen context cache | `cache_control: ephemeral` on compiler prefix | Production-grade compile cost reduction |
| Strict JSON schema compile | `json_schema` + `strict: true` | Guaranteed skill shape from Qwen |
| Parallel tool calls | `parallel_tool_calls=True` on agents | Batch pre-flight tool invocations |
| JWT `leeway=60` | Clock skew tolerance on `iat` | Backend clock behind Clerk token issuance |
| JWKS warmup lock | `asyncio.Lock` on first JWKS fetch | Cold-cache stampede on concurrent first requests |
| Fresh token per request | `getToken({ skipCache: true })` in `api.ts` | Stale Clerk JWT → intermittent 401s |
| org_id threading | Pass through reinforce + log_intercept | Real multi-tenancy leak fix |
| SAG through MCP | `metadata` on `check_intercept` | Full agentic loop gated, not just REST |

---

## 17. Known gaps (honest)

| Gap | Severity | Notes |
|-----|----------|-------|
| Brain doesn't auto-fetch live config | Medium | Agents must supply metadata — integration step |
| Contradiction resolution | Research | Highest score wins; open field problem |
| PII in compiled skills | Prod blocker | Raw event content stored verbatim |
| ECS not re-verified post-all commits | Demo risk | Record against one URL consistently |
| Mongo integration tests | Dev only | pytest-asyncio loop scope issue; unit tests pass |
| TEE attestation | Demo only | Mock envelope — real TDX path documented for enterprise |

---

## 18. Efficiency metric (Track 3 angle)

If judges ask *"measurable efficiency gain over single-agent baseline"*:

### Live numbers (`GET /settings/metrics`)

```json
{
  "governance_hits": 12,
  "est_llm_tokens_saved": 24000,
  "intercept_by_result": {
    "block": 3,
    "warn": 2,
    "suspended": 4,
    "auto_execute": 3
  }
}
```

**Formula:** `governance_hits × 2,000 tokens` = estimated LLM tokens avoided by catching bad decisions **before** the agent reasoning loop runs. SAG suspensions count — they prevent a stale auto-execute without any LLM call in the gate itself.

### Narrative slide (30 seconds)
An agent **without** Company Brain:
- Retrieves similar past events but cannot verify preconditions
- Repeats stale patterns with full confidence
- No fleet-wide propagation — each agent learns in isolation

An agent **with** Company Brain:
- Pre-flight intercept catches known bad patterns **before** LLM cost is spent
- SAG suspends stale skills instead of auto-executing them
- Reinforcement converges known-good patterns to `auto_execute` — fewer LLM deliberation cycles

### Numbers you can show live
- `provenance.reinforcement_count` climbing on a skill over a demo session
- Intercept log growing — bad decisions caught before action
- SAG flip: same skill, zero LLM calls for the gate itself (deterministic)

---

## 19. Roadmap to win live Q&A

### Before submission (priority order)

1. **Push all commits to GitHub** — `3620840d`, `cc42f8cb`, + UI pages
2. **Record demo** using script in §13 against one consistent URL (local `:5174` or ECS)
3. **Prepare one efficiency slide** — Settings page screenshot: governance hits + tokens saved
4. **Revoke exposed GitHub PAT** if not already done
5. **Optional:** Re-verify ECS `/health` if using live URL in demo video

### Post-hackathon (if asked)
- Auto-fetch live context from config service / feature flag API
- Contradiction arbitration layer
- PII redaction on compile
- TEE attestation on Alibaba `g8i` / `gn8v-tee`

---

## 20. Code map

```
company-brain/
├── backend/
│   ├── main.py                 # FastAPI entry, all routes
│   ├── config.py               # Settings from .env
│   ├── middleware/clerk_auth.py
│   ├── brain/store.py          # MongoDB + atomic reinforce
│   ├── core/
│   │   ├── compiler.py         # Qwen compile + embed
│   │   ├── interceptor.py      # Pre-flight + SAG dispatch
│   │   ├── applicability.py    # SAG evaluator (no LLM)
│   │   ├── propagator.py       # SSE broadcast
│   │   └── schema.py           # Pydantic models
│   ├── mcp/server.py           # FastMCP SSE surface
│   ├── mcp/tools.py            # Tool implementations
│   ├── agents/                 # Demo agents
│   └── demo/seed_data.py       # 8 seed skills
├── frontend/src/
│   ├── lib/api.ts              # Fresh Clerk token interceptor
│   ├── components/InterceptList.tsx  # Shared intercept timeline
│   ├── pages/
│   │   ├── Brain.tsx           # Skills + SAG + Decisions + Attestation
│   │   ├── Agents.tsx          # Run demo agents
│   │   ├── Events.tsx          # Timeline + compile form
│   │   ├── Settings.tsx        # Health + metrics + seed
│   │   └── Intercepts.tsx      # Audit log
│   └── hooks/useSSE.ts         # Live updates
├── deploy/
│   ├── companybrain.service    # systemd
│   └── nginx.conf              # SSE-safe proxy
├── docker-compose.yml          # Local MongoDB
├── .env.example                # Safe template (in git)
└── README.md                   # Public-facing docs (in git)
```

**Obsidian architecture graph:** `Company Brain/` vault (local, gitignored) — open in Obsidian Graph view.

---

## 21. Command cheat sheet

```bash
# Health
curl http://127.0.0.1:8000/health

# SAG side-by-side (replace KEY)
curl -X POST http://127.0.0.1:8000/decisions/check \
  -H "Authorization: Bearer cb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"eng-01","decision_text":"Increase data export chunk size to improve throughput","metadata":{"export_chunk_size_mb":25}}'

curl -X POST http://127.0.0.1:8000/decisions/check \
  -H "Authorization: Bearer cb_live_..." \
  -H "Content-Type: application/json" \
  -d '{"agent_id":"eng-01","decision_text":"Increase data export chunk size to improve throughput","metadata":{"export_chunk_size_mb":8}}'

# Seed demo data (Clerk JWT)
curl -X POST http://127.0.0.1:8000/settings/seed-demo-data \
  -H "Authorization: Bearer <clerk_jwt>"

# Tests
RUN_MONGO_TESTS=0 pytest -q

# Git
git log --oneline -5
# (local) UI pages: Agents, Settings, Events, Brain tabs
# cc42f8cb Qwen cache + strict schema + efficiency metrics
# 3620840d Wire SAG metadata through MCP check_intercept
# 3eb282df Initial commit (on GitHub)
```

---

## Related local docs (not in git)

| File | Purpose |
|------|---------|
| `SUBMISSION_WRITEUP.md` | Short form for Devpost submission form |
| `E2E_VERIFICATION_REPORT_RERUN.md` | Full test evidence |
| `Company Brain/` Obsidian vault | Visual architecture graph |

---

**Built for the MemoryAgent track. They retrieve. We verify.**
