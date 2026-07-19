# Real MCP workflow

This folder is a production-shaped client for Company Brain's authenticated
Streamable HTTP MCP endpoint. It does not call the REST workflow route.

The client makes these real JSON-RPC calls:

1. initialize
2. tools/list
3. tools/call with evaluate_workflow

## Judge sandbox walkthrough

1. Open https://brain.veriflowai.me/play/workflow.
2. Select Create temporary MCP connection.
3. Copy the displayed temporary BRAIN_MCP_URL and BRAIN_API_KEY.
4. Set the values in your terminal and run:

       cd real-workflow
       python -m pip install -r requirements.txt
       python run_release_workflow.py

5. The page polls the browser-private sandbox organization and shows the MCP
   execution log, returned memory, SAG verdict, and human owner.

The temporary key is scoped to mcp:read and mcp:workflow, expires with the
browser sandbox, and cannot access the canonical judge fixture.

## Connect a company workflow

Create an organization API key with mcp:workflow (and mcp:read if the workflow
also recalls memory), then configure the workflow runner:

    export BRAIN_MCP_URL=https://brain.veriflowai.me/mcp/
    export BRAIN_API_KEY=cb_live_...
    python run_release_workflow.py

Replace fixtures/release_event.json with one of the code-owned workflow
template contracts: release-safety, money-safety, or rollout-safety.
The Company Brain MCP server resolves organization identity from the API key;
never send an org_id in the tool arguments.

evaluate_workflow only returns an auditable DecisionBrief. It never deploys,
refunds, or changes a feature flag. A human confirmation remains outside MCP.
