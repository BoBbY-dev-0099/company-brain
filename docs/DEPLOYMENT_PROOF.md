# Alibaba Cloud deployment proof

This page is the judge-facing evidence packet for the Qwen Cloud Global AI
Hackathon deployment requirement. The [official rules](https://qwencloud-hackathon.devpost.com/rules) require a link to a repository code file demonstrating Alibaba Cloud services/APIs; this repository's code evidence is [`backend/config.py`](../backend/config.py), [`deploy/deploy.sh`](../deploy/deploy.sh), and [`docker-compose.yml`](../docker-compose.yml). The screenshots below are supplemental proof requested for the judge packet. Complete them only after the checked-out commit is running on Alibaba Cloud ECS or SAS; local Docker is not proof of deployment.

## Evidence to capture

1. **Workbench Overview** — capture the Alibaba Cloud Workbench/instance view
   showing the running ECS or SAS instance. Keep the instance name, region,
   and running status visible; redact account IDs, public IPs, SSH keys, and
   API keys.
2. **Runtime proof** — from that instance, capture the following in one
   terminal/browser sequence:

   ```bash
   cd /opt/company-brain
   docker compose --profile full ps
   curl -s http://127.0.0.1/api/health
   curl -s http://127.0.0.1/api/demo/readiness
   ```

   The readiness response must show the deployed build SHA, `judge-demo-v1`,
   Qwen configuration status, and available canonical fixture counts/state.
3. **Public judge route** — capture the deployed Operations inbox in a fresh
   browser session, including one backend-derived decision brief. Do not
   include secrets, internal URLs, or a local-only address.

Place the redacted images in `docs/assets/` and link them below only after the
evidence has been captured on the deployed instance.

## Evidence manifest

| Artifact | Required state | Link |
| --- | --- | --- |
| Alibaba Workbench Overview | Pending capture on deployed ECS/SAS | Add after capture |
| Container + `/health` + `/demo/readiness` | Pending capture on deployed ECS/SAS | Add after capture |
| Public Operations inbox | Pending capture on deployed ECS/SAS | Add after capture |

## Reproduction

The deployment script is `deploy/deploy.sh`. It deploys the public repository
onto an Alibaba Cloud host with Docker Compose. The application itself calls
Qwen Cloud through the DashScope compatible-mode endpoint; see
`backend/config.py` and the compiler implementation for the runtime API
configuration.

This document deliberately does not claim that a deployment exists until all
three artifacts above are attached.
