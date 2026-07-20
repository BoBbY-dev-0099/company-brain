# Architecture

NexaFlow is a source-backed operational memory system. Governance is the final
checkpoint, not the whole product.

![NexaFlow Reality Layer architecture](nexaflow-reality-architecture.svg)

The [standalone SVG architecture proof](nexaflow-reality-architecture.svg) is
submission-ready for a deck or judge walkthrough.

~~~mermaid
flowchart LR
  subgraph Sources[Read-only source adapters]
    Slack["Slack Events API\nsigned #ops-incidents input"]
    OSS["Alibaba Cloud OSS\nprivate runbook prefix"]
    GitHub["GitHub\nsigned merged PR"]
    Web["Verified web\nallowlisted HTTPS URL"]
  end
  subgraph Reality[Reality Memory]
    Ledger["Immutable source ledger\nhash + excerpt + source/retrieval time\nfreshness + availability + ACL"]
    Qwen["Qwen compiler\nclaim candidate + rationale"]
    Memory["Versioned memory\nactive + superseded + review_required"]
  end
  subgraph Decision[Governed decision gateway]
    SAG["Deterministic SAG\nevidence + live context"]
    MCP["REST + authenticated\nStreamable HTTP MCP"]
    Human["Human-confirmed outcome"]
  end
  Slack --> Ledger
  OSS --> Ledger
  GitHub --> Ledger
  Web --> Ledger
  Ledger --> Qwen --> Memory --> SAG --> MCP --> Human
  Human --> Qwen
~~~

## Ingestion lifecycle

Every source event is idempotent by organization, provider, and external ID:

accepted -> fetched -> normalized -> qwen_compiled -> reconciled -> decision_ready

Failures retain an error and stage instead of silently disappearing. The worker
service reads durable pending work. A source record contains its external ID,
URL where available, raw-payload SHA-256, redacted raw metadata, excerpt,
source timestamp, retrieval time, freshness, availability, ACL scope, and
ingestion state.

## Adapter boundaries

| Adapter | Acceptance rule | No-action rule |
| --- | --- | --- |
| Slack | HMAC signature, five-minute replay window, configured team and channel, ordinary message only. | Does not post, reply, or read outside the configured channel. |
| Alibaba Cloud OSS | Read-only RAM credentials, one configured bucket/prefix, MIME allowlist, modified-time and content-hash tracking. | Does not upload, delete, change sharing, or modify an object. |
| GitHub | Signed webhook, explicit repository allowlist, merged pull request, read-only diff fetch. | Does not merge, comment, or modify a repository. |
| Verified Web | API-key authentication, exact host allowlist, HTTPS, safe redirects, public-IP resolution, MIME/size/time controls. | Does not search the web or act as an arbitrary outbound proxy. |
| Qwen-VL image evidence | API-key authentication, image MIME/size allowlist, typed observation, image digest. | Does not persist the original image or infer a release action without human review. |

## Reality Memory

The source pipeline converts a Qwen compilation into a Reality Memory record.
It has a claim key, subject/predicate/scope, Qwen rationale, source ingestion
and evidence IDs, validity window, and deterministic state. A conflicting newer
claim never overwrites a prior one: the old record becomes superseded and
points at the replacement; uncertain cases can be review_required.

SAG reads only current memory and fresh live context. A source can enrich the
audit trail but cannot invoke an external tool or make an action authoritative.

## Decision contract

The NexaFlow release template defines required evidence, live context,
deterministic SAG predicates, memory type, owner role, and recommended action.
A run returns a shared DecisionBrief:

facts | inference | missing_evidence | excerpts/freshness | prior memory | SAG trace | verdict | owner | recommended action

The current judge route uses one real template: fulfillment release safety.
The same engine remains extensible without claiming a no-code workflow builder.

## MCP trust boundary

The remote endpoint is Streamable HTTP at /mcp/. Every request carries
X-Brain-Api-Key; server-side authentication resolves the organization and
scopes the tools. The caller cannot override the organization ID.

| Permission | Tools |
| --- | --- |
| mcp:read | recall_skills, inspect_memory, query_evidence, query_cross_agent_memory |
| mcp:check | check_intercept |
| mcp:workflow | evaluate_workflow |
| mcp:write | compile_experience, write_operational_note |

There is intentionally no MCP tool for deployment, refund, feature-flag
changes, GitHub writes, OSS writes, or Slack posting. Human outcome recording
stays in the REST/UI path.

## Positioning against adjacent company-brain patterns

This is a clean-room positioning comparison, not a claim that adjacent
projects share an implementation or feature-complete product scope.

| Dimension | `agno-agi/scout` | `caelstewart/company-brain` | NexaFlow |
| --- | --- | --- | --- |
| Memory unit | Retrieved source/context | Connected company knowledge | Versioned Reality Memory claims |
| Time model | Current navigation context | Relationships and recall | Freshness, validity windows, supersession, and conflict review |
| Safety decision | Not the primary boundary | Not the primary boundary | Deterministic SAG evaluates current approved memory plus live evidence |
| Agent connection | Tools can drive a workflow | Agents can consume knowledge | Authenticated MCP with scoped read/check/workflow/write permissions |
| Consequential action | Depends on the integrating agent | Depends on the integrating agent | Human owner confirmation; NexaFlow never deploys, posts, or mutates a provider |
| Intermittent connectivity | Not the primary product promise | Not the primary product promise | Optional read-only edge cache with explicit stale/unavailable state |

The differentiator is not another chatbot over company documents. NexaFlow
records why a claim was trusted, when it stopped being current, and what must
happen before an agent or release workflow proceeds.

## Storage and isolation

MongoDB stores organization-scoped skills, events, workflow runs, source
ingestions, source connections, Reality Memory, outcomes, API-key metadata,
audit records, and temporary judge sandboxes. Browser sessions map to opaque,
signed, expiring judge organizations. Sandbox evidence and memory use TTL and
cannot reinforce skills, enable auto-execution, alter canonical counts, or
cross session boundaries.

## Deployment shape

Docker Compose runs MongoDB, the FastAPI API, nginx, and a separate source
worker. nginx terminates TLS in the Alibaba ECS deployment and forwards the MCP
API-key header. Readiness reports build SHA and Qwen health. Attestation is
reported only when the running host verifies it; otherwise the service reports
the explicit audit fallback.
