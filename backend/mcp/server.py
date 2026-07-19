"""Authenticated Streamable HTTP MCP facade.

The FastMCP transport is deliberately stateless.  The ASGI authentication
middleware validates ``X-Brain-Api-Key`` for every HTTP request and the tool
wrappers below enforce a narrow scope while deriving the organization from the
server-resolved request principal.

Do not add human outcome recording or external-action tools here: Company
Brain's MCP surface produces governed decision briefs only.
"""

import logging
from typing import Any, Optional
from urllib.parse import urlsplit

from mcp.server.fastmcp import Context, FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError

from backend.config import settings
from backend.demo.judge_session import is_judge_sandbox_org
from backend.demo.state import assert_demo_org_mutable
from backend.mcp import tools
from backend.mcp.auth import (
    MCP_CHECK_SCOPE,
    MCP_READ_SCOPE,
    MCP_WORKFLOW_SCOPE,
    MCP_WRITE_SCOPE,
    MCPPrincipal,
    require_mcp_scope,
)
from backend.workflows.models import WorkflowRunRequest
from backend.workflows.service import WorkflowService, WorkflowTemplateNotFoundError


logger = logging.getLogger(__name__)
workflow_service = WorkflowService()


def _require_mutable_org(principal: MCPPrincipal) -> None:
    """Keep the canonical judge fixture free of MCP-triggered writes."""
    try:
        assert_demo_org_mutable(principal.org_id)
    except ValueError as exc:
        from mcp.server.fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


def _split_configured_values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.replace(",", " ").split() if item.strip()]
    if isinstance(value, (list, tuple, set, frozenset)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _default_transport_security() -> TransportSecuritySettings:
    """Build an explicit DNS-rebinding/origin policy for the public MCP host."""
    public_base_url = str(getattr(settings, "PUBLIC_BASE_URL", "") or "")
    parsed = urlsplit(public_base_url)
    hosts = _split_configured_values(getattr(settings, "MCP_ALLOWED_HOSTS", ""))
    if parsed.netloc:
        hosts.extend([parsed.netloc, f"{parsed.hostname}:*"] if parsed.hostname else [parsed.netloc])
    if not hosts:
        # Safe local fallback for a fresh clone. Production must provide
        # PUBLIC_BASE_URL or MCP_ALLOWED_HOSTS before its public hostname works.
        hosts = ["localhost:*", "127.0.0.1:*", "[::1]:*"]
    origins = _split_configured_values(getattr(settings, "MCP_ALLOWED_ORIGINS", ""))
    if not origins and parsed.scheme and parsed.netloc:
        origins = [f"{parsed.scheme}://{parsed.netloc}"]
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(dict.fromkeys(hosts)),
        allowed_origins=list(dict.fromkeys(origins)),
    )


def create_mcp_server(
    *,
    transport_security: TransportSecuritySettings | None = None,
) -> FastMCP:
    """Build a fresh server instance (also useful for isolated transport tests)."""
    server = FastMCP(
        "company-brain",
        # The parent FastAPI app mounts this at /mcp, producing canonical /mcp/.
        streamable_http_path="/",
        stateless_http=True,
        # A JSON response is valid Streamable HTTP and avoids a needless
        # long-lived SSE response for a single decision request.
        json_response=True,
        transport_security=transport_security or _default_transport_security(),
    )

    @server.tool()
    async def recall_skills(context: str, top_k: int = 5, ctx: Context = None) -> dict:
        """Recall active company memory before an agent plans an action."""
        principal = require_mcp_scope(ctx, MCP_READ_SCOPE)
        return await tools.recall_skills(
            context=context,
            top_k=top_k,
            org_id=principal.org_id,
        )

    @server.tool()
    async def check_intercept(
        agent_id: str,
        decision_text: str,
        domain: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        ctx: Context = None,
    ) -> dict:
        """Evaluate a proposed action against governed memory and live context.

        This tool never executes the proposed action.  Its response explicitly
        requires a human confirmation outside MCP before a company action.
        """
        principal = require_mcp_scope(ctx, MCP_CHECK_SCOPE)
        # Intercept evaluation can log/suspend/re-activate memory, so it is not
        # permitted against the immutable canonical judge fixture.
        _require_mutable_org(principal)
        result = await tools.check_intercept(
            agent_id=agent_id,
            decision_text=decision_text,
            domain=domain,
            metadata=metadata,
            org_id=principal.org_id,
        )
        # The legacy brain primitive may classify a memory as auto-executable.
        # The remote MCP contract never grants execution authority.
        result["auto_execute"] = False
        result["human_approval_required"] = True
        result["external_action_permitted"] = False
        return result

    @server.tool()
    async def evaluate_workflow(
        template_id: str,
        evidence: list[dict[str, Any]],
        live_context: dict[str, Any],
        ctx: Context = None,
    ) -> dict:
        """Return the auditable DecisionBrief for normalized evidence and live context.

        The server selects the organization from the API key, runs the same
        workflow engine as the REST API, and persists no human outcome.
        """
        principal = require_mcp_scope(ctx, MCP_WORKFLOW_SCOPE)
        _require_mutable_org(principal)
        try:
            request = WorkflowRunRequest(
                template_id=template_id,
                evidence=evidence or [],
                live_context=live_context or {},
            )
        except ValidationError as exc:
            from mcp.server.fastmcp.exceptions import ToolError

            raise ToolError(f"Invalid workflow input: {exc.errors(include_url=False)}") from exc
        try:
            run = await workflow_service.run_workflow(
                request,
                org_id=principal.org_id,
                is_judge_sandbox=is_judge_sandbox_org(principal.org_id),
                execution_origin="mcp",
            )
        except WorkflowTemplateNotFoundError as exc:
            from mcp.server.fastmcp.exceptions import ToolError

            raise ToolError("workflow template not found") from exc
        return run.model_dump(mode="json")

    @server.tool()
    async def compile_experience(
        event_id: str,
        agent_id: str,
        event_type: str,
        content: str,
        outcome: str = "",
        ctx: Context = None,
    ) -> dict:
        """Compile a resolved experience into governed memory for this organization.

        This writes memory only.  It does not record a human outcome and cannot
        execute any external company action.
        """
        principal = require_mcp_scope(ctx, MCP_WRITE_SCOPE)
        _require_mutable_org(principal)
        return await tools.compile_experience(
            event_id=event_id,
            agent_id=agent_id,
            event_type=event_type,
            content=content,
            outcome=outcome,
            metadata=None,
            org_id=principal.org_id,
        )

    return server


mcp_server = create_mcp_server()


# Silence unused-import warning while preserving the import for editor IDEs.
_ = Any
