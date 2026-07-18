# Connect Company Brain

> Company Brain does not replace a company's agents or systems. It is the
> governed memory checkpoint they call before consequential actions.

The product exposes three deliberate connection boundaries. They are visible
in the UI at `/app/connect` and returned by the server at
`GET /integration-catalog` (or `/api/integration-catalog` through nginx).
The catalog is the source of truth for runtime status; it never exposes
secrets.

| Boundary | What is available now | Runtime label |
| --- | --- | --- |
| Connect evidence | Signed GitHub merged-PR webhook intake | `connected` only when all GitHub settings are configured; otherwise `setup_required` |
| Connect a workflow | Stable REST contracts for evidence, live context, and a `DecisionBrief` | `contract_ready` |
| Connect an agent | Authenticated MCP Streamable HTTP at `/mcp/` | `connected` only on configured HTTPS with remote MCP enabled; otherwise `preview` |

`fixture` means a deterministic demo adapter or example, not a live external
integration. The submission does not claim live Slack, Stripe, Zendesk,
feature-flag, marketplace, or no-code connectors.

## 1. Connect evidence: GitHub

The implemented source connector accepts a signed merged-pull-request webhook
at:

```text
POST https://brain.veriflowai.me/integrations/github/pr
```

Before the catalog reports it as `connected`, configure all of the following
on the server:

```dotenv
GITHUB_WEBHOOK_SECRET=...
GITHUB_TOKEN=...
GITHUB_REPOS=owner/repository,owner/another-repository
```

The handler verifies GitHub's HMAC signature, keeps an explicit repository
allowlist, persists raw evidence, compiles the Qwen-backed memory, stores a
signed audit record, emits the event stream update, and creates the linked
Release Safety run before returning success. A PR with insufficient current
runtime evidence returns `review_required`; it does not invent telemetry.

This is one signed connector, not self-service GitHub App onboarding. A
GitHub App with installation-scoped tokens is a production roadmap.

## 2. Connect a workflow: REST

An existing service can call the same workflow engine used by the Decision
Queue. It submits normalized source-backed evidence plus current live context,
then receives a shared `DecisionBrief` with facts, Qwen inference, missing
evidence, provenance, freshness, deterministic SAG trace, verdict, owner, and
recommended next action.

```bash
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

curl -X POST https://brain.veriflowai.me/workflow-runs \
  -H 'Content-Type: application/json' \
  -H 'X-Brain-Api-Key: cb_live_...' \
  -d "{
    \"template_id\": \"release-safety\",
    \"evidence\": [
      {
        \"source_type\": \"github_pull_request\",
        \"source_name\": \"GitHub\",
        \"external_id\": \"acme/service#42\",
        \"occurred_at\": \"$NOW\",
        \"excerpt\": \"Merged PR #42 updates export-worker configuration.\"
      },
      {
        \"source_type\": \"runtime_metric\",
        \"source_name\": \"Runtime telemetry\",
        \"external_id\": \"export-worker-memory\",
        \"occurred_at\": \"$NOW\",
        \"excerpt\": \"export-worker effective memory limit is 25 MiB.\"
      }
    ],
    \"live_context\": {
      \"worker_memory_mb\": 25,
      \"runbook_validated\": true,
      \"deployment_window_open\": true
    }
  }"
```

Available stable REST contracts:

- `POST /workflow-runs` — evidence to memory to SAG to `DecisionBrief`
- `GET /workflow-runs/{id}` — one auditable run
- `POST /workflow-runs/{id}/outcome` — UI/REST-only human confirmation
- `POST /decisions/check` — pre-flight memory and deterministic safety check

All external company actions remain human-approved. A workflow result is a
governed recommendation, not authorization to perform a refund, deployment,
or feature-flag change.

## 3. Connect an agent: MCP

Use the canonical Streamable HTTP endpoint after TLS is verified:

```text
https://brain.veriflowai.me/mcp/
```

Every MCP request must include `X-Brain-Api-Key`. The server resolves the
organization from that key; clients cannot supply or override an `org_id`.
Each tool requires an explicit capability scope:

| MCP tool | Required key permission | Purpose |
| --- | --- | --- |
| `recall_skills` | `mcp:read` | Read relevant active company memory |
| `check_intercept` | `mcp:check` | Pre-flight check against memory and live context |
| `evaluate_workflow` | `mcp:workflow` | Run the shared evidence-to-DecisionBrief workflow engine |
| `compile_experience` | `mcp:write` | Compile a resolved experience into governed memory |

The MCP surface has no tool for recording a human outcome or executing an
external company action. The legacy `/mcp/sse` endpoint is retired and returns
`410` on the public deployment.

Browser-originated MCP requests must also match the configured origin allowlist
(`MCP_ALLOWED_ORIGINS`). Full OAuth 2.1 / dynamic-client registration is a
production next step, not a hackathon claim.

## Deployment identity

The intended public identity is `https://brain.veriflowai.me`. It becomes the
catalog's public endpoint only after the DNS record, ECS port 443, certificate,
and `PUBLIC_BASE_URL` configuration have been verified. See
[`docs/DEPLOYMENT_PROOF.md`](docs/DEPLOYMENT_PROOF.md) for the safe deployment
and proof sequence.
