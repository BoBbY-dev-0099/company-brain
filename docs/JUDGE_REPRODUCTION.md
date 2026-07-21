# NexaFlow Judge Reproduction

This document is the complete evidence-to-decision rehearsal for Company Brain. It starts with a clean local operator setup, connects the three NexaFlow source systems, delivers real events, and ends with the governed release decision.

The public route is:

~~~text
https://brain.veriflowai.me/
~~~

The public service runs on Alibaba Cloud ECS. To control hackathon credits, the ECS instance may be stopped outside a scheduled demonstration window. If the URL is unavailable, request a live activation window at aayushsigdel23@gmail.com with the subject NexaFlow live test.

## What the judge will verify

The same source-backed workflow is used in every environment:

~~~text
Slack incident + Alibaba OSS policy + GitHub merged PR
        -> normalized evidence ledger
        -> Qwen Reality Memory with provenance
        -> deterministic SAG release check
        -> named human owner and no external execution
~~~

Expected demo result:

- Alibaba OSS runbook minimum: 24 MiB
- merged GitHub worker memory: 8 MiB
- Slack incident: open SEV-2 OOM incident
- decision: suspended
- owner: NexaFlow engineering release owner
- execution: human confirmation required

No deployment, GitHub write, OSS write, or Slack post is performed by Company Brain.

## 1. Prerequisites

Install or prepare:

- Docker Desktop with Docker Compose
- Git and PowerShell
- an ngrok account and the ngrok client for local HTTPS callbacks
- a Qwen Cloud/DashScope API key for qwen-plus and text-embedding-v3
- the dedicated NexaFlow Slack workspace, Alibaba Cloud OSS bucket, and GitHub repository described below

Never commit .env, provider tokens, RAM secrets, or webhook secrets.

## 2. Local operator unlock and boot

Clone the repository and create the local environment file:

~~~powershell
git clone https://github.com/BoBbY-dev-0099/company-brain.git
Set-Location .\company-brain
Copy-Item .env.example .env
notepad .env
~~~

Set at least these values in .env:

~~~dotenv
QWEN_API_KEY=your_dashscope_key
QWEN_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_EMBEDDING_BASE_URL=https://dashscope-intl.aliyuncs.com/compatible-mode/v1
QWEN_COMPILER_MODEL=qwen-plus
QWEN_EMBEDDING_MODEL=text-embedding-v3
MONGODB_DB_NAME=companybrain_nexaflow
DEMO_ORG_ID=nexaflow-demo
SOURCE_ORG_ID=nexaflow-demo
~~~

Run the local helper:

~~~powershell
powershell -ExecutionPolicy Bypass -File scripts/start-local.ps1
docker compose ps
curl.exe http://localhost/api/health
curl.exe http://localhost/api/demo/readiness
~~~

scripts/start-local.ps1 generates and preserves these local-only values without printing them:

- INTEGRATION_ADMIN_TOKEN
- INTEGRATION_CONFIG_ENCRYPTION_KEY
- LOCAL_REHEARSAL=true

On localhost, LOCAL_REHEARSAL allows the setup page to operate without exposing an unlock token in the browser. On any non-local hostname, the operator must send the server-side token in the X-Integration-Admin-Token header. Provider secrets are encrypted before persistence and are never returned to browser clients.

Open:

~~~text
http://localhost/setup
~~~

If the page says setup is disabled, confirm the helper completed successfully, then restart the API and worker:

~~~powershell
docker compose --profile full up -d --force-recreate api worker nginx
~~~

## 3. Create local HTTPS callbacks

In a second PowerShell window, keep ngrok running:

~~~powershell
ngrok http 80
~~~

Copy the HTTPS forwarding URL, for example https://example.ngrok-free.dev, then set it as the local public base URL:

~~~powershell
$ngrokHost = "https://example.ngrok-free.dev"
$envLines = Get-Content .env
$envLines = $envLines -replace '^PUBLIC_BASE_URL=.*$', "PUBLIC_BASE_URL=$ngrokHost"
Set-Content -LiteralPath .env -Value $envLines
docker compose --profile full up -d --force-recreate api worker nginx
~~~

