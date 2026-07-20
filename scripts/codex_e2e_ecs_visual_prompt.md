# Company Brain — Visual Browser E2E (Live Alibaba ECS)

You are visually verifying the **deployed** Company Brain demo with **real browser automation**. Do **not** rebuild features. Fix only blockers that stop verification (e.g. obvious UI crash). Prefer reporting over coding.

## Target (production-shaped ECS)

| Item | Value |
|------|--------|
| Base URL | `http://8.218.174.77` |
| Brain | `http://8.218.174.77/app/brain` |
| Health | `http://8.218.174.77/api/health` |
| Auth | **None** — open demo, org `integrations-demo` |
| Host notes | `ecs.r9i.xlarge` → **no TDX guest**; expect **RSA audit fallback** (not hardware TDX) |
| Screenshots | `e2e-artifacts/ecs-visual-<YYYYMMDD>/` under repo `E:\qwen\company-brain` |
| Report | `E2E_ECS_VISUAL_REPORT.md` at repo root |

If the site is unreachable, say so immediately (SG / nginx / container) and stop.

## Tools

1. Playwright Chromium **or** Codex in-app browser.
2. Full-page screenshot after every meaningful state.
3. Capture console errors + failed `/api/*` (4xx/5xx).
4. Prefetch API OK, but **every UI checkpoint must be done in the browser**.

## Deliverable

Write `E2E_ECS_VISUAL_REPORT.md` with:

1. Pass / Fail / Partial per checklist row  
2. Screenshot path per checkpoint  
3. JSON snippets: health, `/api/attestation/status`, live-config 8 vs 25, one `/api/sag/evaluate` body  
4. Console / network summary  
5. Verdict line: `ECS READY TO RECORD` **or** the single blocker  

**Hard fail:** Brain toggle to **8MB** does not show red **SUSPENDED**, or **25MB** does not show green **AUTO_EXECUTE**, for skill `data-export-large-file-timeout`.

---

## PART 0 — API preflight (curl / fetch, no browser)

| # | Check | Expect |
|---|--------|--------|
| 0.1 | `GET http://8.218.174.77/api/health` | 200; `status=ok`; `qwen_configured=true`; `embedding_healthy=true`; `db.connected=true` |
| 0.2 | `GET http://8.218.174.77/attestation/status` | 200; `mode=rsa_fallback` (or tdx if somehow present); `tdx_guest=false` on r9i |
| 0.3 | `GET http://8.218.174.77/api/settings/live-config` | 200; org `integrations-demo`; has `export_chunk_size_mb` |
| 0.4 | `POST http://8.218.174.77/api/settings/live-config` `{"export_chunk_size_mb":8}` | 200; SAG suspended for `data-export-large-file-timeout` |
| 0.5 | `POST …/live-config` `{"export_chunk_size_mb":25}` | 200; SAG auto_execute / active for same skill |
| 0.6 | `POST http://8.218.174.77/api/sag/evaluate` body `{"skill_id":"data-export-large-file-timeout","metadata":{"export_chunk_size_mb":8},"attest":true}` | `decision=suspended`; `trace` present; `integrity.mode=rsa` (or tdx) |
| 0.7 | `GET http://8.218.174.77/api/brain/skills` | Includes `data-export-large-file-timeout` |
| 0.8 | `GET http://8.218.174.77/api/brain/intercepts?limit=20` | At least one export / horror-related intercept |

---

## PART 1 — Landing & shell

| # | Action | Expect + screenshot |
|---|--------|---------------------|
| 1.1 | Open `/` | Company Brain branding, CTA into app. `01-landing.png` |
| 1.2 | Go to Brain via CTA or `/app/brain` | No login wall. `02-brain-entry.png` |
| 1.3 | Sidebar | Shows open / demo org (`integrations-demo` if labeled); **no** Clerk Sign-in / Sign-out. `03-sidebar.png` |
| 1.4 | Hit `/sign-in` if routed | Should redirect into app, not a login product. `04-no-clerk.png` |

