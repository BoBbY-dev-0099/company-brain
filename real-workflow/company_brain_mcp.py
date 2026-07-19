"""Small authenticated Streamable HTTP MCP client for Company Brain."""

from __future__ import annotations

import json
from typing import Any

import httpx


class CompanyBrainMcpClient:
    """Use Company Brain as a governed workflow checkpoint over MCP."""

    def __init__(self, endpoint: str, api_key: str) -> None:
        self.endpoint = endpoint.rstrip("/") + "/"
        self.api_key = api_key
        self._request_id = 0
        self._client = httpx.Client(timeout=120.0)

    def close(self) -> None:
        self._client.close()

    def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        response = self._client.post(
            self.endpoint,
            headers={
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
                "X-Brain-Api-Key": self.api_key,
            },
            json={
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
                "params": params,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message", "MCP request failed"))
        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("MCP response did not include a result object")
        return result

    def initialize(self) -> dict[str, Any]:
        return self._call(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "company-brain-real-workflow", "version": "1.0.0"},
            },
        )

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._call("tools/list", {})
        tools = result.get("tools", [])
        if not isinstance(tools, list):
            raise RuntimeError("MCP tools/list response is invalid")
        return [tool for tool in tools if isinstance(tool, dict)]

    def evaluate_workflow(
        self,
        *,
        template_id: str,
        evidence: list[dict[str, Any]],
        live_context: dict[str, Any],
    ) -> dict[str, Any]:
        result = self._call(
            "tools/call",
            {
                "name": "evaluate_workflow",
                "arguments": {
                    "template_id": template_id,
                    "evidence": evidence,
                    "live_context": live_context,
                },
            },
        )
        if result.get("isError"):
            content = result.get("content", [])
            raise RuntimeError(str(content[0] if content else "evaluate_workflow failed"))
        content = result.get("content", [])
        if not isinstance(content, list) or not content or not isinstance(content[0], dict):
            raise RuntimeError("MCP evaluate_workflow response has no content")
        text = content[0].get("text")
        if not isinstance(text, str):
            raise RuntimeError("MCP evaluate_workflow result is not text JSON")
        decoded = json.loads(text)
        if not isinstance(decoded, dict):
            raise RuntimeError("MCP evaluate_workflow result is not an object")
        return decoded
