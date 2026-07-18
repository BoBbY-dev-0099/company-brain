"""Stable HTTP endpoints for the generalized operational workflow engine."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from backend.config import settings
from backend.demo.state import assert_demo_org_mutable
from backend.workflows.models import (
    WorkflowOutcomeRequest,
    WorkflowRun,
    WorkflowRunRequest,
)
from backend.workflows.service import (
    WorkflowNotFoundError,
    WorkflowService,
    WorkflowTemplateNotFoundError,
)
from backend.workflows.templates import DEMO_SCENARIO_VERSION


router = APIRouter(tags=["workflows"])
service = WorkflowService()


def _org(request: Request) -> str:
    return getattr(request.state, "org_id", None) or settings.DEMO_ORG_ID


@router.get("/workflow-templates")
async def list_workflow_templates() -> dict:
    templates = service.list_templates()
    previews = {
        template.template_id: await service.preview_fixture(template.template_id)
        for template in templates
    }
    return {
        "scenario_version": DEMO_SCENARIO_VERSION,
        "templates": [
            {
                **template.model_dump(mode="json"),
                "demo_preview": previews[template.template_id].model_dump(mode="json"),
            }
            for template in templates
        ],
    }


@router.post("/workflow-runs", response_model=WorkflowRun, status_code=status.HTTP_201_CREATED)
async def create_workflow_run(request: Request, body: WorkflowRunRequest) -> WorkflowRun:
    org_id = _org(request)
    try:
        # The versioned judge fixture is read-only.  The open UI maps to the
        # sandbox org, where fixtures can be replayed without changing the
        # canonical source data or confidence history.
        assert_demo_org_mutable(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        return await service.run_workflow(body, org_id=org_id)
    except WorkflowTemplateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="workflow template not found") from exc


@router.get("/workflow-runs/{run_id}", response_model=WorkflowRun)
async def get_workflow_run(request: Request, run_id: str) -> WorkflowRun:
    try:
        return await service.get_run(run_id, org_id=_org(request))
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail="workflow run not found") from exc


@router.post("/workflow-runs/{run_id}/outcome", response_model=WorkflowRun)
async def post_workflow_outcome(
    request: Request,
    run_id: str,
    body: WorkflowOutcomeRequest,
) -> WorkflowRun:
    org_id = _org(request)
    try:
        assert_demo_org_mutable(org_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        return await service.record_outcome(run_id, body, org_id=org_id)
    except WorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail="workflow run not found") from exc


@router.get("/workflow-sources")
async def list_workflow_sources(
    request: Request,
    template_id: str | None = None,
    limit: int = 50,
) -> dict:
    if template_id:
        try:
            service.get_template(template_id)
        except WorkflowTemplateNotFoundError as exc:
            raise HTTPException(status_code=404, detail="workflow template not found") from exc
    sources = await service.list_sources(
        org_id=_org(request),
        template_id=template_id,
        limit=limit,
    )
    return {"sources": [source.model_dump(mode="json") for source in sources]}
