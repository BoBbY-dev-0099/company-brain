"""Authenticated REST surface for the code-owned workflow contract."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from backend.config import settings
from backend.workflows.models import WorkflowOutcomeRequest, WorkflowRun, WorkflowRunRequest
from backend.workflows.service import WorkflowNotFoundError, WorkflowService, WorkflowTemplateNotFoundError
from backend.workflows.templates import DEMO_SCENARIO_VERSION


router = APIRouter(tags=["workflows"])
service = WorkflowService()


def _org(request: Request) -> str:
    return getattr(request.state, "org_id", None) or settings.DEMO_ORG_ID


def _require_agent(request: Request) -> None:
    if getattr(request.state, "auth_type", None) != "agent":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="X-Brain-Api-Key is required")


@router.get("/workflow-templates")
async def list_workflow_templates() -> dict:
    """Publish the one code-owned NexaFlow contract without a browser fixture."""
    return {
        "scenario_version": DEMO_SCENARIO_VERSION,
        "templates": [
            {
                **template.model_dump(mode="json"),
                "demo_fixture": {"title": "test-only", "description": "Not exposed by the NexaFlow console."},
            }
            for template in service.list_templates()
        ],
    }


@router.post("/workflow-runs", response_model=WorkflowRun, status_code=status.HTTP_201_CREATED)
async def create_workflow_run(request: Request, body: WorkflowRunRequest) -> WorkflowRun:
    _require_agent(request)
    if body.fixture:
        raise HTTPException(status_code=422, detail="Browser fixtures are not available in NexaFlow.")
    try:
        return await service.run_workflow(body, org_id=_org(request), execution_origin="authenticated_rest")
    except WorkflowTemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="workflow template not found") from exc


@router.get("/workflow-runs")
async def list_workflow_runs(request: Request, limit: int = 20) -> dict:
    _require_agent(request)
    runs = await service.list_runs(org_id=_org(request), limit=max(1, min(limit, 50)))
    return {"runs": [run.model_dump(mode="json") for run in runs]}


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRun)
async def get_workflow_run(request: Request, run_id: str) -> WorkflowRun:
    _require_agent(request)
    try:
        return await service.get_run(run_id, org_id=_org(request))
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail="workflow run not found") from exc


@router.post("/workflow-runs/{run_id}/outcome", response_model=WorkflowRun)
async def post_workflow_outcome(request: Request, run_id: str, body: WorkflowOutcomeRequest) -> WorkflowRun:
    _require_agent(request)
    try:
        return await service.record_outcome(run_id, body, org_id=_org(request))
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail="workflow run not found") from exc


@router.get("/workflow-sources")
async def list_workflow_sources(request: Request, template_id: str | None = None, limit: int = 50) -> dict:
    _require_agent(request)
    if template_id:
        try:
            service.get_template(template_id)
        except WorkflowTemplateNotFoundError as exc:
            raise HTTPException(status_code=404, detail="workflow template not found") from exc
    sources = await service.list_sources(org_id=_org(request), template_id=template_id, limit=limit)
    return {"sources": [source.model_dump(mode="json") for source in sources]}
