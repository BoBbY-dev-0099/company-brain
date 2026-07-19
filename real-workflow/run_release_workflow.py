"""Run a release workflow through Company Brain's real MCP endpoint."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from company_brain_mcp import CompanyBrainMcpClient


ROOT = Path(__file__).resolve().parent
FIXTURE_PATH = ROOT / "fixtures" / "release_event.json"


def emit(stage: str, **fields: Any) -> None:
    print(json.dumps({"stage": stage, **fields}, sort_keys=True))


def require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"{name} is required; see real-workflow/.env.example")
    return value


def main() -> int:
    endpoint = require("BRAIN_MCP_URL")
    api_key = require("BRAIN_API_KEY")
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    client = CompanyBrainMcpClient(endpoint, api_key)
    try:
        initialized = client.initialize()
        server = initialized.get("serverInfo", {})
        emit("initialize", server=server)

        tools = client.list_tools()
        emit("tools_list", tools=[tool.get("name") for tool in tools])
        if not any(tool.get("name") == "evaluate_workflow" for tool in tools):
            raise RuntimeError("Company Brain did not expose evaluate_workflow")

        run = client.evaluate_workflow(
            template_id=str(fixture["template_id"]),
            evidence=list(fixture["evidence"]),
            live_context=dict(fixture["live_context"]),
        )
        brief = dict(run.get("decision_brief", {}))
        emit(
            "evaluate_workflow",
            run_id=run.get("run_id"),
            origin=run.get("execution_origin"),
            verdict=brief.get("verdict"),
            owner=brief.get("owner"),
            memory_count=len(brief.get("memory_refs", [])),
        )
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
