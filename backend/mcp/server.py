"""MCP server façade.

FastMCP exposes the company-brain tools over SSE so external clients
(IDE plugins, third-party agents, judges' curl commands) can use them.
In-process agents skip the SSE loopback and call backend.mcp.tools directly.

Note: FastMCP 1.12 introspects parameter annotations via `issubclass(...)`,
which throws when annotations are strings (i.e. under
`from __future__ import annotations`). We deliberately do NOT use future
annotations in this module so type hints evaluate to real classes.
"""

import logging
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from backend.mcp import tools

logger = logging.getLogger(__name__)


mcp_server = FastMCP("company-brain")


@mcp_server.tool()
async def recall_skills(context: str, top_k: int = 5) -> dict:
    """Recall the most relevant active skills for a free-text context.

    Use this BEFORE planning an action to surface what the brain has already learned.
    """
    return await tools.recall_skills(context=context, top_k=top_k)


@mcp_server.tool()
async def check_intercept(
    agent_id: str,
    decision_text: str,
    domain: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict:
    """Pre-flight: ask the brain whether a decision should be blocked, warned, or auto-executed.

    Always call before taking a non-trivial action. Pass ``metadata`` with live
    system state (config values, deploy flags) so skill preconditions are checked.
    """
    return await tools.check_intercept(
        agent_id=agent_id,
        decision_text=decision_text,
        domain=domain,
        metadata=metadata,
    )


@mcp_server.tool()
async def compile_experience(
    event_id: str,
    agent_id: str,
    event_type: str,
    content: str,
    outcome: str = "",
) -> dict:
    """Compile a freshly resolved experience into a durable skill and propagate it
    to all agents in the org."""
    return await tools.compile_experience(
        event_id=event_id,
        agent_id=agent_id,
        event_type=event_type,
        content=content,
        outcome=outcome,
        metadata=None,
    )


# Silence unused-import warning while preserving the import for editor IDEs.
_ = Any