Use these exact callback URLs:

~~~text
Slack:  https://example.ngrok-free.dev/api/integrations/slack/events
GitHub: https://example.ngrok-free.dev/api/integrations/github/pr
~~~

Do not close ngrok or change its URL during the rehearsal. If the URL changes, update .env and both provider webhooks before sending new events.

## 4. Configure Slack

1. Create a dedicated workspace named NexaFlow Logistics Demo.
2. Create a Slack app from scratch in that workspace.
3. In OAuth & Permissions, add the bot scope channels:history, install the app, and invite the bot to the public #ops-incidents channel.
4. In Event Subscriptions, enable events and set the request URL to the ngrok Slack callback above. Slack must return a successful URL verification.
5. Subscribe only to the bot event message.channels.
6. Copy the app Signing Secret from Basic Information.
7. Find the workspace team ID and the #ops-incidents channel ID. The team ID can be checked with the optional bot token:

~~~powershell
$headers = @{ Authorization = "Bearer xoxb-your-token" }
Invoke-RestMethod -Method Post -Uri https://slack.com/api/auth.test -Headers $headers
~~~

8. In http://localhost/setup, select Slack and enter team_id, channel_ids, signing_secret, and the optional bot_token.
9. Click Save and verify, then Test boundary. A ready-for-signed-event result is valid even without a bot token; the signing secret authenticates the incoming event.
10. Send this exact message in #ops-incidents:

~~~text
SEV-2: fulfillment workers are OOM. Pause promotion for the release until the incident is resolved.
~~~

The signed event is persisted before acknowledgment. The worker then normalizes the message and asks Qwen to compile source-linked reality memory.

## 5. Configure Alibaba Cloud OSS

