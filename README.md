# Company Brain

Operating Memory Primitive for agent fleets — Qwen Cloud Global AI Hackathon 2026 (MemoryAgent track).

Company Brain is not a chatbot, and it is not an agent. It is a
**memory-and-governance layer** that any AI agent — yours, ours, or
anyone's — plugs into via MCP or a REST API. Agents call in before
acting; the brain tells them whether their planned action matches
something the fleet has already learned, and whether that lesson
still holds given the live state of the system.

We built three example agents (support, engineering, product)
purely to prove this mechanism works end-to-end. They are not the
product — they are the smallest possible demonstration that shared,
decaying, precondition-checked memory changes what an agent actually
does, not just what it retrieves.

## Who this is for

Teams already running multiple independent AI agents who want those
agents to share what they've learned — without building a shared
memory and governance layer from scratch. This is infrastructure,
not an application.

## Semantic Applicability Gate (SAG)

SAG is a deterministic, no-LLM layer that checks whether a matched skill's
preconditions still hold in the current live context before it is allowed to
block or auto-execute a decision. Each skill can declare `applies_if` and
`invalidated_if` conditions against keys passed in the request metadata.
The interceptor evaluates these conditions after the relevance gate and before
reinforcement.

**Current scope:** SAG evaluates live context supplied via the `metadata`
field on `POST /decisions/check` and on the MCP `check_intercept` tool.
Pass config values, deploy flags, or other runtime state as metadata keys
so each skill's `applies_if` / `invalidated_if` preconditions are checked
before block, warn, or auto-execute. The engineering agent's pre-flight
check forwards request metadata into the same path.

### Known limitations

- **Concurrency:** skill reinforcement now uses an atomic
  aggregation-pipeline update (`$inc` on a matched document), so
  concurrent intercepts on the same skill no longer drop increments.
  It still needs load testing at production scale.
- **Contradiction resolution:** when multiple skills match one
  decision, the highest-scoring match wins with no arbitration
  between conflicting recommendations. In our own research across
  five reference memory systems (gbrain, Hermes Agent, Claude Code,
  Codex, Cursor), none of them solve this either — it's an open
  problem in the field, and it's our next milestone.
- **Data governance:** compiled skills currently store raw event
  content verbatim, with no PII redaction or sensitivity
  classification. Any production deployment would need this before
  handling real customer data.

### Security fix: org-scoped reinforcement and intercept logging

A prior implementation of `check_decision` called `store.reinforce_skill()`
and `store.log_intercept()` without passing the authenticated `org_id`. This
caused every reinforcement and every intercept log entry to be written against
the `default` org, regardless of which Clerk organization or API key made the
request — a real multi-tenancy leak. The current code passes `org_id` through
the entire interceptor path, so skills, reinforcement counts, and intercept
logs stay scoped to the calling org.

## Stack

| Layer    | Choice                                                               |
| -------- | -------------------------------------------------------------------- |
| LLM      | Qwen 3 (`qwen-plus`) via DashScope international compatible-mode     |
| Embeddings | Qwen `text-embedding-v3` (1024-dim)                                |
| Database | MongoDB 7 single-node replica set (Motor async driver)               |
| Backend  | FastAPI + sse-starlette + FastMCP (mounted at `/mcp/sse`)            |
| Frontend | React 18 + Vite + Tailwind + Framer Motion                           |
| Cloud    | Alibaba Cloud ECS + nginx + systemd                                  |

## Three demo agents

- **Support agent** — recalls relevant skills, resolves a ticket, compiles the resolution back to the brain.
- **Engineering agent** — runs a brain pre-flight intercept *before* the LLM call. PRs that match an existing skill get blocked or warned.
- **Product agent** — bridges sessions: when the same user returns, the agent prepends a cross-session context line referencing prior intents and any skills compiled since.

## Quick start

```bash
# 1. Mongo (single-node replica set; required for change streams + TTL)
cd company-brain
docker compose up -d
docker compose exec mongodb mongosh --quiet --eval "rs.status().ok || rs.initiate({_id:'rs0', members:[{_id:0, host:'localhost:27017'}]})"

# 2. Backend
python -m venv .venv
.venv\Scripts\activate              # PowerShell:  .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env              # paste your DashScope key
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# 3. Frontend
cd frontend
npm install
npm run dev                          # http://localhost:5173
```

