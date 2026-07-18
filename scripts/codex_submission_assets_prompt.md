# Task: Generate hackathon submission architecture + docs assets

Repo: `E:\qwen\company-brain`  
Track: MemoryAgent · Qwen Cloud Global AI Hackathon 2026

## Context (do not rebuild the product)

Company Brain already works locally (READY TO RECORD). You must produce **submission documentation assets** only. Do not change SAG core, MCP tool names, or APIs except tiny doc fixes.

## Deliverables (create these files)

### 1. `docs/ARCHITECTURE.md`

Clear architecture doc for judges including:

1. **One-paragraph system summary**
2. **Mermaid system diagram** (agents / UI → FastAPI → interceptor+SAG → Mongo → Qwen DashScope → SSE back to UI)
3. **Mermaid SAG sequence** for the 8MB vs 25MB flip (`POST /settings/live-config` → decisions/check → suspended vs auto_execute)
4. **Component table**: frontend pages, backend modules (`interceptor`, `applicability`, `compiler`, `mcp`, `agents`, `integrations/`)
5. **Data model** (skills provenance applies_if/invalidated_if, intercept_log, org_configs live metadata)
6. **Qwen usage map**: which calls use `qwen-plus` vs `text-embedding-v3`
7. **Honest TEE note**: attestation envelope vs production TDX

Use accurate paths from this repo. Prefer mermaid `flowchart` / `sequenceDiagram`.

### 2. `docs/ARCHITECTURE.mmd`

Standalone mermaid source of the **main system diagram** only (so it can be rendered to PNG later).

### 3. `docs/SUBMISSION_CHECKLIST.md`

Map against official checklist + weighted judging:

| Weight | Criterion |
|--------|-----------|
| 30% | Innovation & AI Creativity |
| 30% | Technical Depth & Engineering |
| 25% | Problem Value & Impact |
| 15% | Presentation & Documentation |

For each: **how Company Brain scores**, evidence (files/features), and **gaps**.

Submission checklist status (mark Done / TODO):

- Public GitHub repo URL
- Open-source LICENSE visible on repo
- 1–3 min video demo
- Architecture diagram (link to ARCHITECTURE.md + mmd)
- Written summary (link HACKATHON_WRITEUP.md)
- Proof of Alibaba Cloud Deployment (ECS/SAS screenshots — note if only local Docker ECS-mimic today)
- No cloning official starter as the whole product

### 4. `docs/JUDGING_ALIGNMENT.md`

Short scorecard: Green / Yellow / Red per criterion with one sentence each. Call out **Alibaba Cloud deployment proof** and **LICENSE** as the main remaining blockers if missing.

### 5. Optional: render diagram

If `mmdc` (mermaid-cli) or similar is available, render `docs/ARCHITECTURE.mmd` → `docs/architecture.png`. If not available, leave mmd only and note the render command.

### 6. `LICENSE`

If no LICENSE file exists at repo root, add **MIT License** with copyright `Copyright (c) 2026 Company Brain contributors`.

## Constraints

- Do not commit or push
- Do not invent an ECS public IP — if not deployed, mark deployment proof as TODO
- Keep writeups honest (SAG is real; TEE attestation is mock/envelope)

## Done when

All listed markdown files exist and mermaid diagrams are valid. Print a short summary of files created.
