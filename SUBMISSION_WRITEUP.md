# Company Brain

## Keep agents from acting on outdated reality.

**Qwen Cloud Hackathon 2026 · MemoryAgent track**

Company Brain is a governed memory checkpoint for agent workflows. It receives
what changed in the systems a company already uses, asks Qwen to compile that
evidence into source-linked operational memory, and checks whether the next
consequential action is still safe. A named human owner confirms the outcome.

Company Brain does not replace a company’s agents or systems. It sits between
them and the action boundary.

---

## The problem

Operational truth is distributed across tools:

- an incident is reported in Slack;
- the approved requirement is documented in a runbook;
- a configuration change is merged in GitHub;
- an agent or release workflow sees only one part of that reality.

This makes stale memory dangerous. A workflow can apply a previously safe
decision even though a new incident is open, a policy has changed, or the
current configuration no longer satisfies the approved requirement.

This is not only a search problem. The system must answer:

1. What actually arrived?
2. Which claim did that evidence support?
3. Is the claim still current?
4. What does the current evidence allow?
5. Who is accountable for the next action?

---

## The solution

Company Brain makes the evidence-to-action path explicit:

~~~text
Slack · Alibaba OSS · GitHub
            ↓
Immutable normalized evidence
            ↓
Qwen Reality Memory
claims · rationale · provenance · freshness · supersession
            ↓
Deterministic SAG safety check
            ↓
Auditable DecisionBrief
            ↓
Named human owner and confirmation
~~~

The browser is deliberately untrusted. It cannot choose an organization,
submit provider credentials, inject evidence, or invent a verdict.

---

## The judge-ready NexaFlow scenario

The demo company is **NexaFlow Logistics**. Its fulfillment release is about
to be promoted.

### Three source records

1. Slack **#ops-incidents** receives:

   > SEV-2: fulfillment workers are OOM. Pause promotion for the release until
   > the incident is resolved.

2. A private Alibaba Cloud OSS runbook says:

   > Fulfillment workers require at least 24 MiB of memory before release
   > promotion.

3. A signed, merged GitHub pull request changes:

   ~~~diff
   -NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=32
   +NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=8
   ~~~

The operator opens the Company Brain console and selects **Run safety check**.
The server chooses the newest fresh records. The returned decision is:

~~~text
Verdict: suspended
Runbook minimum: 24 MiB
Merged configuration: 8 MiB
Slack incident: open
Owner: NexaFlow engineering release owner
Execution: human confirmation required
~~~

The recommendation is real, but Company Brain does not deploy, change GitHub,
write to OSS, post to Slack, or close the incident.

---

## What Qwen does

Qwen is a core part of the system, not decorative chat copy.

### Evidence-to-memory compilation

Each normalized source record is sent through the Qwen compiler. Qwen produces
a structured Reality Memory candidate containing:

- a subject, predicate, and operational claim;
- a concise rationale;
- linked source ingestion IDs;
- source and retrieval timestamps;
- freshness and availability state;
- scope, validity, and reconciliation metadata.

The UI exposes the actual Qwen status and generated rationale. If Qwen is
unavailable, the UI says so and never claims that memory was compiled.

### Temporal reconciliation

New evidence does not silently overwrite old knowledge. Conflicting or newer
claims can mark a previous memory as **superseded** or **review required**,
while the old record remains available for audit.

### Semantic recall

Qwen **text-embedding-v3** supports source-backed semantic retrieval. Retrieved
memory remains attributable to its evidence; it is not presented as an
unqualified answer.

### Multi-case proof

The **Run five-case proof** action sends five independent realities through the
same Qwen plus SAG engine:

| Case | Qwen result | Deterministic result |
|---|---|---|
| Memory regression + open incident | Compiled | Suspended |
| Safe configuration + resolved incident | Compiled | Proceed with human approval |
| Open incident + safe memory | Compiled | Suspended |
| Missing runbook | Compiled from available evidence | Review required |
| Stale runbook | Compiled with stale context visible | Review required |

These runs are ephemeral. They cannot change canonical memory, confidence,
reinforcement, provider records, or external systems.

---

## The deterministic safety gate

Qwen interprets evidence. The final safety result is deterministic and
replayable.

~~~text
configured_memory_meets_runbook == true
AND
linked_incident_open == false
~~~

The release is suspended when either independent condition fails. If evidence
is missing, stale, unavailable, unsigned, out of scope, or not safely
parseable, the result is **review required**; the system never converts
missing evidence into a safe verdict.

The DecisionBrief contains:

~~~text
facts
inference
missing evidence
source excerpts and freshness
prior memory
SAG trace
verdict
owner
recommended next action
~~~

---

## Architecture

~~~mermaid
flowchart LR
  S["Slack · Alibaba OSS · GitHub"] --> A["Source adapters"]
  A --> L["Immutable evidence ledger"]
  L --> Q["Qwen Reality Memory"]
  Q --> R["REST + authenticated Streamable HTTP MCP"]
  R --> G["Deterministic SAG"]
  G --> D["DecisionBrief"]
  D --> H["Named human owner"]
  H --> Q
  D -. "no external execution" .-> X["Company systems remain unchanged"]
