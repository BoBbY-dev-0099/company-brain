# Company Brain — Full Browser + Real-Qwen E2E

You are running a freeze-pass end-to-end verification. Do NOT add features or change product schema. Verify what exists. Fix only blockers that prevent the test from completing.

## Environment (already running)

- API: `http://127.0.0.1:8000` — health must show `embedding_healthy: true`
- UI: `http://127.0.0.1:5174` (Vite)
- Repo root: `E:\qwen\company-brain`
- Auth for API: header `X-Brain-Api-Key` (NOT Bearer for `cb_live_` keys)
- Bootstrap a clean org key if needed:
  `.\.venv\Scripts\python.exe integrations\python-client\bootstrap_api_key.py`
- Connector suite (API-level, real Qwen for W4/W5):
  `$env:BRAIN_BASE_URL='http://127.0.0.1:8000'; $env:BRAIN_API_KEY='...'; .\.venv\Scripts\python.exe integrations\python-client\connect_to_brain.py`

## Deliverable

Write `E2E_CODEX_BROWSER_REPORT.md` at repo root with:
1. Pass/Fail table for every page and action below
2. Raw evidence (status codes, key JSON snippets, screenshot paths if taken)
3. Real Qwen call proof (agent response excerpts + skill_ids)
4. Final one-line verdict: READY TO RECORD or the single blocker

## Part A — API + real Qwen (must pass first)

1. `GET /health` → ok + embedding_healthy true
2. Bootstrap API key for `integrations-demo` if needed
3. Run `integrations/python-client/connect_to_brain.py` — W1–W5 all PASS
4. Extra real Qwen agent calls with API key:
   - `POST /agents/engineering/run` with metadata `{"export_chunk_size_mb": 8}` — expect intercepted / SAG / BLOCK language
   - `POST /agents/support/run` with a refund-style ticket message — expect recall/compile path and a non-empty response
   - `POST /agents/product/run` twice same user_id different session_id — expect sessions persisted

## Part B — Browser automation (every page)

Use Playwright (install if needed: `npx playwright install chromium`) or any reliable browser automation. Prefer headed=false.

**Login:** If sign-in is required, use env vars `E2E_EMAIL` and `E2E_PASSWORD` if set. If password automation is blocked, document PARTIAL and continue with API-authenticated checks for agent pages. Do not invent credentials.

Visit and exercise each route at `http://127.0.0.1:5174`:

| Page | Route | Actions to prove |
|------|-------|------------------|
| Landing | `/` | Loads, Sign In link works |
| Sign-in | `/sign-in` | Form visible |
| Dashboard | `/app/dashboard` | Metrics/skills render (not error boundary) |
| Brain skills | `/app/brain` | Skills list > 0 after seed; select export skill |
| Brain SAG 8MB | `/app/brain` | Click Simulate 8MB → status contains suspended |
| Brain SAG 25MB | `/app/brain` | Click Simulate 25MB → status contains auto_execute or active |
| Brain decisions | `/app/brain` decisions tab | Intercepts/decisions list not empty after sims |
| Brain attestation | `/app/brain` attestation tab | TEE / attestation JSON or fields visible |
| Intercepts | `/app/intercepts` | Suspended + auto_execute entries |
| Agents | `/app/agents` | Run Engineering with metadata 8 → real Qwen response (wait up to 120s) |
| Events | `/app/events` | Page loads; optionally submit compile if Qwen available |
| Settings | `/app/settings` | Health green; Seed message if used; metrics load |
| API Keys | `/app/api-keys` | Page loads; create/list UI present |

Save screenshots under `e2e-artifacts/` for each major page.

## Part C — Console / network sanity

Note any uncaught page errors, unexpected 401/500 on demo paths, and whether SSE feed is connected or intentionally null on Dashboard.

## Constraints

- No Outcome Feedback Loop / new schema / new endpoints
- Prefer fixing only broken wiring that blocks verification
- Use real Qwen (server `.env` already has `QWEN_API_KEY`) — do not mock agent LLM calls
- Prefer `X-Brain-Api-Key` for API tests

Start now. Be thorough. Write the report when done.
