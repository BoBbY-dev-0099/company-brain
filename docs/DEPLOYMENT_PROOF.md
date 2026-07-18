# Alibaba Cloud deployment proof

This is the judge-facing deployment packet for Company Brain. Local Docker is
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
curl -fsSI https://brain.veriflowai.me/app/inbox
curl -fsS https://brain.veriflowai.me/api/health
curl -fsS https://brain.veriflowai.me/api/demo/readiness
curl -fsS https://brain.veriflowai.me/api/integration-catalog
```

The readiness response must show the deployed build SHA, `judge-demo-v1`, Qwen
configuration status, and canonical fixture counts. The catalog should only
report GitHub as `connected` after its webhook secret, token, and repository
allowlist are configured; it reports the REST workflow contract separately and
MCP as `preview` until authenticated HTTPS configuration is enabled.

To exercise MCP, use a scoped `X-Brain-Api-Key` against the canonical endpoint
`https://brain.veriflowai.me/mcp/`. The public legacy `/mcp/sse` path should
return `410`; it is not a valid production connector.

## Evidence to capture

1. **Workbench Overview:** Alibaba Cloud Workbench/instance view showing the
   running ECS or SAS instance. Keep instance name, region, and running status
   visible; redact account identifiers, IP addresses, SSH keys, and API keys.
2. **Runtime proof:** one sequence showing `docker compose ... ps`, the local
   readiness response, and its build SHA.
3. **Public judge route:** `https://brain.veriflowai.me/app/inbox` in a fresh
   browser session, showing one backend-derived Decision Queue item and its
   five-step explanation.
4. **HTTPS/MCP proof:** a redacted `curl -I` or browser security view for the
   hostname plus the integration catalog response. Never show API keys.

Place redacted images in `docs/assets/` and link them below only after capture.

## Evidence manifest

| Artifact | Required state | Link |
| --- | --- | --- |
| Alibaba Workbench Overview | Pending capture on deployed ECS/SAS | Add after capture |
| Container, health, readiness, and build SHA | Pending capture on deployed ECS/SAS | Add after capture |
| Public Decision Queue over HTTPS | Pending DNS, TLS, and browser rehearsal | Add after capture |
| HTTPS/MCP integration catalog proof | Pending authenticated endpoint check | Add after capture |

This document intentionally makes no claim that the DNS hostname, TLS
certificate, or public deployment is live until those artifacts are attached.
