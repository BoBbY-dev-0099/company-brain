# Company Brain — ECS Visual E2E Report

**Target:** `http://8.218.174.77`  
**Org:** `integrations-demo` (open demo; no authentication)  
**Executed:** 2026-07-18 (Asia/Kathmandu)  
**Browser:** standalone Playwright Chromium against the deployed ECS instance. The Codex in-app browser locally returned `ERR_BLOCKED_BY_CLIENT` before contacting the host; Chromium reached the same production URL with HTTP 200, so this was an automation-client restriction, not an ECS availability issue.

All UI checkpoints below were exercised in the browser. Screenshots are full-page PNGs under `e2e-artifacts/ecs-visual-20260718/`.

## Checklist results

### Part 0 — API preflight

| Check | Status | Evidence |
|---|---|---|
| 0.1 `GET /api/health` | **Pass** | 200; `status=ok`, Qwen configured, embeddings healthy, MongoDB connected. |
| 0.2 `GET /attestation/status` | **Pass** | 200; `mode=rsa_fallback`, `tdx_guest=false`, matching the r9i host expectation. |
| 0.3 `GET /api/settings/live-config` | **Pass** | 200; `org_id=integrations-demo`, `export_chunk_size_mb` present. |
| 0.4 `POST /api/settings/live-config` with 8MB | **Pass** | 200; hero skill returned `suspended`. |
| 0.5 `POST /api/settings/live-config` with 25MB | **Pass** | 200; hero skill returned `auto_execute` / `active`. |
| 0.6 `POST /api/sag/evaluate` at 8MB | **Pass** | `decision=suspended`; operator trace and RSA integrity evidence present. |
| 0.7 `GET /api/brain/skills` | **Pass** | 200; eight skills include `data-export-large-file-timeout`. |
| 0.8 `GET /api/brain/intercepts?limit=20` | **Pass** | 200; returned the export horror-story suspension plus current export flips. |

### Part 1 — Landing and shell

| Check | Status | Screenshot / evidence |
|---|---|---|
| 1.1 Landing branding and CTA | **Pass** | `e2e-artifacts/ecs-visual-20260718/01-landing.png` — Company Brain, CTA, and 30-second demo copy visible. |
| 1.2 Brain entry without login wall | **Pass** | `e2e-artifacts/ecs-visual-20260718/02-brain-entry.png` |
| 1.3 Open/demo-org sidebar, no Clerk controls | **Pass** | `e2e-artifacts/ecs-visual-20260718/03-sidebar.png` — `org: integrations-demo`, `open mode · no login`; no sign-in/out controls. |
| 1.4 `/sign-in` does not expose a login product | **Pass** | `e2e-artifacts/ecs-visual-20260718/04-no-clerk.png` — routed directly to the open dashboard shell. |

### Part 2 — Dashboard and settings

| Check | Status | Screenshot / evidence |
|---|---|---|
| 2.1 Dashboard metrics and judge hints | **Pass** | `e2e-artifacts/ecs-visual-20260718/10-dashboard.png` — visible 30-second judge script and eight active skills. |
| 2.2 Settings health and seed control | **Pass** | `e2e-artifacts/ecs-visual-20260718/20-settings.png` — healthy system/Qwen/embedding indicators and visible **Seed Demo Data** control. |
| 2.3 Seed when empty | **Pass** | Skipped correctly: browser already showed eight seeded skills, including the SAG hero skill. |

### Part 3 — Brain recording gate

| Check | Status | Screenshot / evidence |
|---|---|---|
| 3.1 Initial 25MB Brain state | **Pass** | `e2e-artifacts/ecs-visual-20260718/30-brain-initial.png` — 25MB and green **AUTO_EXECUTE** for `data-export-large-file-timeout`. |
| 3.2 UI 8MB toggle | **Pass** | `e2e-artifacts/ecs-visual-20260718/31-brain-8mb.png` — red **SUSPENDED**; browser observed `POST /api/settings/live-config` 200 and `POST /api/sag/evaluate` 200. |
| 3.3 Evaluation trace | **Pass** | `e2e-artifacts/ecs-visual-20260718/32-eval-trace-8.png` — expanded `and` / `not` / `or` / `lte` / `gt` tree. |
| 3.4 Integrity badge honesty | **Pass** | `e2e-artifacts/ecs-visual-20260718/33-rsa-badge.png` — blue **RSA Audited** badge; no false green TDX claim. No badge detail action was exposed. |
| 3.5 UI 25MB toggle | **Pass** | `e2e-artifacts/ecs-visual-20260718/34-brain-25mb.png` — green **AUTO_EXECUTE**, visually distinct from 8MB. |
| 3.6 Keyboard `8` | **Pass** | `e2e-artifacts/ecs-visual-20260718/35-key-8.png` — returned to red **SUSPENDED**. |
| 3.7 Keyboard `2` | **Pass** | `e2e-artifacts/ecs-visual-20260718/36-key-2.png` — returned to green **AUTO_EXECUTE** / 25MB. |
| 3.8 Intercepts → Brain remount | **Pass** | `e2e-artifacts/ecs-visual-20260718/37-brain-remount.png` — remount refetched and displayed the final 25MB / **AUTO_EXECUTE** state. |
| 3.9 Decisions and attestation tabs | **Pass** | `e2e-artifacts/ecs-visual-20260718/38-decisions.png` shows fresh flip history; `e2e-artifacts/ecs-visual-20260718/39-attestation-tab.png` shows **Not verified** and the RSA fallback narrative. |
| Narration copy | **Pass** | Visible: “Memory that knows when to stop trusting itself” and live-SAG toggle instructions. |

