# Integration adapters and examples

These scripts are reference adapters that show how an existing company system
can shape a payload for Company Brain's REST contracts. They are not installed
connectors and they do not use live Stripe, Zendesk, feature-flag, or GitHub
SDKs.

The product's truthful connection boundary is documented in
[`../CONNECT.md`](../CONNECT.md): the signed GitHub merged-PR webhook is the
only source connector that can become `connected` in this submission. The
other scripts are deterministic examples or fixture-shaped adapters.

## Authentication

REST clients use an organization-scoped API key:

```text
X-Brain-Api-Key: cb_live_...
```

Do not send `Authorization: Bearer cb_live_...`; API-key authentication uses
the explicit header above.

Bootstrap a local key for an isolated example organization:

```bash
python integrations/python-client/bootstrap_api_key.py
```

## Run the examples

```bash
export BRAIN_BASE_URL=http://127.0.0.1:8000
export BRAIN_API_KEY=cb_live_...
python integrations/python-client/connect_to_brain.py
```

| Example | Script | Honest status | Contract exercised |
| --- | --- | --- | --- |
| Engineering export | `example-systems/github_pr_export.py` | adapter example | `POST /decisions/check` |
| Billing refund | `example-systems/billing_refund.py` | fixture-shaped adapter | `POST /decisions/check` |
| Feature-flag rollout | `example-systems/feature_flag_rollout.py` | fixture-shaped adapter | `POST /decisions/check` |
| Support resolution | `example-systems/zendesk_resolve.py` | fixture-shaped adapter | `POST /events` |
| Product session | `example-systems/product_session.py` | fixture-shaped adapter | agent/session API |

The command exits non-zero when an expected deterministic safety result is not
returned. Qwen-backed compile/agent examples require `QWEN_API_KEY`; they may
be skipped cleanly when it is unavailable.

For the generalized workflow contract used by the judge inbox, use
`POST /workflow-runs` with normalized evidence and live context. The API
catalog provides a fresh copy-paste request at `GET /integration-catalog`.