The first backend boot seeds 8 realistic skills + 3 demo sessions if the
brain is empty, and (if `QWEN_API_KEY` is set) backfills embeddings for
each seeded skill.

## Smoke test

```bash
# health
curl localhost:8000/health

# read seeded skills
curl localhost:8000/brain/skills

# the engineering pre-flight intercept demo
curl -X POST localhost:8000/agents/engineering/run \
  -H 'content-type: application/json' \
  -d '{"user_message":"PR adds a synchronous CSV export endpoint at /export/csv. Returns the file inline. Should be fine for our 30MB exports."}'

# follow the SSE stream while you do the above (separate terminal)
curl -N localhost:8000/stream
```

## API

| Method | Path                          | Purpose                                                             |
| ------ | ----------------------------- | ------------------------------------------------------------------- |
| GET    | `/health`                     | service + db status, skill count, qwen-configured flag              |
| POST   | `/events`                     | compile a raw event into a skill, persist, propagate                |
| POST   | `/decisions/check`            | hybrid keyword + cosine intercept check                             |
| GET    | `/brain/skills`               | list active skills (filter by `?domain=`)                           |
| GET    | `/brain/skills/{skill_id}`    | full skill detail                                                   |
| POST   | `/settings/seed-demo-data`    | idempotent org-scoped seed of the demo skill set (Clerk JWT or API key) |
| POST   | `/agents/{kind}/run`          | run support / engineering / product agent (Chat Completions + MCP)  |
| GET    | `/sessions/{user_id}`         | sessions for a user (cross-session demo)                            |
| GET    | `/sessions/by-id/{id}`        | one session                                                         |
| GET    | `/stream`                     | SSE event stream (skill_compiled, decision_intercepted, …)          |
| GET    | `/mcp/sse`                    | MCP server (recall_skills, check_intercept, compile_experience)     |
| GET    | `/mcp/attestation`            | mock TDX attestation envelope                                       |

## Tests

```bash
RUN_MONGO_TESTS=0 pytest -x          # unit (default; no DB required)
RUN_MONGO_TESTS=1 pytest -x          # full suite incl. store integration
```

## Deploy (Alibaba Cloud ECS)

```bash
# After `git clone` + venv setup:
sudo cp deploy/companybrain.service /etc/systemd/system/
sudo cp deploy/nginx.conf /etc/nginx/sites-available/companybrain
sudo ln -sf /etc/nginx/sites-available/companybrain /etc/nginx/sites-enabled/
sudo systemctl daemon-reload
sudo systemctl enable --now companybrain
sudo nginx -t && sudo systemctl reload nginx
```

The nginx config disables proxy buffering on `/stream` and `/mcp/sse` —
without that SSE events are batched and the UI looks frozen.

## Notes on Qwen

- **Context cache (explicit):** The compiler marks its frozen >1024-token system
  prefix with `cache_control: ephemeral` on every compile call. First compile
  in an org caches the prefix at 125% input rate; subsequent compiles hit at
  10%. Toggle via `QWEN_ENABLE_EXPLICIT_CACHE=false` in `.env`.
- **Structured output (strict):** Skill compilation uses
  `response_format={"type":"json_schema","strict":true}` against a full
  `CompanyBrainSkill` JSON schema, with automatic fallback to `json_object`.
- **Parallel tool calls:** Demo agents pass `parallel_tool_calls=True` so Qwen
  can invoke `recall_skills` and `check_intercept` in one completion when useful.
- **Thinking mode:** every Chat Completions call sends
  `extra_body={"enable_thinking": False}` to keep latency predictable.
- **Agents** use Chat Completions with function-calling (the MCP tools are
  registered as OpenAI-style tools and dispatched in-process). The
  separately-mounted FastMCP server at `/mcp/sse` exposes the same tools
  to external MCP clients.
- **Efficiency metric:** `GET /settings/metrics` returns `governance_hits` and
  `est_llm_tokens_saved` — intercepts that blocked/warned/suspended before an
  agent LLM turn (~2k tokens per hit, back-of-envelope).
