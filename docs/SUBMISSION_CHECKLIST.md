# Qwen Hackathon pre-submit gate

This is a truthfulness-first checklist aligned to the [official rules](https://qwencloud-hackathon.devpost.com/rules). The submission deadline is **July 20, 2026 at 2:00 pm Pacific Time**. Do not replace proof with a local Docker run or a stale public URL.

## Judge story

| Criterion | Concrete evidence in this build | What to show |
| --- | --- | --- |
| Innovation and AI creativity | Three code-owned `WorkflowTemplate`s share one evidence → memory → live context → safe action engine. | The four-module Launchpad, not three separate agents. |
| Technical depth | Typed FastAPI workflow API, source provenance/freshness, Qwen compiler, deterministic SAG traces, Mongo persistence, SSE, durable GitHub intake, outcome gate, canonical/sandbox isolation. | A Release Safety run and its `DecisionBrief`; then the GitHub webhook lifecycle in code or logs. |
| Problem value | Release, money, and rollout risks map immediately to operators, blockers, and owners. | Why a PR, contract exception, or incident changes what an agent may safely recommend. |
| Presentation | `/` is the four-module judge route; `/app/connect` explains adoption; Brain and Agents remain technical proof. | One complete workflow, then rapid proof that the other two use the same contract. |

## Required evidence before marking the submission complete

- [ ] Public repository opens without credentials and displays the MIT license.
- [ ] Written description explains the features/functionality and points judges to `/` and the three simulations.
- [ ] Architecture diagram and the workflow API are linked from the repository.
- [ ] A public video is **under three minutes**, shows the project functioning, and is hosted on YouTube, Vimeo, or Youku.
- [ ] The deployed commit is running on Alibaba Cloud ECS or SAS.
- [ ] A redacted Workbench Overview screenshot shows the running instance (supplemental visual proof requested by the deployment packet).
- [ ] A redacted runtime capture shows `/api/health` and `/api/demo/readiness`, including build SHA, `judge-demo-v1`, Qwen configuration state, and canonical counts.
- [ ] The public four-module Launchpad loads in a fresh browser session and displays a backend-derived decision brief.
- [ ] `https://brain.veriflowai.me/` has a valid certificate, redirects HTTP to HTTPS, and shows the deployed four-module Launchpad.
- [ ] `/api/integration-catalog` truthfully labels GitHub, REST, fixtures, and MCP; public `/mcp/sse` returns 410 and authenticated `/mcp/` is tested with a scoped key.
- [ ] The repository includes a direct code-file link demonstrating Alibaba Cloud service/API use, as required by the rules; [`docs/DEPLOYMENT_PROOF.md`](DEPLOYMENT_PROOF.md) links the supplemental captured artifacts.
- [ ] Devpost includes the public URL or functional test build, repository, video, written summary, architecture, and deployment evidence. It must remain free and available for judging/testing through the judging period.

## Claims to keep precise

- Qwen compilation is real where Qwen is configured; deterministic fixture previews intentionally skip model calls.
- Release Safety implements a signed GitHub merged-PR intake; label it `connected` only when the secret, token, and explicit repository allowlist are configured. Money Safety and Rollout Safety are labelled demo fixtures using the same API contract.
- All external actions are human-approved recommendations. `auto_execute` eligibility is gated behind a persisted human-confirmed outcome; the demo does not perform external actions.
- TDX is only claimed on an eligible configured Confidential VM. Other hosts use the RSA-PSS audit fallback.
- Token savings is an estimate, not a measured production-cost result.
- MCP API keys enforce the four explicit tool scopes; full OAuth 2.1 and general enterprise RBAC remain production roadmap work.

## Final rehearsal

1. Open `/` as a judge would.
2. Read the Release Safety card aloud: source, changed condition, owner, next step.
3. Click **Simulate decision** and expand **Audit proof** to show facts, Qwen inference, missing evidence, prior memory, and SAG trace.
4. Record a human outcome and call out fixture isolation.
5. Open Money Safety and Rollout Safety for five seconds each.
6. Show `/api/demo/readiness`, Workbench proof, and the public video link.
7. Open `/app/connect` and read the one-sentence agent/workflow connection story.
