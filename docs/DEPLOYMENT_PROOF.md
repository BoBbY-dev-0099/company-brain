# NexaFlow Alibaba Cloud deployment proof

This is the judge-facing deployment packet for NexaFlow. Local Docker is
a useful validation gate, but it is not evidence of an Alibaba Cloud
deployment. Do not mark the artifacts below complete until the exact checked
out commit is running on ECS or SAS and the public HTTPS route has been tested.

Relevant implementation evidence:

- [`backend/config.py`](../backend/config.py) configures Qwen, public identity,
  and the authenticated MCP deployment flags.
- [`backend/routers/integration_catalog.py`](../backend/routers/integration_catalog.py)
  reports only configured connections, stable REST contracts, and previews.
- [`deploy/deploy.sh`](../deploy/deploy.sh) and
  [`deploy/docker-compose.tls.yml`](../deploy/docker-compose.tls.yml) provide
  the ECS Docker/TLS path.

## DNS and network prerequisites

Before certificate issuance, the DNS owner must create:

```text
A  brain.veriflowai.me  8.218.174.77
```

Open inbound TCP `80` and `443` in the ECS security group. Port 80 is used for
the ACME challenge and redirects to HTTPS after a certificate exists. The
first deploy keeps an HTTP bootstrap on the public IP so the application stays
reachable while DNS propagates; it must not be presented as the final judge
URL.

## Safe deployment sequence

On the ECS host:

```bash
cd /opt/company-brain
# Set QWEN_API_KEY in .env before serving real Qwen-backed flows.
sudo bash deploy/deploy.sh

# Verify the bootstrap before DNS/TLS issuance.
curl -fsS http://127.0.0.1/api/health
curl -fsS http://127.0.0.1/api/demo/readiness
```

After DNS and TLS are live, the repository includes a non-secret capture helper:

```bash
BASE_URL=https://brain.veriflowai.me bash deploy/capture-proof.sh
```

It stores health, readiness, integration-catalog, and HTTPS-header responses
under a timestamped `docs/assets/` directory. It does not call MCP or write
provider data; API-key and Workbench screenshots still require manual
redaction.

When the DNS A record resolves to the same ECS public IP, issue TLS:

```bash
ISSUE_TLS_CERTIFICATE=true LETSENCRYPT_EMAIL=you@example.com sudo bash deploy/deploy.sh

sudo cp deploy/companybrain-certbot-renew.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now companybrain-certbot-renew.timer
```

The issuance command creates the certificate in a persistent Docker volume,
restarts nginx into TLS mode, records `PUBLIC_BASE_URL`, and enables the
authenticated remote-MCP configuration only after issuance succeeds.

## Public verification

Run these from a machine outside the ECS host after issuance:

```bash
curl -fsSI https://brain.veriflowai.me/
curl -fsS https://brain.veriflowai.me/api/health
curl -fsS https://brain.veriflowai.me/api/demo/readiness
curl -fsS https://brain.veriflowai.me/api/integration-catalog
```

The readiness response must show the deployed build SHA, NexaFlow scenario
version, Qwen configuration status, and the source/decision counts for the
configured `nexaflow-demo` organization. The catalog should only report Slack,
Alibaba OSS, or GitHub as `connected` after the exact server-side configuration
for that adapter is complete; it reports verified web and the REST workflow
boundary separately and MCP only after authenticated HTTPS is enabled.

To exercise MCP, use a scoped `X-Brain-Api-Key` against the canonical endpoint
`https://brain.veriflowai.me/mcp/`. The public legacy `/mcp/sse` path should
return `410`; it is not a valid production connector.

## Verified public run

On 20 July 2026, the exact commit `746ccf4281345d43e8aedba9580857baa66d877f`
was deployed to the NexaFlow ECS host and verified from outside the host.

- Public health: `status=ok`, MongoDB connected to `companybrain_nexaflow`,
  Qwen configured, embeddings healthy.
- Public overview: 3 persisted source records, 3 Reality Memory records, and
  Slack, Alibaba OSS, and GitHub all `connected/healthy` for `nexaflow-demo`.
- Aggregate release check: `suspended`; runbook minimum `24 MiB`, merged
  configuration `8 MiB`, linked incident `open`, owner `NexaFlow engineering
  release owner`.
- Safety boundary: the response explicitly states that no deployment, Slack
  post, GitHub change, or OSS write was executed.
- Legacy transport: `GET /mcp/sse` returns `410`.
- Authenticated MCP: initialize, `tools/list`, `query_evidence`, and
  `check_intercept` were exercised with a temporary scoped key; all 8 tools
  were listed and the check returned `external_action_permitted=false`,
  `human_approval_required=true`, and `auto_execute=false`. The temporary key
  was revoked after the test.

The captured non-secret HTTP responses are versioned under
[`docs/assets/deployment-proof-20260720T101115Z`](assets/deployment-proof-20260720T101115Z/):

- [`health.json`](assets/deployment-proof-20260720T101115Z/health.json)
- [`readiness.json`](assets/deployment-proof-20260720T101115Z/readiness.json)
- [`integration-catalog.json`](assets/deployment-proof-20260720T101115Z/integration-catalog.json)
- [`https-headers.txt`](assets/deployment-proof-20260720T101115Z/https-headers.txt)

## Evidence to capture

1. **Workbench Overview:** Alibaba Cloud Workbench/instance view showing the
   running ECS or SAS instance. Keep instance name, region, and running status
   visible; redact account identifiers, IP addresses, SSH keys, and API keys.
2. **Runtime proof:** one sequence showing `docker compose ... ps`, the local
   readiness response, and its build SHA.
3. **Public judge route:** `https://brain.veriflowai.me/` in a fresh
   browser session, showing the Company Reality Console, one backend-derived
   incident-to-release trace, and its source/memory/SAG explanation.
4. **HTTPS/MCP proof:** a redacted `curl -I` or browser security view for the
   hostname plus the integration catalog response. Never show API keys.

Place redacted images in `docs/assets/` and link them below only after capture.

## Evidence manifest

| Artifact | Required state | Link |
| --- | --- | --- |
| Alibaba Workbench Overview | Pending manual redacted screenshot | Capture from the Alibaba console before submission |
| Container, health, readiness, and build SHA | Captured from deployed ECS | [health](assets/deployment-proof-20260720T101115Z/health.json) · [readiness](assets/deployment-proof-20260720T101115Z/readiness.json) |
| Public NexaFlow Console over HTTPS | Browser route verified; screenshot still requires manual capture | [live console](https://brain.veriflowai.me/) |
| HTTPS/MCP integration catalog proof | Captured; authenticated MCP smoke verified | [catalog](assets/deployment-proof-20260720T101115Z/integration-catalog.json) · [headers](assets/deployment-proof-20260720T101115Z/https-headers.txt) |

This document intentionally makes no claim that the DNS hostname, TLS
certificate, or public deployment is live until those artifacts are attached.