1. In Alibaba Cloud OSS, create a private Standard LRS bucket in the ECS region, preferably China (Hong Kong) for this rehearsal. Keep Block Public Access enabled and keep the ACL private.
2. Create the prefix runbooks/.
3. Upload this repository file as runbooks/fulfillment-release-policy.md.
4. The policy must state that fulfillment workers require at least 24 MiB and that an open linked incident blocks promotion.
5. Create a dedicated RAM user for read-only sync. Grant only object listing for the configured prefix and object reads for runbooks/*; do not grant Put, Delete, or FullAccess permissions.
6. In /setup, select Alibaba OSS and enter the region cn-hongkong, endpoint https://oss-cn-hongkong.aliyuncs.com, bucket name, prefix runbooks/, RAM AccessKey ID, and RAM AccessKey secret.
7. Click Save and verify, Test boundary, and then Sync OSS now.

The adapter lists and reads the allowlisted prefix only. It never uploads, overwrites, deletes, or publishes an OSS object.

## 6. Configure GitHub

Use the dedicated repository:

~~~text
BoBbY-dev-0099/nexaflow-logistics-demo
~~~

1. Ensure the baseline file contains:

~~~text
NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=32
~~~

2. Create a fine-grained GitHub token with an expiration date. Select Only select repositories and choose nexaflow-logistics-demo.
3. Grant only Contents: Read-only, Pull requests: Read-only, and Metadata: Read-only.
4. In /setup, select GitHub and enter the repository allowlist owner/nexaflow-logistics-demo, a new webhook secret, and the fine-grained read-only token.
5. In the repository, open Settings -> Webhooks -> Add webhook.
6. Set the payload URL to the ngrok GitHub callback, choose application/json, paste the exact same webhook secret, enable SSL, and subscribe only to Pull requests.
7. Click Save and verify and Test boundary in /setup.

### Create the merged release-change PR

Run this in PowerShell from a clean clone of the demo repository:

~~~powershell
git clone https://github.com/BoBbY-dev-0099/nexaflow-logistics-demo.git
Set-Location .\nexaflow-logistics-demo
git fetch origin
git switch main
git pull --ff-only origin main

$file = "deploy\fulfillment.env"
$baseline = (Get-Content -LiteralPath $file | Select-String '^NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=').Line.Trim()
if ($baseline -ne "NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=32") {
    throw "Expected the approved 32 MiB baseline before creating the test PR. Found: $baseline"
}

$branch = "judge/release-safety-8mb-$((Get-Date).ToString('yyyyMMddHHmmss'))"
git switch -c $branch
$text = Get-Content -LiteralPath $file -Raw
$text = $text -replace 'NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=32', 'NEXAFLOW_FULFILLMENT_WORKER_MEMORY_MB=8'
Set-Content -LiteralPath $file -Value $text -NoNewline

git diff -- deploy/fulfillment.env
git add deploy/fulfillment.env
git commit -m "Test release safety with reduced worker memory"
git push -u origin $branch
~~~

Open a pull request from the new branch into main, confirm the diff is 32 -> 8, and merge it. The signed pull_request delivery is accepted only for the allowlisted repository and only after the pull request is merged.

If main is already at 8, restore the approved 32 baseline first or use a known baseline commit. A second test PR must contain the actual 32 -> 8 regression; otherwise the release parser has no change to evaluate.

After merging, inspect the GitHub webhook Recent Deliveries. A successful delivery returns HTTP 2xx. A 503 normally means the local API, ECS instance, or ngrok tunnel is not running.

## 7. Run the complete decision

1. Open http://localhost/ locally, or https://brain.veriflowai.me/ during an active ECS window.
2. Click Refresh.
3. Confirm that the source cards show fresh Slack, Alibaba OSS, and GitHub evidence.
4. Confirm the evidence timeline shows source receipt and Qwen compilation.
5. Click Run release safety check.
6. Read the returned owner, blocker, Qwen interpretation, and deterministic SAG rule.
7. Expand Audit proof to inspect source excerpts, freshness, provenance, parsing, and the SAG trace.
8. Run Qwen case proof if available to exercise the five ephemeral cases: safe/resolved, open incident, missing policy, stale policy, and memory regression. These cases do not change canonical memory or provider counts.

The main run should return suspended because the merged worker setting is below the OSS runbook minimum and the linked Slack incident remains open. Missing, stale, unavailable, or unparsable source evidence must return review_required, never a fabricated safe or suspended result.

## 8. Local verification commands

~~~powershell
docker compose ps
curl.exe http://localhost/api/health
curl.exe http://localhost/api/demo/readiness

python -m pytest backend/tests/test_sources.py backend/tests/test_github_integration.py backend/tests/test_operator_integrations.py -q

Set-Location .\frontend
npm.cmd run build
~~~

The public route does not accept browser-supplied organization IDs, provider credentials, or source evidence. The server selects the NexaFlow organization and the newest ready records.

## 9. Troubleshooting

| Symptom | Check |
| --- | --- |
| Setup says operator unlock is disabled | Run scripts/start-local.ps1; confirm the API and worker were recreated. |
| Slack invalid_auth | The optional bot token is wrong or expired. Signed event delivery still works with the signing secret, team ID, and channel ID. |
| Slack receives no event | Confirm the app is invited to #ops-incidents, message.channels is subscribed, and ngrok is running. |
| OSS 403 or bucket ownership error | Verify the bucket account, region, endpoint, RAM user, private bucket name, and runbooks/ prefix. |
| GitHub webhook returns 503 | Start Docker/ECS and ngrok; then redeliver the event from GitHub Recent Deliveries. |
| GitHub evidence is missing | Confirm the event is a merged pull request, the secret matches, and the exact owner/repository is allowlisted. |
| Qwen is unavailable | Set a valid QWEN_API_KEY in the server .env and recreate API/worker. The UI must show the real unavailable state. |

## 10. Cleanup

When the rehearsal is complete:

~~~powershell
docker compose down
~~~

Stop ngrok, rotate the Slack signing secret, GitHub token, webhook secret, and Alibaba RAM keys, and remove the temporary Slack app or GitHub webhook if they are no longer needed. Never publish .env or provider credentials.

Supporting screenshots and the combined evidence pack are in [docs/assets/judge-proof](assets/judge-proof) and [nexaflow-evidence-pack.pdf](assets/judge-proof/nexaflow-evidence-pack.pdf).
