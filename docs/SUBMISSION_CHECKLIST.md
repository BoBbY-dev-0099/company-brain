# Hackathon submission checklist

This checklist is aligned to the [Qwen Cloud Global AI Hackathon overview](https://www.qwencloud.com/challenge/hackathon) and [Devpost submission requirements](https://qwencloud-hackathon.devpost.com/). It distinguishes code evidence from items that still require an externally visible submission or deployment proof.

## Weighted judging alignment

| Weight | Criterion | How Company Brain scores | Evidence | Gaps to close |
|---:|---|---|---|---|
| 30% | Innovation & AI Creativity | A memory system that does more than retrieve: experience becomes versioned skills, and the Semantic Applicability Gate can suspend a relevant skill when current operating conditions invalidate it. The 8MB/25MB flip provides a single, visible proof point. | `backend/core/{compiler,interceptor,applicability}.py`; `backend/demo/seed_data.py`; `HACKATHON_WRITEUP.md`. | Video must show the same decision text producing `suspended` at 8MB and `auto_execute` at 25MB, then explain that SAG is deterministic. Do not overclaim autonomous production execution. |
| 30% | Technical Depth & Engineering | Modular FastAPI, FastMCP/SSE, Qwen tool-calling agents, typed schema, MongoDB persistence/indexes, hybrid keyword/vector matching, organization scoping, audit log, and real SSE UI updates. | `backend/main.py`; `backend/core/`; `backend/mcp/`; `backend/agents/`; `backend/brain/store.py`; `frontend/src/hooks/useSSE.ts`; `docker-compose.yml`. | Add Alibaba Cloud deployment evidence. Keep the TEE endpoint labelled as a mock envelope, not deployed TDX. |
| 25% | Problem Value & Impact | Agent fleets repeatedly lose resolved operational experience and can reuse stale advice. Company Brain preserves the experience, retrieves it across sessions, and checks live constraints before allowing guidance to govern a decision. | `README.md`; `HACKATHON_WRITEUP.md`; `integrations/`; agent and session routes in `backend/main.py`. | State a concrete target operator/team and expected workflow in the video/writeup. Avoid unsupported quantitative impact claims. |
| 15% | Presentation & Documentation | The UI includes a judge-friendly Brain/SAG view, intercept audit trail, agents, events, and settings. These architecture and checklist assets make the backend and Qwen use explicit. | `frontend/src/pages/Brain.tsx`; `frontend/src/pages/Intercepts.tsx`; [ARCHITECTURE.md](ARCHITECTURE.md); [ARCHITECTURE.mmd](ARCHITECTURE.mmd); `HACKATHON_WRITEUP.md`. | Record and publish the demo, fill every Devpost field, and ensure the public repository shows its license in the top-level metadata. |

## Submission deliverables

| Status | Requirement | Current evidence / next action |
|---|---|---|
| TODO | Public GitHub repo URL | Git remote is configured as `https://github.com/BoBbY-dev-0099/company-brain.git`. Verify the repository is publicly reachable and paste the final URL into Devpost. |
| Done | Open-source LICENSE visible on repo | Root [LICENSE](../LICENSE) is MIT (`Copyright (c) 2026 Company Brain contributors`). Confirm GitHub recognizes it after the repository is published/updated. |
| TODO | 1-3 minute video demo | Target a ~3-minute public video (the official requirement describes a public video of about 3 minutes and permits up to 5 minutes). Record the 25MB → 8MB SAG flip, audit entry, and Qwen/MCP architecture. |
| Done | Architecture diagram | [ARCHITECTURE.md](ARCHITECTURE.md) contains the judge-facing system and SAG sequence diagrams; [ARCHITECTURE.mmd](ARCHITECTURE.mmd) is the standalone render source. PNG rendering is pending because Mermaid CLI is not installed. |
| Done | Written summary | [HACKATHON_WRITEUP.md](../HACKATHON_WRITEUP.md) is the submission-oriented product description and demo script. |
| TODO | Proof of Alibaba Cloud deployment | Current `docker-compose.yml` explicitly documents a local **ECS mimic**. Deploy the API/frontend to Alibaba Cloud, then attach ECS/SAS console screenshots and a repository link showing the Qwen Cloud API integration. Do not invent a public IP or state that local Docker is deployed. |
| Done | No cloning of an official starter as the whole product | The repository contains a bespoke React/FastAPI/MongoDB application, custom SAG/interceptor/compiler modules, and integration examples; no official starter is used as the product. Preserve this provenance in the public repository. |

## Final pre-submit gate

- [ ] Public repository loads without credentials and shows the MIT license.
- [ ] Devpost repository URL points to that repository.
- [ ] Public video URL is playable and stays within the demo time limit.
- [ ] Video visibly demonstrates 25MB `auto_execute` and 8MB `suspended` for the same seeded export skill.
- [ ] Devpost includes [ARCHITECTURE.md](ARCHITECTURE.md), [ARCHITECTURE.mmd](ARCHITECTURE.mmd), and [HACKATHON_WRITEUP.md](../HACKATHON_WRITEUP.md).
- [ ] Alibaba Cloud deployment proof is attached; local Docker is not described as a cloud deployment.
- [ ] Qwen Cloud/DashScope usage is shown in code/configuration without exposing API keys.
- [ ] TEE language remains limited to the mock attestation envelope and proposed production TDX path.
