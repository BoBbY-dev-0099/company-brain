# NexaFlow Fulfillment Release Runbook

## Runtime safety requirement

Fulfillment workers require at least 24 MiB of memory before release promotion.

The merged worker configuration must meet or exceed this minimum before a release can proceed.

## Incident hold

Release promotion must remain paused while any linked SEV-2 incident is open.

The engineering release owner must review the incident and confirm the runtime configuration before promotion.

## Human approval boundary

Company Brain may recommend suspending or resuming a release, but it must not deploy, change runtime configuration, or close an incident. A human engineering owner confirms the final outcome.

## Evidence interpretation rules

Company Brain may use only fresh, available, decision-ready evidence from all three configured sources:

1. Slack `#ops-incidents` supplies the current incident state.
2. This runbook in Alibaba Cloud OSS supplies the approved minimum memory requirement.
3. A merged GitHub pull request supplies the effective worker memory configuration.

The newest source record wins only after its signature, source identity, timestamp, and content hash have been verified. Older records remain in the audit history and must never be silently overwritten.

If a newer runbook changes the approved threshold, the previous runbook memory becomes superseded. The release check must use the current approved runbook and retain the supersession link for audit.

## Release decision rules

### Suspend: memory regression

Suspend release promotion when the merged value of `NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB` is below the current runbook minimum, even if no incident is open.

Recommended action: route the release to the NexaFlow engineering release owner, cite the runbook and merged pull request, and require a human decision.

### Suspend: active incident

Suspend release promotion when a fresh Slack message identifies an open SEV-1 or SEV-2 incident, OOM, out-of-memory condition, or explicit pause-promotion instruction.

Recommended action: keep promotion paused until the incident is resolved and the engineering owner confirms the runtime configuration.

### Review required: evidence is incomplete

Return `review_required` when any required source is missing, stale, unavailable, still processing, unsigned, outside the configured scope, or cannot be parsed safely.

Never infer that a release is safe from missing evidence. Never fabricate a Qwen memory claim or a deterministic safety result.

### Allow pending human confirmation

When the merged worker memory meets or exceeds the current runbook minimum and the linked incident is explicitly resolved, the result may be `allow` or `approved_for_review` depending on the configured SAG template.

The result still requires human confirmation in the NexaFlow console. Company Brain does not deploy the release automatically.

## Judge and regression test cases

These cases are safe synthetic records for local rehearsal. They must run against the same source ledger and release-check endpoint as real provider events.

### Case A — current demo suspension

- Slack: `SEV-2: fulfillment workers are OOM. Pause promotion for the release until the incident is resolved.`
- Runbook: minimum worker memory is `24 MiB`.
- GitHub merged PR: `+NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=8`.
- Expected verdict: `suspended`.
- Expected reason: the worker is below the approved threshold and the incident remains open.

### Case B — safe configuration, resolved incident

- Slack: `SEV-2 fulfillment incident resolved and mitigated; promotion may be considered after validation.`
- Runbook: minimum worker memory is `24 MiB`.
- GitHub merged PR: `+NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=32`.
- Expected verdict: `proceed_with_human_approval`.
- Expected reason: the worker meets the runbook and the incident is explicitly resolved.

### Case C — open incident with safe memory

- Slack: `SEV-2 checkout dependency incident is open. Pause promotion until mitigation is verified.`
- Runbook: minimum worker memory is `24 MiB`.
- GitHub merged PR: `+NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=32`.
- Expected verdict: `suspended`.
- Expected reason: an open incident blocks promotion independently of memory safety.

### Case D — memory regression after incident resolution

- Slack: `SEV-2 fulfillment incident resolved and mitigated; promotion may be considered after validation.`
- Runbook: minimum worker memory is `24 MiB`.
- GitHub merged PR: `+NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=16`.
- Expected verdict: `suspended`.
- Expected reason: the merged configuration is below the approved runbook minimum, even though the incident is resolved.

### Case E — missing source

- Slack: present and fresh.
- Runbook: absent or not yet synced from OSS.
- GitHub: present and fresh.
- Expected verdict: `review_required`.
- Expected reason: no release may be approved without the current runbook.

### Case F — stale source

- Slack, runbook, or GitHub record: older than the configured freshness window.
- Expected verdict: `review_required`.
- Expected reason: refresh the stale source before evaluating the release.

### Case G — superseded runbook

- Older runbook: minimum `24 MiB`.
- Newer runbook: minimum `32 MiB`.
- GitHub merged PR: `+NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=24`.
- Expected verdict: `suspended` or `review_required` according to the active SAG template.
- Expected audit result: the 24 MiB memory remains linked to the older policy, while the newer 32 MiB policy is active and the prior memory is marked superseded.

### Case H — malformed or out-of-scope evidence

- Provider event has an invalid signature, wrong Slack team/channel, unmerged GitHub PR, unsupported file type, or a runbook with no parseable memory requirement.
- Expected verdict: `review_required`.
- Expected behavior: reject or quarantine the source record, preserve the failure reason, and do not create an active memory claim.

## Operational boundaries

- Slack ingestion is read-only and never posts a message.
- Alibaba Cloud OSS access is read-only and never uploads, edits, or deletes a runbook.
- GitHub ingestion accepts only allowlisted merged pull requests.
- MCP and REST can inspect evidence and recommend an action, but cannot deploy, alter runtime configuration, close incidents, or approve the release.
- Every decision must expose its cited source records, freshness, Qwen status, memory lineage, deterministic SAG trace, owner, and human outcome.
