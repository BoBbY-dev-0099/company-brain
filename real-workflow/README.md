# NexaFlow MCP proof client

This folder contains a small authenticated Streamable HTTP MCP client for
auditing Company Brain/NexaFlow. It does not execute deployments or change any
provider. The NexaFlow browser console itself uses `POST /nexaflow/release-check`
because that endpoint selects the latest real Slack, Alibaba OSS, and GitHub evidence
server-side.

After local setup, create an organization API key with `mcp:read` and
`mcp:workflow`, then configure:

```powershell
$env:BRAIN_MCP_URL = "http://localhost:8000/mcp/"
$env:BRAIN_API_KEY = "cb_live_..."
python -m pip install -r requirements.txt
python run_release_workflow.py
```

The MCP client may call `recall_skills`, `inspect_memory`, `query_evidence`,
`check_intercept`, and `evaluate_workflow` within its scoped key permissions.
It has no tool for release execution, Slack posting, or GitHub/OSS writes.

For the live NexaFlow decision, use the root console after the three source
records are `decision_ready`; do not replace its aggregate evidence selection
with a browser or client-supplied organization ID.
