# Integrations — production-shaped connectors

These clients act like **external systems** calling Company Brain. They do not
embed Stripe/GitHub/Zendesk SDKs; they map realistic payloads into the brain’s
existing REST contracts (`POST /decisions/check`, `POST /events`, agent runs).

## Auth

Always use:

```
X-Brain-Api-Key: cb_live_...
```

Do **not** send `Authorization: Bearer cb_live_...` (returns 401).

Bootstrap a clean org (`integrations-demo`) with seed + embeddings + API key:

```bash
python integrations/python-client/bootstrap_api_key.py
# prints BRAIN_API_KEY=cb_live_...
```

## Run all workflows

```bash
export BRAIN_BASE_URL=http://127.0.0.1:8000
export BRAIN_API_KEY=cb_live_...
python integrations/python-client/connect_to_brain.py
```

| Workflow | Adapter | Metadata / action |
|----------|---------|-------------------|
| W1 Engineering | `example-systems/github_pr_export.py` | `export_chunk_size_mb` 25 vs 8 |
| W2 Support | `example-systems/billing_refund.py` | `days_since_purchase` 20 vs 60 |
| W3 Product | `example-systems/feature_flag_rollout.py` | `feature_flag_rollout_percent` 3 vs 40 |
| W4 Support learn | `example-systems/zendesk_resolve.py` | `POST /events` compile |
| W5 Product memory | `example-systems/product_session.py` | cross-session agent runs |

Exit code is non-zero if any SAG/result expectation fails (W1–W3).
W4–W5 need `QWEN_API_KEY` on the server; they are skipped cleanly if compile/agent is unavailable.
