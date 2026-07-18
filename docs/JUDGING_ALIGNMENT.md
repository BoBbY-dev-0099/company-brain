# Judging alignment scorecard

| Criterion | Status | Scorecard |
|---|---|---|
| Innovation & AI Creativity (30%) | Green | Company Brain pairs persistent, Qwen-compiled organizational skills with a deterministic live-context gate that can suspend stale guidance; the 8MB/25MB flip makes that distinction easy to demonstrate. |
| Technical Depth & Engineering (30%) | Yellow | FastAPI, MongoDB, FastMCP, SSE, Qwen tool calling, vector retrieval, typed SAG conditions, organization scoping, and audit logs are real, but Alibaba Cloud deployment proof is still required. |
| Problem Value & Impact (25%) | Green | The product addresses a concrete agent-fleet failure mode: losing resolved operational knowledge or applying it after conditions changed; cross-session skills plus live applicability are a credible product direction. |
| Presentation & Documentation (15%) | Yellow | The UI and written architecture are ready to support a clear walkthrough, but the public demo video and final Devpost presentation fields still need completion. |

## Main remaining blockers

1. **Alibaba Cloud deployment proof — Red until supplied.** Local Docker is explicitly an ECS mimic, not an Alibaba Cloud deployment. Capture real ECS/SAS evidence after deployment and link code that shows the Qwen Cloud integration.
2. **LICENSE visibility — Yellow until verified on GitHub.** The repository now has an MIT [LICENSE](../LICENSE), but it must be committed to the public repository and visibly recognized on its GitHub page.

Keep the TEE message exact: the attestation endpoint is a mock/envelope that demonstrates the intended integration shape, not production TDX attestation.
