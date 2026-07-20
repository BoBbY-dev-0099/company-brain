# Qwen Hackathon pre-submit gate

## Judge route

1. Open / and read the source tiles: Slack, Alibaba OSS, and GitHub are
   server-derived statuses, not optimistic client labels.
2. Click Run release safety check.
3. Show the ordered server trace: Slack incident -> Alibaba OSS runbook ->
   GitHub change -> Qwen Reality Memory -> deterministic SAG -> human owner.
4. Expand Audit proof for source hashes, timestamps, freshness, memory
   lineage, Qwen status, and the DecisionBrief.
5. Show Human confirmation required and the no-external-action statement.

## Must be true before submission

- [ ] Public repository, MIT license, written summary, architecture, live URL,
      and 1-3 minute video are accessible.
- [ ] The deployed readiness response shows build SHA, Qwen health, scenario
      version, and canonical counts.
- [ ] The root route is reachable over HTTPS from a fresh browser session.
- [ ] The NexaFlow overview labels each source with its actual runtime status.
- [ ] An authenticated MCP client can initialize, list tools, inspect memory,
      query evidence, and evaluate a workflow; invalid or cross-org keys fail.
- [ ] A scoped MCP write/read rehearsal shows one agent writing an
      evidence-linked note and another agent reading the same provenance.
- [ ] The optional edge profile returns cached memory with explicit
      `fresh`, `stale`, or `unavailable` status and never permits an action.
- [ ] Source status is called connected only after server configuration is
      complete. Otherwise the UI says setup_required.
- [ ] Slack HMAC, GitHub signing, OSS prefix scope, memory supersession,
      outcome gating, and no-external-action tests pass.
- [ ] Redacted Alibaba Workbench Overview and deployed health/readiness captures
      are linked from deployment materials.

## Claims to keep precise

- Qwen compiles evidence where the key is configured. The UI exposes
  unavailable or failure rather than inventing a compilation.
- Slack, Alibaba OSS, GitHub, and verified web are source-specific,
  least-privilege adapters. This is not a generic connector marketplace or
  browser credential flow.
- MCP returns governed recommendations and provenance. It cannot perform
  company actions.
- OAuth 2.1, per-company secret-vault onboarding, broad RBAC, and a connector
  marketplace are post-hackathon work.
