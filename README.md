# NexaFlow

**Submission writeup:** [HACKATHON_WRITEUP.md](HACKATHON_WRITEUP.md)

NexaFlow is a local-first operational memory system. A real Slack incident, a
read-only Alibaba Cloud OSS runbook, and a signed GitHub merged pull request become
source-backed Qwen Reality Memory before one governed decision is made:

> Suspend the fulfillment release when the merged worker-memory setting is
> below the approved runbook minimum, or a related incident remains open.

```mermaid
flowchart LR
  S["Slack #ops-incidents"] --> E["Immutable evidence ledger"]
  D["Alibaba Cloud OSS runbook"] --> E
  G["GitHub merged PR"] --> E
  E --> M["Qwen Reality Memory\nprovenance and supersession"]
  M --> R["Release safety check\ndeterministic SAG"]
  R --> H["Engineering owner\nhuman-required action"]
```

For the clean-room positioning against adjacent company-brain patterns, see
the [architecture comparison](docs/ARCHITECTURE.md#positioning-against-adjacent-company-brain-patterns).
The complete judge-facing flow is shown in the [NexaFlow Reality Layer architecture diagram](docs/nexaflow-reality-architecture.svg).

The root route is the **NexaFlow Live Operations Console**. It is intentionally
empty until the real test company sends evidence; it has no synthetic fallback,
no browser-provided organization ID, and no fake green verdict.

## What is shipped

- Signed Slack Events API intake, restricted to one configured workspace and
  `#ops-incidents`; NexaFlow never posts to Slack.
- Read-only Alibaba Cloud OSS sync restricted to one private bucket prefix;
  it supports Markdown, text files, and PDFs and never writes to OSS.
- Signed GitHub merged-PR intake for an explicit repository allowlist. It
  persists the raw event, Qwen-compiled skill, audit record, source record,
  and memory provenance before it is available to the release check.
- A source ledger and Qwen Reality Memory layer with freshness, raw-payload
  hash, ACL scope, Qwen status, and auditable supersession.
- One aggregate `POST /nexaflow/release-check` endpoint. The server—not the
  browser—selects the latest ready NexaFlow Slack, OSS, and GitHub evidence.
- Deterministic SAG. Missing, stale, unavailable, or unparsable evidence is
  `review_required`; it is never presented as a suspension or a safe release.
- Authenticated Streamable HTTP MCP for read/audit proof. MCP does not deploy,
  change GitHub or OSS, or post to Slack. Human confirmation remains outside
  MCP.
- Optional authenticated Qwen-VL evidence intake stores a typed observation and
  image digest only; unavailable vision is explicit and review-required.
- Optional edge profile serves a stale-aware, read-only cache for intermittent
  connectivity without local action execution.

This is a selected-workspace local rehearsal, not a connector marketplace,
self-service OAuth product, autonomous executor, or generic workflow builder.

## Local-first quick start

The local rehearsal remains the safest way to iterate. The verified public
deployment is now running on Alibaba ECS at
`https://brain.veriflowai.me/`; stop the instance when you are not recording
or rehearsing the judge demo to control cost.

```powershell
Copy-Item .env.example .env
# Set QWEN_API_KEY in .env. Do not commit .env.
docker compose --profile full up --build -d
curl http://localhost/api/health
```

For a fresh local rehearsal, the helper below creates the operator unlock and
encryption values without printing them, recreates the API and worker, and
refreshes nginx so the setup page is ready in one command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
```

Use this helper only locally. Production deployments must provide
`INTEGRATION_ADMIN_TOKEN` and `INTEGRATION_CONFIG_ENCRYPTION_KEY` through their
secret-management process.

Docker Compose creates a new `companybrain_nexaflow` database and separate
`nexaflow_mongodb_*` volumes. It does not remove or reuse the old demo volume.

Open `http://localhost/`. The console will show `setup required` until the
three real providers are configured. Open `http://localhost/setup` to unlock
operator configuration. The browser uses the unlock token only to send
settings over same-origin HTTPS; provider secrets are encrypted before
persistence and are never returned.

## Create the NexaFlow test company

Use new, dedicated resources so this rehearsal cannot affect a real company.

### 1. Start a temporary HTTPS callback URL

With the local stack running:

```powershell
ngrok http 80
```

Copy the `https://...ngrok-free.dev` forwarding URL to `PUBLIC_BASE_URL` in
`.env`, then restart API and worker:

```powershell
docker compose --profile full up -d --force-recreate api worker
```

Use the two exact callback URLs in provider setup:

- Slack: `https://<ngrok-host>/api/integrations/slack/events`
- GitHub: `https://<ngrok-host>/api/integrations/github/pr`

Keep ngrok running while testing. The URL is temporary; update
`PUBLIC_BASE_URL` whenever it changes.

### 2. Slack: `NexaFlow Logistics Demo`

1. Create a Slack workspace named **NexaFlow Logistics Demo** and public
   channel **#ops-incidents**.
2. Create a Slack app from scratch for this workspace.
3. In **OAuth & Permissions**, add the bot scope **`channels:history`**. This
   is the only message-history scope needed for Slack's `message.channels`
   event. Install the app to the workspace and copy its **Bot User OAuth
   Token** (`xoxb-...`) if you want the optional auth test in `/setup`.
4. In **Event Subscriptions**, enable events and set the request URL to the
   Slack callback above. Slack will send a signed URL verification request.
5. Under **Subscribe to bot events**, select only `message.channels`, then
   invite the app to **#ops-incidents**. The app must be a member of that
   public channel to receive its messages.
6. Copy the **Signing Secret** from **Basic Information**. To obtain the
   workspace/team ID, run this locally with the bot token (or read `team_id`
   from a received Slack event):

   ```powershell
   $headers = @{ Authorization = "Bearer xoxb-your-token" }
   Invoke-RestMethod -Method Post -Uri https://slack.com/api/auth.test -Headers $headers
   ```

   Copy the returned `team_id`. Copy the channel ID from the channel's Slack
   URL (`C...`) or its channel details, then paste `team_id`, `channel_ids`,
   `signing_secret`, and optional `bot_token` into `/setup` → Slack.
7. Click **Save**, then **Test connection**. A successful test means the
   server is ready for a signed event; the real message below is the ingestion
   proof.
8. Send the real test message:

   ```text
   SEV-2: fulfillment workers are OOM. Pause promotion for the release until the incident is resolved.
   ```

The signed event is persisted first and the worker then compiles Qwen memory.

### 3. Alibaba Cloud OSS: `nexaflow-operations-hk-2026`

1. In the Alibaba Cloud OSS console, create a private **Standard LRS** bucket
   in the same region as ECS, preferably **China (Hong Kong)** for this demo.
   Keep Block Public Access enabled and use a private ACL.
2. Create the prefix `runbooks/` and upload
   `runbooks/fulfillment-release-policy.md` from this repository.
3. In RAM, create a programmatic user such as `nexaflow-oss-reader`. Attach a
   custom policy that grants only `oss:ListObjects` for the `runbooks/` prefix
   and `oss:GetObject` for `runbooks/*`. Do not grant Put, Delete, or FullAccess.
4. Copy the OSS region, HTTPS endpoint, bucket name, and prefix into
   `/setup` → Alibaba OSS. Paste the RAM AccessKey values only into the
   operator form; they are encrypted server-side and never returned.
5. Run the read-only connection test, then click **Sync OSS now**. The source
   worker polls the same prefix in the background.

### 4. GitHub: `nexaflow-logistics-demo`

1. Create a dedicated **private** repository named
   `nexaflow-logistics-demo`.
2. Add a file such as `deploy/fulfillment.env` containing:

   ```bash
   NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=32
   ```

3. Create a fine-grained personal access token with an expiration date. Set
   **Repository access** to **Only select repositories** and select this repo.
   Grant only these repository permissions: **Contents: Read-only**,
   **Pull requests: Read-only**, and the default **Metadata: Read-only**.
4. In `/setup` → GitHub, save the exact `owner/nexaflow-logistics-demo`
   allowlist, a new webhook secret, and the read-only token. Run the read-only
   test.
5. In GitHub **Settings → Webhooks**, add the GitHub callback URL, choose JSON,
   use the same webhook secret, and subscribe only to **Pull requests**.
6. Create and merge a PR changing the setting from `32` to `8`:

   ```diff
   -NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=32
   +NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=8
   ```

GitHub validates the signature, fetches the merged diff with the read-only
token, persists/compiles/audits the intake, and mirrors it into the shared
source ledger.

## The one demo script

1. Confirm the console has a `decision_ready` event from Slack, OSS, and
   GitHub. `Qwen unavailable` is displayed honestly if no valid Qwen key is
   present.
2. Click **Run release safety check**.
3. NexaFlow parses `24 MiB` from OSS, `8 MiB` from the merged PR, and the
   open SEV-2 Slack message.
4. The result is **suspended**. It cites all three sources, the Reality Memory
   lineage, the deterministic SAG trace, the engineering release owner, and a
   human-required next action.
5. Expand **Audit proof** to show the exact server-derived records and parser
   output. No external action has occurred.
6. Click **Run Qwen case proof** to compile five ephemeral alternate realities:
   safe/resolved, open incident, missing policy, stale policy, and the memory
   regression. The Qwen model/status is shown beside each deterministic SAG
   verdict; these runs never change canonical memory.

To rehearse missing/stale paths safely, remove or let one required source age
out; the same endpoint returns `review_required` instead of inventing a
decision.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/nexaflow/overview` | Read-only console state for `nexaflow-demo`. |
| `POST` | `/nexaflow/release-check` | Aggregate Slack + OSS + GitHub release decision. |
| `POST` | `/nexaflow/case-matrix` | Five ephemeral Qwen + SAG regression cases for judge proof. |
| `POST` | `/integrations/slack/events` | Signed, allowlisted Slack ingress. |
| `POST` | `/integrations/github/pr` | Signed merged pull-request ingress. |
| `POST` | `/operator/integrations/alibaba_oss/sync-now` | Operator-authenticated, read-only Alibaba OSS sync. |
| `GET` | `/source-events` | Read-only normalized evidence ledger. |
| `GET` | `/reality-memory` | Active and superseded Qwen Reality Memory. |
| `POST` | `/mcp/` | Authenticated Streamable HTTP MCP transport. |

## Verify locally

```powershell
python -m pytest backend/tests/test_sources.py backend/tests/test_github_integration.py backend/tests/test_operator_integrations.py -q
cd frontend
npm.cmd run build
```

For the final local acceptance, also verify Slack and GitHub’s delivery logs,
OSS sync, Docker health, and the root console in a desktop and mobile browser.
No provider secret is committed or exposed in the browser.