---

## PART 2 — Dashboard + Settings

| # | Expect | Screenshot |
|---|--------|------------|
| 2.1 | `/app/dashboard` loads metrics / judge hints | `10-dashboard.png` |
| 2.2 | `/app/settings` health + seed control usable | `20-settings.png` |
| 2.3 | If skills empty, click Seed once, wait, confirm skills appear | `21-settings-seed.png` (skip if already seeded) |

---

## PART 3 — Brain ⭐ recording gate (must look judge-ready)

Open `http://8.218.174.77/app/brain`.

| # | Action | Expect | Screenshot |
|---|--------|--------|------------|
| 3.1 | Initial load | Live chunk size visible (prefer 25); hero skill `data-export-large-file-timeout`; green **AUTO_EXECUTE** if 25 | `30-brain-initial.png` |
| 3.2 | Use **SAGToggle** / 8MB control | Red **SUSPENDED**; network `POST /api/settings/live-config` 200; optional `/api/sag/evaluate` 200 | `31-brain-8mb.png` |
| 3.3 | **EvalTrace** panel | Collapsible tree with operators (`lte`/`gt`/`and`/`not`); not empty after toggle | `32-eval-trace-8.png` |
| 3.4 | **TDXBadge / integrity** | Shows **RSA Audited** (blue) on r9i — **not** fake green TDX unless status says tdx. Click opens detail modal if present | `33-rsa-badge.png` |
| 3.5 | Switch to **25MB** | Green **AUTO_EXECUTE**; visually distinct from 3.2 | `34-brain-25mb.png` |
| 3.6 | Keyboard **`8`** (not focused in an input) | Suspended again | `35-key-8.png` |
| 3.7 | Keyboard **`2`** | Auto_execute again | `36-key-2.png` |
| 3.8 | Leave Brain → Intercepts → back to Brain | Badge/config still match last state (refetch on mount) | `37-brain-remount.png` |
| 3.9 | Tabs: skills / decisions / attestation | Decisions list recent flips; attestation tab honest about RSA/TDX | `38-decisions.png`, `39-attestation-tab.png` |

Narration check (visible copy): something like “knows when to stop trusting” / SAG live config — note if missing (soft fail).

---

## PART 4 — Intercepts

| # | Expect | Screenshot |
|---|--------|------------|
| 4.1 | `/app/intercepts` lists horror / export suspended rows | `40-intercepts.png` |
| 4.2 | Rows from today’s Brain toggles visible near top | `41-intercepts-fresh.png` |

---

## PART 5 — Agents (optional if time; real Qwen on ECS)

Only if PART 3 passes. Cap **90s** each.

| # | Agent | Expect | Screenshot |
|---|-------|--------|------------|
| 5.1 | Engineering with metadata `export_chunk_size_mb: 8` | Mentions suspend / chunk / skill | `50-eng-8.png` |
| 5.2 | Engineering with `25` | Mentions allow / auto_execute / proceed | `51-eng-25.png` |

Skip Support/Product if slow — note Partial.

---

## PART 6 — Integrity endpoints in browser Network tab

While on Brain after an 8MB flip, confirm in DevTools Network:

| # | Request | Expect |
|---|---------|--------|
| 6.1 | `POST /api/settings/live-config` | 200 |
| 6.2 | `POST /api/sag/evaluate` (if UI calls it) | 200; body has `trace` + `integrity` |
| 6.3 | No unexpected 401/500 spam | Clean |

Screenshot of Network filter optional: `60-network.png`.

---

## PART 7 — Mobile smoke (resize)

| # | Action | Expect | Screenshot |
|---|--------|--------|------------|
| 7.1 | Viewport ~390×844 | Toggle + badge still usable; no horizontal wreck | `70-mobile-brain.png` |

---

## Done criteria

- PART 0 green  
- PART 3 hard-fail items green  
- RSA badge honesty (no fake TDX on r9i)  
- Report + screenshots written  

Print final verdict as the last line of the report.
