# Company Brain — Visual Browser E2E (Post Align-Demo-UX)

You are verifying the **Company Brain** hackathon demo with **real browser automation** and **visual proof**. Do **not** add product features. Fix only blockers that stop the test. Use **real Qwen** where agents run (no mocked LLM).

## Environment

- Repo: `E:\qwen\company-brain`
- API: `http://127.0.0.1:8000` — `GET /health` → `embedding_healthy: true`, `qwen_configured: true`
- UI: `http://127.0.0.1:5174` (try `5173` if needed)
- **No Clerk / no login**
- Open org: **`integrations-demo`** (sidebar must say this)
- Screenshots: `e2e-artifacts/visual-<YYYYMMDD>-demo-ux/` (create dated folder)
- Python: `E:\qwen\company-brain\.venv\Scripts\python.exe`

If API/UI/Mongo down, start them, then continue.

## Tools

1. Playwright Chromium or Codex in-app browser.
2. Full-page screenshot after every meaningful UI state.
3. Capture console errors + unexpected `/api/*` 401/500.
4. Prefetch API OK; **every UI feature below must be exercised in the browser**.

## Deliverable

Write `E2E_VISUAL_BROWSER_REPORT.md` at repo root:

1. Pass / Fail / Partial for every checklist item
2. Screenshot path per checkpoint
3. Live-config + SAG JSON snippets (8 vs 25)
4. Console/network summary
5. One-line verdict: `READY TO RECORD` or the **single** blocker

**Hard fail:** Brain Switch to 8MB does not show giant **SUSPENDED** (red) on `data-export-large-file-timeout`, or Switch to 25MB does not show giant **AUTO_EXECUTE** (green). Shadow skill winning = FAIL.

---

## PART 0 — API preflight

| # | Check | Expect |
|---|--------|--------|
| 0.1 | `GET /health` | 200; ok; embeddings + qwen true |
| 0.2 | `GET /settings/live-config` | 200; `org_id=integrations-demo`; has `export_chunk_size_mb` |
| 0.3 | `POST /settings/live-config` `{"export_chunk_size_mb":8}` | 200; `sag.result=suspended`; skill `data-export-large-file-timeout` (or `sag: null` only if skill missing — that is FAIL for demo org) |
| 0.4 | `POST /settings/live-config` `{"export_chunk_size_mb":25}` | 200; `sag.result=auto_execute`; same skill |
| 0.5 | `GET /brain/intercepts` | Includes a `[horror-story]` suspended row for export skill |

---

## PART 1 — Landing & nav

| # | Action | Expect + screenshot |
|---|--------|---------------------|
| 1.1 | Open `/` | Company Brain, trust one-liner, CTA to 30s demo / Brain. `01-landing.png` |
| 1.2 | CTA → Brain | Lands `/app/brain`, no sign-in. `02-from-landing.png` |
| 1.3 | `/sign-in`, `/sign-up` | Redirect `/app/dashboard`. `03-signin-redirect.png` |
| 1.4 | Sidebar | `org: integrations-demo`, open mode, no Clerk/Sign Out |

---

## PART 2 — Dashboard + Settings

| # | Expect | Screenshot |
|---|--------|------------|
| 2.1 | Dashboard metrics + judge script / Brain link | `10-dashboard.png` |
| 2.2 | Settings health + Seed (already seeded OK) | `20-settings.png`, `21-settings-seed.png` |

---

## PART 3 — Brain ⭐ recording gate (live-config UX)

Open `/app/brain`.

| # | Action | Expect | Screenshot |
|---|--------|--------|------------|
| 3.1 | Initial load (refetch on mount) | Live config shows a number (prefer **25** after seed); hero skill card visible; badge green **AUTO_EXECUTE** if 25 | `30-brain-initial.png` |
| 3.2 | Click **Switch to 8MB** | **Optimistic** instant red **SUSPENDED**; status mentions skill; network `POST /api/settings/live-config` 200 | `31-brain-8mb.png` |
| 3.3 | Click **Switch to 25MB** | Instant green **AUTO_EXECUTE**; differentiated from 3.2 | `32-brain-25mb.png` |
| 3.4 | Keyboard **`8`** (not in an input) | Flips to suspended again | `33-brain-key-8.png` |
| 3.5 | Keyboard **`2`** | Flips to auto_execute | `34-brain-key-2.png` |
| 3.6 | Navigate to Intercepts then **back to Brain** | Config + badge match last toggle (refetch-on-mount) | `35-brain-remount.png` |
| 3.7 | Skills / decisions / attestation tabs | Still work; decisions show recent suspend + auto_execute | `36-brain-decisions.png`, `37-brain-attestation.png` |

Hero card must show audit line like `invalidated_if … | current: N`.

---

## PART 4 — Intercepts

| # | Expect | Screenshot |
|---|--------|------------|
| 4.1 | List includes **horror-story** suspended export row | `40-intercepts.png` |
| 4.2 | Fresh rows from Brain toggles (8 and/or 25) appear | same or `41-intercepts-fresh.png` |

---

## PART 5 — Agents (real Qwen, ≤120s each)

| # | Agent | Expect | Screenshot |
|---|-------|--------|------------|
| 5.1 | Engineering metadata `export_chunk_size_mb: 8` | Suspend/SAG path; skill `data-export-large-file-timeout` | `50-eng-8.png` |
| 5.2 | Engineering `export_chunk_size_mb: 25` | Different vs 5.1 (auto_execute / active) | `51-eng-25.png` |
| 5.3 | Support refund ticket | Answer about refunds/policy | `52-support.png` |
| 5.4 | Product two sessions | Both answer; B may continue | `53-product-a.png`, `54-product-b.png` |

---

## PART 6 — Events + API Keys + Onboard

| # | Action | Expect | Screenshot |
|---|--------|--------|------------|
| 6.1 | Events load + optional compile | Timeline OK | `60-events.png` |
| 6.2 | After any compile, re-check Brain 8/25 | SAG flip still works | `63-post-compile-8.png`, `64-post-compile-25.png` |
| 6.3 | API Keys create + revoke | One-time key; revoke (native confirm OK to complete via API if dialog stalls) | `70–72` |
| 6.4 | Onboard | All Set; org label **integrations-demo** | `73-onboard.png` |

---

## PART 7 — Polish

| # | Check |
|---|--------|
| 7.1 | No React crash / blank page |
| 7.2 | No Clerk / Sign In / Sign Out |
| 7.3 | Active sidebar styling |
| 7.4 | Page console clean (prefer `[]`) |
| 7.5 | No unexpected open-mode 401/500 |

---

## Constraints

- Do not reintroduce Clerk or rebuild `/api/compile` schemas
- Do not change core SAG / MCP tool names
- Missing Brain toggle or badge = FAIL with screenshot
- Qwen timeout: retry once, then FAIL that item

## Start order

0 → 1 → 2 → **3 (critical)** → 4 → 5 → 6 → 7 → write report.

Begin now. Be thorough. The live-config 8/25 badge flip is the recording gate.