### Part 4 — Intercepts

| Check | Status | Screenshot / evidence |
|---|---|---|
| 4.1 Export/horror suspended rows | **Pass** | `e2e-artifacts/ecs-visual-20260718/40-intercepts.png` |
| 4.2 Fresh Brain flips near top | **Pass** | `e2e-artifacts/ecs-visual-20260718/41-intercepts-fresh.png` — recent suspended and auto-execute export decisions shown. |

### Part 5 — Agents

| Check | Status | Screenshot / evidence |
|---|---|---|
| 5.1 Engineering, metadata 8 | **Pass** | `e2e-artifacts/ecs-visual-20260718/50-eng-8.png` — returned **BLOCK** because 8 satisfies the `lte 10` invalidation; completed in 2.5s. |
| 5.2 Engineering, metadata 25 | **Pass** | `e2e-artifacts/ecs-visual-20260718/51-eng-25.png` — returned **AUTO-EXECUTE PRE-FLIGHT (active)** and the existing async `/jobs/*` recommendation; completed within the 90s cap (55.3s). |

Support and Product were intentionally skipped because the requested Engineering examples passed.

### Part 6 — Browser network integrity

| Check | Status | Evidence |
|---|---|---|
| 6.1 UI `POST /api/settings/live-config` | **Pass** | Browser observed 200 after both the 8MB and 25MB flips. |
| 6.2 UI `POST /api/sag/evaluate` | **Pass** | Browser observed 200 after both flips; its body supplied the rendered trace and RSA integrity result. |
| 6.3 No unexpected 401/500 | **Pass** | No browser-observed `/api/*` 4xx/5xx and no browser console errors. |

### Part 7 — Mobile smoke

| Check | Status | Screenshot / evidence |
|---|---|---|
| 7.1 390 × 844 Brain viewport | **Fail** | `e2e-artifacts/ecs-visual-20260718/70-mobile-brain.png` — no document overflow (`scrollWidth=390`), but the fixed desktop sidebar consumes about 240px, leaving the config card/toggle compressed and clipped. The control is not comfortably usable at this width. |

## Required API JSON evidence

### `GET /api/health`

```json
{
  "status": "ok",
  "db": { "connected": true, "db": "companybrain" },
  "qwen_configured": true,
  "embedding_healthy": true
}
```

### `GET /api/attestation/status`

```json
{
  "tdx_guest": false,
  "tdx_binary": false,
  "mode": "rsa_fallback"
}
```

### Live config: 8MB versus 25MB

```json
// POST /api/settings/live-config {"export_chunk_size_mb":8}
{
  "org_id": "integrations-demo",
  "metadata": { "export_chunk_size_mb": 8 },
  "sag": {
    "result": "suspended",
    "applicability_status": "suspended",
    "skill_id": "data-export-large-file-timeout"
  }
}

// POST /api/settings/live-config {"export_chunk_size_mb":25}
{
  "org_id": "integrations-demo",
  "metadata": { "export_chunk_size_mb": 25 },
  "sag": {
    "result": "auto_execute",
    "applicability_status": "active",
    "skill_id": "data-export-large-file-timeout"
  }
}
```

### `POST /api/sag/evaluate`

Request body:

```json
{
  "skill_id": "data-export-large-file-timeout",
  "metadata": { "export_chunk_size_mb": 8 },
  "attest": true
}
```

Response evidence (trimmed only to omit the long RSA signature):

```json
{
  "skill_id": "data-export-large-file-timeout",
  "decision": "suspended",
  "status": "suspended",
  "trace": {
    "node": "and",
    "args": [
      { "node": "not", "args": [{ "node": "or", "args": [{ "node": "lte", "result": true }]}]},
      { "node": "and", "args": [{ "node": "gt", "result": false }]}
    ],
    "result": false
  },
  "integrity": {
    "mode": "rsa",
    "tdx_fallback": true,
    "decision": "suspended",
    "algorithm": "RSA-PSS-SHA256"
  }
}
```

## Console and network summary

- Browser console errors: **0** across landing, dashboard, settings, Brain, tabs, intercepts, mobile, and both Engineering runs.
- Browser-observed failed `/api/*` responses: **0**.
- Brain toggles each made `POST /api/settings/live-config` **200**, `POST /api/sag/evaluate` **200**, then refreshed skills with `GET /api/brain/skills` **200**.
- The two real Engineering calls returned `POST /api/agents/engineering/run` **200**.
- The Brain route keeps a live connection, so `networkidle` does not settle; checks used DOM-loaded plus rendered-state waits. This is expected for the page’s SSE behavior, not a request failure.

## Verdict

Desktop recording gate is green: Part 0, all Part 3 hard-fail checks, RSA honesty, and network evidence passed. The 390px mobile layout failure is non-gating for the desktop recording but should be repaired before claiming mobile readiness.

**ECS READY TO RECORD**
