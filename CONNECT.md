# Connect NexaFlow

NexaFlow is the evidence and memory checkpoint inside an existing workflow. It
does not replace Slack, Alibaba Cloud OSS, GitHub, an agent runtime, or an
operator.

~~~mermaid
flowchart LR
  S["Company source"] --> E["Evidence adapter"]
  E --> M["Qwen Reality Memory"]
  M --> C["MCP or REST check"]
  C --> H["Human-confirmed next step"]
~~~

Open Setup sources at /setup. The public console reads server-owned status, so
source labels reflect actual configuration rather than optimistic client copy.

## Operator setup

The browser never receives provider secrets. The operator configures the
selected provider through the local setup surface; values are encrypted before
MongoDB persistence and the UI receives only presence or masked values.

This is a single-deployment, administrator-controlled path. It is not a claim
of self-serve OAuth, generic marketplace installation, or production tenant
administration. Use a dedicated Slack workspace, GitHub repository, and
Alibaba OSS bucket with synthetic evidence for the public hackathon deployment.

## Source adapters

| Source | Endpoint or job | Required configuration | Boundary |
| --- | --- | --- | --- |
| Slack | POST /integrations/slack/events | Signing secret, team ID, channel IDs | Signed messages from one configured #ops-incidents channel only; persisted before acknowledgement; no Slack write. |
| Alibaba Cloud OSS | POST /operator/integrations/alibaba_oss/sync-now or worker poll | Read-only RAM AccessKey, bucket, region, prefix | Reads Markdown, text, and PDF runbooks in one private prefix; no upload, delete, or ACL change. |
| GitHub | POST /integrations/github/pr | Webhook secret, read-only token, repository allowlist | Signed, merged pull requests from allowlisted repositories. |
| Verified Web | POST /integrations/web/fetch | Exact HTTPS host allowlist | API-key protected explicit fetch with SSRF, redirect, MIME, timeout, and size controls. Not web search. |

Source events are organization-scoped immutable ledger records. Each has a
source/external ID, URL where available, raw payload hash, excerpt, source and
retrieval time, freshness, availability, ACL scope, and lifecycle stage.

## Primary release workflow

The judge-facing route uses the server-owned NexaFlow release template. The
browser supplies no organization or evidence:

~~~text
POST /api/nexaflow/release-check
{}
~~~

The server selects the newest fresh Slack, OSS, and GitHub records, parses the
runbook minimum, merged worker memory, and incident state, then returns a
DecisionBrief. Missing, stale, unavailable, unsigned, or unparseable evidence
returns review_required.

## Connect an agent with MCP

Use authenticated Streamable HTTP:

~~~text
https://brain.veriflowai.me/mcp/
X-Brain-Api-Key: cb_live_...
~~~

The server resolves the organization from the API key and ignores any
caller-supplied organization ID.

| Permission | Tools | Purpose |
| --- | --- | --- |
| mcp:read | recall_skills, inspect_memory, query_evidence | Read governed memory and source provenance. |
| mcp:check | check_intercept | Run a pre-flight memory and safety check. |
| mcp:workflow | evaluate_workflow | Return the source-aware DecisionBrief. |
| mcp:write | compile_experience | Compile a deliberate resolved experience into durable skill memory. |
| mcp:write | write_operational_note | Write an evidence-linked agent note into shared Reality Memory. |
| mcp:read | query_cross_agent_memory | Read shared notes, linked evidence, and memory lineage. |

MCP cannot record a human outcome or run a deployment, refund, feature-flag
change, GitHub write, OSS write, or Slack post. OAuth 2.1 dynamic registration,
per-company secret-vault onboarding, and self-serve provider installation are
roadmap items, not shipped claims.

### Cross-agent handoff example

The writing agent must reference evidence already present in the same
organization. The API key supplies the organization; the caller cannot choose
one.

~~~json
{
  "name": "write_operational_note",
  "arguments": {
    "note_id": "sales-acme-001",
    "agent_id": "sales-agent",
    "subject": "Acme fulfillment blocker",
    "scope": "acme",
    "claim": "Acme release concern is tied to the open fulfillment OOM incident.",
    "evidence_refs": ["slack-ingestion-id-from-query_evidence"]
  }
}
~~~

A second agent calls query_cross_agent_memory with subject Acme. The response
includes the shared note, Reality Memory ID, evidence excerpt, freshness, and
the explicit no-external-action boundary.

## Status language

- connected: server configuration is complete.
- setup_required: the provider has not been configured on the server.
- contract_ready: a supported API contract is available.
- fixture: deterministic demo evidence only.
- preview: not production-ready.
