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
      and 1-3 minute video are accessible. (Video remains to be recorded.)
- [x] The deployed readiness response shows build SHA, Qwen health, scenario
      version, and canonical counts.
- [x] The root route is reachable over HTTPS from the built-in browser and a
      fresh public request.
- [x] The NexaFlow overview labels Slack, Alibaba OSS, and GitHub with their
      actual backend-derived runtime status.
- [x] An authenticated MCP client initialized, listed all 8 tools, queried
      evidence, and checked an intercept; the final response enforced
      `external_action_permitted=false`, `human_approval_required=true`, and
      `auto_execute=false`.
- [x] Local scoped MCP tests cover one agent writing an evidence-linked note
      and another agent reading the same provenance, including idempotency and
      cross-organization rejection.
- [x] The optional edge profile returns cached memory with explicit `fresh`,
      `stale`, or `unavailable` status and never permits an action.
- [x] Source status is called connected only after server configuration is
      complete. Otherwise the UI says setup_required.
- [x] Slack HMAC, GitHub signing, OSS prefix scope, memory supersession,
      outcome gating, no-external-action, Qwen fallback, vision, and
      concurrent workflow tests pass.
- [ ] Redacted Alibaba Workbench Overview is still required; deployed
      health/readiness and HTTPS/MCP captures are linked from
      [deployment proof](DEPLOYMENT_PROOF.md).

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