~~~

### Evidence layer

- **Slack:** verifies the signing secret, replay window, team, and
  **#ops-incidents**; persists before acknowledgment; never posts.
- **Alibaba OSS:** reads one explicitly configured private bucket/prefix with
  least-privilege RAM credentials; never writes or deletes objects.
- **GitHub:** verifies the webhook signature, repository allowlist, merged PR
  state, and read-only diff fetch.

Every record carries source identity, external ID, URL, excerpt, raw-payload
hash, timestamps, freshness, availability, ACL scope, and ingestion stage.
Durable worker processing moves a record through:

~~~text
accepted → fetched → normalized → qwen_compiled → reconciled → decision_ready
~~~

### Memory and action layer

MongoDB stores the evidence ledger, Reality Memory lineage, workflow runs, and
audit records. FastAPI exposes the same DecisionBrief to the console, REST
clients, and authenticated MCP clients.

MCP is an agent connection, not an executor. Its scoped tools can recall,
inspect evidence and memory, compile an experience, or evaluate a workflow.
No MCP tool can deploy, refund, change a feature flag, modify GitHub/OSS, or
post to Slack.

---

## What the judge can try

### Live Operations Console

The root route shows backend-derived Slack, OSS, and GitHub tiles; the four-step
checkpoint; one primary safety action; the real verdict; persisted evidence;
Reality Memory lineage; and expandable audit proof.

The visible workflow is:

~~~text
Input → Qwen output → SAG output → human boundary
~~~

The Qwen card shows the returned model status and rationale. The SAG card
shows the plain-language deterministic rule before the raw trace.

### Integration Studio

The **/setup** route explains and configures the three read-only boundaries:

~~~text
Source event → Qwen memory → deterministic safety check → named human owner
~~~

Provider secrets are encrypted server-side and are never rendered back to the
browser.

### Qwen case proof

Click **Run five-case proof**. Five independent realities are compiled by
Qwen, evaluated by the same SAG rule, and displayed with the returned model
status, summary, source count, and verdict.

---

## Two-minute demo script

### 0:00–0:15 — State the problem

> The release workflow sees a merged code change, but operational truth is
> spread across Slack and the runbook. Company Brain checks the company memory
> before anyone acts.

### 0:15–0:35 — Show the evidence

Point to the three source cards: Slack’s open OOM incident, the 24 MiB OSS
policy minimum, and GitHub’s merged 8 MiB configuration.

### 0:35–1:00 — Run the real decision

Click **Run safety check**. Show **suspended**, the 24 MiB versus 8 MiB
mismatch, the open incident, the engineering owner, and human confirmation
required.

### 1:00–1:25 — Explain Qwen

Open the Qwen interpretation and Reality Memory cards. Explain that Qwen
converted the three source records into claims with provenance, while SAG
performed the final deterministic check.

### 1:25–1:45 — Prove generalization

Click **Run five-case proof**. Show that the same engine produces suspension,
human-approved continuation, and review-required outcomes for different
realities.

### 1:45–2:00 — Close on the boundary

> Company Brain does not replace a company’s agents. It is the governed memory
> checkpoint they call before consequential actions. It recommends; a human
> confirms; nothing external is executed by the demo.

---

## Verification evidence

The local acceptance gate includes signed Slack intake, replay protection,
idempotency, signed merged GitHub intake, read-only OSS sync, content hashing,
freshness handling, temporal supersession, source-org isolation, authenticated
MCP scopes, and no-external-action enforcement.

Recorded verification:

- backend tests: **95 passed, 5 skipped** without Mongo integration;
- Mongo integration smoke tests: **5 passed**;
- five ephemeral Qwen case compilations;
- production frontend build: passed;
- clean Docker API, worker, MongoDB, and nginx boot;
- browser verification of **/** and **/setup**;
- real release-check flow returning **suspended** with 24 MiB, 8 MiB, and an
  open incident.

The latest local UI commit is **a0573466**. The public ECS deployment requires
redeploying that commit before the final cloud screenshot and video; the last
SSH deployment attempt was unavailable.

---

## Honest scope

Company Brain is production-shaped for the hackathon, but it does not claim a
generic connector marketplace, self-service OAuth onboarding for every
company, broad enterprise RBAC, arbitrary no-code workflows, autonomous
deployment/refunds/feature-flag changes/Slack posting, guaranteed Qwen
availability, or guaranteed competition placement.

The next product layer is per-company OAuth onboarding, expanded source
adapters, and carefully approved external action adapters. Human approval and
the no-external-action boundary remain mandatory until those controls are
independently governed.

---

## Links

- Repository: <https://github.com/BoBbY-dev-0099/company-brain>
- Judge route: <https://brain.veriflowai.me/>
- Local setup route: <http://localhost/setup>
- Architecture: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- Deployment proof: [docs/DEPLOYMENT_PROOF.md](docs/DEPLOYMENT_PROOF.md)
- Setup guide: [CONNECT.md](CONNECT.md)
- Release policy: [real-workflow/runbooks/fulfillment-release-policy.md](real-workflow/runbooks/fulfillment-release-policy.md)
