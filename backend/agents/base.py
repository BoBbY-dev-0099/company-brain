"""Shared MCP tool-loop agent base.

DashScope's compatible-mode endpoint exposes Chat Completions with
OpenAI-style function calling. We register the company-brain tools as
function tools and run a loop:

    chat.completions.create
    while response has tool_calls:
        for each tool_call: dispatch to backend.mcp.tools
        feed results back as role=tool messages
        chat.completions.create again
    return final assistant content

For the demo we dispatch in-process to avoid an SSE loopback. The MCP
server (server.py) exposes the same tools to external clients.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from backend.config import settings
from backend.mcp import tools as brain_tools

logger = logging.getLogger(__name__)


_MAX_ITERATIONS = 6


def _tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "recall_skills",
                "description": (
                    "Recall the most relevant active skills from the Company Brain "
                    "for a free-text context. Call this BEFORE planning to surface "
                    "what the brain has already learned about similar situations."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "context": {
                            "type": "string",
                            "description": "The situation or decision the agent is reasoning about.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Max skills to return.",
                            "default": 5,
                        },
                    },
                    "required": ["context"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "check_intercept",
                "description": (
                    "Pre-flight check: would this proposed decision be intercepted? "
                    "Use this before taking any non-trivial action — the brain may "
                    "block, warn, or auto-execute based on prior experience."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "decision_text": {
                            "type": "string",
                            "description": "Plain-text description of the action you are about to take.",
                        },
                        "domain": {
                            "type": "string",
                            "description": "Optional: scope the check to a domain (engineering, support, product).",
                        },
                    },
                    "required": ["agent_id", "decision_text"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "compile_experience",
                "description": (
                    "After resolving an experience, compile it into a durable skill "
                    "the brain can reuse. Call this ONCE per resolved ticket / merged "
                    "PR / closed product question."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "agent_id": {"type": "string"},
                        "event_type": {
                            "type": "string",
                            "description": "Examples: ticket_resolved, pr_reviewed, qa_resolved.",
                        },
                        "content": {"type": "string"},
                        "outcome": {"type": "string"},
                    },
                    "required": ["event_id", "agent_id", "event_type", "content"],
                },
            },
        },
    ]


_DISPATCH = {
    "recall_skills": brain_tools.recall_skills,
    "check_intercept": brain_tools.check_intercept,
    "compile_experience": brain_tools.compile_experience,
}


@dataclass
class AgentRunResult:
    response: str
    skills_used: list[str]
    iterations: int
    intercepted: bool
    intercept_skill: str | None


class MCPToolLoopAgent:
    """Subclass and override `system_prompt` and `agent_id` / `agent_type`."""

    agent_id: str = "agent-base"
    agent_type: str = "general"
    system_prompt: str = "You are a helpful agent."

    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def client(self) -> AsyncOpenAI:
        if not settings.QWEN_API_KEY:
            raise RuntimeError("QWEN_API_KEY missing — agent cannot run")
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.QWEN_API_KEY, base_url=settings.QWEN_BASE_URL)
        return self._client

    async def pre_messages(self, user_message: str) -> list[dict[str, Any]]:
        """Hook for subclasses to inject extra context (e.g. cross-session memory).

        Default: nothing extra.
        """
        return []

    async def run(self, user_message: str) -> AgentRunResult:
        client = self.client()

        messages: list[dict[str, Any]] = [{"role": "system", "content": self.system_prompt}]
        messages.extend(await self.pre_messages(user_message))
        messages.append({"role": "user", "content": user_message})

        skills_used: list[str] = []
        intercepted = False
        intercept_skill: str | None = None

        for iteration in range(1, _MAX_ITERATIONS + 1):
            resp = await client.chat.completions.create(
                model=settings.QWEN_AGENT_MODEL,
                messages=messages,
                tools=_tool_schemas(),
                tool_choice="auto",
                temperature=0.3,
                extra_body={"enable_thinking": False},
            )
            choice = resp.choices[0]
            msg = choice.message

            assistant_msg: dict[str, Any] = {
                "role": "assistant",
                "content": msg.content or "",
            }
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_msg)

            if not msg.tool_calls:
                return AgentRunResult(
                    response=msg.content or "",
                    skills_used=skills_used,
                    iterations=iteration,
                    intercepted=intercepted,
                    intercept_skill=intercept_skill,
                )

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    fn_args = {}

                handler = _DISPATCH.get(fn_name)
                if handler is None:
                    tool_result: Any = {"error": f"unknown tool {fn_name}"}
                else:
                    try:
                        tool_result = await handler(**fn_args)
                    except Exception as exc:  # noqa: BLE001
                        logger.exception("tool %s failed", fn_name)
                        tool_result = {"error": str(exc)}

                if fn_name == "recall_skills":
                    for s in tool_result.get("skills", []):
                        sid = s.get("skill_id")
                        if sid and sid not in skills_used:
                            skills_used.append(sid)
                elif fn_name == "check_intercept":
                    if tool_result.get("result") in ("block", "warn", "auto_execute"):
                        intercepted = True
                        intercept_skill = tool_result.get("matched_skill_id") or intercept_skill

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(tool_result, default=str),
                })

        return AgentRunResult(
            response=(messages[-1].get("content") or "(agent hit iteration cap)"),
            skills_used=skills_used,
            iterations=_MAX_ITERATIONS,
            intercepted=intercepted,
            intercept_skill=intercept_skill,
        )
