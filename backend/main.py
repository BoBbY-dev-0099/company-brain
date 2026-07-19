"""FastAPI entry: lifespan + all routes + SSE stream + MCP mount."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from backend.brain import store
from backend.config import settings
from backend.core import compiler, interceptor, propagator
from backend.core.compiler import check_embedding_health
from backend.core.schema import (
    DecisionCheckRequest,
    DecisionCheckResponse,
    InterceptResult,
    RawEvent,
    SessionMemory,
    SSEEvent,
    SSEEventType,
)
from backend.demo import seed_data
from backend.demo.state import build_demo_readiness
from backend.mcp import tools as brain_tools
from backend.mcp.auth import (
    DEFAULT_MCP_API_KEY_PERMISSIONS,
    MCPApiKeyAuthMiddleware,
    validate_api_key_permissions,
)
from backend.mcp.server import mcp_server
from backend.middleware.auth import (
    auth_middleware,
    resolve_org_from_token,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_ttl_task: asyncio.Task[None] | None = None
_keepalive_task: asyncio.Task[None] | None = None

# FastMCP's Streamable HTTP app owns a session manager that must run inside
# the parent FastAPI lifespan; mounted sub-app lifespans are not started by
# Starlette automatically.  The middleware requires a scoped API key for every
# request before the FastMCP transport sees it.
mcp_http_app = MCPApiKeyAuthMiddleware(mcp_server.streamable_http_app())


class CreateApiKeyRequest(BaseModel):
    name: str
    permissions: Optional[str] = None


class LiveConfigUpdateRequest(BaseModel):
    export_chunk_size_mb: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None


class MockGithubWebhookRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class SeedDemoDataResponse(BaseModel):
    seeded: bool
    org_id: str
    skill_count: int = Field(default=0)
    reason: Optional[str] = None
    embeddings_backfilled: int = Field(default=0)


async def _ttl_sweeper() -> None:
    """Periodic background task: mark soft-expired skills inactive.

    MongoDB's TTL index handles hard deletion; this sweeper updates is_active
    for skills whose expires_at has passed but whose TTL deletion hasn't run yet
    (TTL background task wakes ~60s, so there's a small window).
    """
    while True:
        try:
            await asyncio.sleep(6 * 3600)
            db = store.get_db()
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            await db.skills.update_many(
                {"is_active": True, "provenance.expires_at": {"$lt": now}},
                {"$set": {"is_active": False, "provenance.invalidated": True, "updated_at": now}},
            )
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("TTL sweeper error: %s", exc)


async def _keepalive_loop() -> None:
    while True:
        try:
            await asyncio.sleep(15)
            if propagator.subscriber_count() > 0:
                await propagator.broadcast_keepalive()
        except asyncio.CancelledError:
            return
        except Exception as exc:  # noqa: BLE001
            logger.warning("keepalive error: %s", exc)


async def _backfill_org_embeddings(org_id: str) -> int:
    """Backfill Qwen embeddings for org skills missing vectors."""
    if not settings.QWEN_API_KEY:
        return 0
    try:
        filled = await store.backfill_embeddings_for_org(org_id=org_id)
        logger.info("Backfilled %d embeddings for org %s", filled, org_id)
        return filled
    except Exception as exc:  # noqa: BLE001
        logger.warning("Seed embedding backfill failed for org %s: %s", org_id, exc)
        return 0


@asynccontextmanager
async def _brain_lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _ttl_task, _keepalive_task

    await store.init_db()
    # Seed the clean demo org used by open UI (not the polluted local `default`).
    # Order inside seed_for_org / seed_demo_stage: Skill → Config=25 → Horror intercept.
    seeded = await seed_data.seed_for_org(settings.DEMO_ORG_ID)
    logger.info("Sandbox seed result: %s", seeded)
    if settings.JUDGE_DEMO_ORG_ID != settings.DEMO_ORG_ID:
        # Controlled, idempotent fixture bootstrap. Workflow fixtures are
        # regenerated from versioned code; public actions cannot write here.
        judge_seeded = await seed_data.seed_for_org(settings.JUDGE_DEMO_ORG_ID)
        logger.info("Canonical judge fixture seed result: %s", judge_seeded)
    try:
        filled = await _backfill_org_embeddings(settings.DEMO_ORG_ID)
        if filled:
            logger.info("Backfilled %d embeddings for demo org %s", filled, settings.DEMO_ORG_ID)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Demo org embedding backfill failed: %s", exc)
    if settings.JUDGE_DEMO_ORG_ID != settings.DEMO_ORG_ID:
        try:
            filled = await _backfill_org_embeddings(settings.JUDGE_DEMO_ORG_ID)
            if filled:
                logger.info(
                    "Backfilled %d embeddings for canonical judge org %s",
                    filled,
                    settings.JUDGE_DEMO_ORG_ID,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Canonical judge embedding backfill failed: %s", exc)

    embedding_status = await check_embedding_health()
    if not embedding_status["healthy"]:
        logger.warning(
            f"EMBEDDING DEGRADED: {embedding_status['error']}. "
            "Interceptor will use keyword-only scoring."
        )
        app.state.embedding_healthy = False
    else:
        logger.info(
            f"Embeddings healthy. Dimensions: {embedding_status['dimensions']}"
        )
        app.state.embedding_healthy = True

    import os

    from backend.services import rsa_audit, tdx_attestation

    if tdx_attestation.tdx_guest_present():
        logger.info("TDX_READY: Confidential VM active")
        app.state.tdx_ready = True
    else:
        logger.info("TDX_UNAVAILABLE: Running in standard mode, RSA fallback enabled")
        app.state.tdx_ready = False
    try:
        rsa_audit.ensure_keys()
        await store.upsert_public_audit_key(
            settings.DEMO_ORG_ID,
            rsa_audit.public_key_fingerprint(),
            rsa_audit.public_key_pem(),
        )
        logger.info("RSA audit keys ready (fingerprint=%s)", rsa_audit.public_key_fingerprint()[:16])
    except Exception as exc:  # noqa: BLE001
        logger.warning("RSA audit key init failed: %s", exc)

    _ttl_task = asyncio.create_task(_ttl_sweeper())
    _keepalive_task = asyncio.create_task(_keepalive_loop())

    try:
        yield
    finally:
        for t in (_ttl_task, _keepalive_task):
            if t and not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        await store.close()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Run the app and the stateless Streamable HTTP MCP manager together."""
    async with mcp_server.session_manager.run():
        async with _brain_lifespan(app):
            yield


app = FastAPI(
    title="Company Brain",
    description="Source-backed Reality Memory and governed MCP decisions (Qwen Cloud Hackathon 2026)",
    version="1.0.0",
    lifespan=lifespan,
)


def _cors_origins() -> list[str]:
    """Return an explicit browser-origin allowlist.

    The deployed UI is same-origin, so it only needs its configured public
    hostname. Local Vite origins remain available when no public hostname is
    configured. Other browser clients must be added deliberately via env.
    """
    configured = getattr(settings, "CORS_ALLOWED_ORIGINS", "")
    values = configured.replace(",", " ").split() if isinstance(configured, str) else []
    origins = {value.rstrip("/") for value in values if value.strip()}
    public = str(getattr(settings, "PUBLIC_BASE_URL", "")).strip().rstrip("/")
    if public.startswith(("https://", "http://")):
        origins.add(public)
    if not origins:
        origins.update({"http://localhost:5173", "http://127.0.0.1:5173"})
    return sorted(origins)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Brain-Api-Key"],
    allow_credentials=False,
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.middleware("http")(auth_middleware)

from backend.routers import attestation as attestation_router
from backend.routers import audit as audit_router
from backend.routers import benchmark as benchmark_router
from backend.routers import github_integration as github_router
from backend.routers import integration_catalog as integration_catalog_router
from backend.routers import sag as sag_router
from backend.routers import sources as sources_router
from backend.routers import workflows as workflows_router

app.include_router(attestation_router.router)
app.include_router(audit_router.router)
app.include_router(benchmark_router.router)
app.include_router(github_router.router)
app.include_router(integration_catalog_router.router)
app.include_router(sag_router.router)
app.include_router(sources_router.router)
app.include_router(workflows_router.router)

# Register this concrete endpoint before the /mcp sub-application. Starlette
# dispatches in registration order, so placing it after the mount makes the
# sub-application consume /mcp/attestation and respond 404.
@app.get("/mcp/attestation")
async def get_attestation(request: Request) -> dict[str, Any]:
    _get_org_id(request)
    from backend.services import tdx_attestation

    base = brain_tools.attestation()
    base["tdx_guest"] = tdx_attestation.tdx_guest_present()
    base["mode"] = "tdx" if getattr(request.app.state, "tdx_ready", False) else "rsa_fallback"
    base["attestation_verified"] = bool(getattr(request.app.state, "tdx_ready", False))
    if not base["attestation_verified"]:
        base["narrative"] = (
            "TDX guest device not present on this host. Decisions are integrity-protected "
            "with RSA-PSS-SHA256 audit signatures (fallback). Deploy on Alibaba g7t/g8i "
            "Confidential VM for hardware TDX quotes."
        )
    return base

# Canonical remote MCP endpoint.  FastMCP is configured with path "/", so the
# mount produces exactly /mcp/ rather than /mcp/mcp.
@app.api_route("/mcp", methods=["GET", "POST", "DELETE"], include_in_schema=False)
async def redirect_mcp_to_canonical_endpoint() -> RedirectResponse:
    return RedirectResponse(url="/mcp/", status_code=status.HTTP_308_PERMANENT_REDIRECT)


@app.api_route("/mcp/sse", methods=["GET", "POST", "DELETE"], include_in_schema=False)
async def retired_mcp_sse_endpoint() -> JSONResponse:
    """Explicit migration response for the unauthenticated legacy SSE path."""
    return JSONResponse(
        {
            "error": "MCP_SSE_RETIRED",
            "detail": "Legacy MCP SSE is disabled. Use authenticated Streamable HTTP at /mcp/.",
            "migration_endpoint": "/mcp/",
        },
        status_code=status.HTTP_410_GONE,
    )


app.mount("/mcp", mcp_http_app)


# ---------- helpers ----------

def _get_org_id(request: Request) -> str:
    return getattr(request.state, "org_id", None) or settings.DEMO_ORG_ID


# ---------- health ----------

@app.get("/health")
async def health() -> dict[str, Any]:
    db_status = await store.db_health()
    return {
        "status": "ok" if db_status["connected"] else "degraded",
        "version": "1.0.0",
        "build_sha": settings.BUILD_SHA,
        "skills_compiled": await store.get_skill_count(),
        "subscribers": propagator.subscriber_count(),
        "db": db_status,
        "qwen_configured": bool(settings.QWEN_API_KEY),
        "embedding_healthy": getattr(app.state, "embedding_healthy", None),
    }


@app.get("/demo/readiness")
async def demo_readiness() -> dict[str, Any]:
    """Return server-observed deployment facts for the judge route."""
    return await build_demo_readiness(
        qwen_configured=bool(settings.QWEN_API_KEY),
        embedding_healthy=getattr(app.state, "embedding_healthy", None),
        build_sha=settings.BUILD_SHA,
    )


# ---------- events / compilation ----------

@limiter.limit("20/minute")
async def _post_event_limited(request: Request, event: RawEvent, org_id: str) -> dict[str, Any]:
    if not settings.QWEN_API_KEY:
        raise HTTPException(status_code=503, detail="QWEN_API_KEY not configured")
    try:
        skill = await compiler.compile_event_to_skill(event)
    except Exception as exc:
        logger.exception("compile failed")
        raise HTTPException(status_code=500, detail=f"compile failed: {exc}") from exc

    saved = await store.save_skill(skill, org_id=org_id)
    await store.save_event(event, skill_compiled=saved.skill_id, org_id=org_id)
    await propagator.propagate_skill(saved, is_new=(saved.version == 1), org_id=org_id)
    return {
        "skill_id": saved.skill_id,
        "name": saved.name,
        "version": saved.version,
        "domain": saved.domain,
        "summary": saved.summary,
        "confidence": saved.provenance.confidence,
        "embedding_dimensions": len(saved.embedding) if saved.embedding else 0,
    }


@app.post("/events")
async def post_event(request: Request, event: RawEvent) -> dict[str, Any]:
    org_id = _get_org_id(request)
    if not event.content or not event.content.strip():
        raise HTTPException(status_code=422, detail="event content cannot be empty")
    return await _post_event_limited(request, event, org_id)


# ---------- decision check ----------

@app.post("/decisions/check", response_model=DecisionCheckResponse)
async def post_decision_check(request: Request, req: DecisionCheckRequest) -> DecisionCheckResponse:
    req.org_id = _get_org_id(request)
    resp = await interceptor.check_decision(req)
    if resp.matched_skill is not None and resp.result != InterceptResult.CLEAR:
        await propagator.broadcast_intercept(
            agent_id=req.agent_id,
            skill=resp.matched_skill,
            result=resp.result,
            confidence=resp.confidence,
            org_id=req.org_id,
        )
    return resp


# ---------- brain browsing ----------

@app.get("/brain/skills")
async def list_skills(request: Request, domain: str | None = None) -> dict[str, Any]:
    org_id = _get_org_id(request)
    skills = await store.get_all_active_skills(domain=domain, org_id=org_id)
    return {
        "count": len(skills),
        "skills": [s.model_dump(mode="json", exclude={"embedding"}) for s in skills],
    }


@app.get("/brain/skills/{skill_id}")
async def get_skill_route(request: Request, skill_id: str) -> dict[str, Any]:
    org_id = _get_org_id(request)
    skill = await store.get_skill(skill_id, org_id=org_id)
    if not skill:
        raise HTTPException(status_code=404, detail="skill not found")
    return skill.model_dump(mode="json", exclude={"embedding"})


@app.get("/brain/intercepts")
async def list_intercepts(request: Request, limit: int = 50) -> dict[str, Any]:
    org_id = _get_org_id(request)
    intercepts = await store.get_recent_intercepts(org_id=org_id, limit=limit)
    return {"count": len(intercepts), "intercepts": intercepts}


@app.get("/brain/events")
async def list_events(request: Request, limit: int = 50) -> dict[str, Any]:
    org_id = _get_org_id(request)
    events = await store.get_recent_events(org_id=org_id, limit=limit)
    return {"count": len(events), "events": events}


# ---------- sessions ----------

@app.post("/sessions", response_model=SessionMemory)
async def create_session(request: Request, session: SessionMemory) -> SessionMemory:
    org_id = _get_org_id(request)
    if not session.session_id:
        session.session_id = f"session-{uuid.uuid4().hex[:8]}"
    return await store.save_session(session, org_id=org_id)


@app.get("/sessions/by-id/{session_id}")
async def get_one_session(request: Request, session_id: str) -> dict[str, Any]:
    org_id = _get_org_id(request)
    s = await store.get_session(session_id, org_id=org_id)
    if not s:
        return {"session_id": session_id, "found": False}
    return {"found": True, **s.model_dump(mode="json")}


@app.get("/sessions/{user_id}")
async def list_user_sessions(request: Request, user_id: str) -> dict[str, Any]:
    org_id = _get_org_id(request)
    sessions = await store.get_sessions_for_user(user_id, org_id=org_id)
    return {
        "user_id": user_id,
        "count": len(sessions),
        "sessions": [s.model_dump(mode="json") for s in sessions],
    }


# ---------- SSE stream ----------

@app.get("/stream")
async def stream(request: Request, token: Optional[str] = None) -> EventSourceResponse:
    # Resolve org_id from API key query token, else open demo org.
    org_id = getattr(request.state, "org_id", None)
    if not org_id and token:
        org_id = await resolve_org_from_token(token)
    if not org_id:
        org_id = settings.DEMO_ORG_ID

    sub_id, queue = propagator.add_subscriber(org_id=org_id)

    async def event_generator() -> AsyncIterator[dict[str, Any]]:
        try:
            # Initial hello so the client knows we're connected.
            yield {
                "event": "hello",
                "data": json.dumps({
                    "subscriber_id": sub_id,
                    "skills_compiled": await store.get_skill_count(org_id=org_id),
                }),
            }
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=20.0)
                except asyncio.TimeoutError:
                    yield {"event": SSEEventType.KEEPALIVE.value, "data": "{}"}
                    continue

                yield {
                    "event": event.type.value,
                    "data": json.dumps(event.payload, default=str),
                }
        finally:
            propagator.remove_subscriber(sub_id)

    return EventSourceResponse(event_generator())


# ---------- settings / api keys ----------

@app.get("/settings/metrics")
async def get_metrics(request: Request) -> dict[str, Any]:
    org_id = _get_org_id(request)
    total_skills = await store.get_skill_count(org_id=org_id)
    active_skills = await store.get_skill_count(org_id=org_id, active_only=True)
    recent_events = await store.get_recent_events(org_id=org_id, limit=10)
    intercept_stats = await store.get_intercept_stats(org_id=org_id)
    last_event = recent_events[0] if recent_events else None
    return {
        "metrics": {
            "total_skills": total_skills,
            "active_skills": active_skills,
            "total_decisions": intercept_stats["total_intercepts"],
            "governance_hits": intercept_stats["governance_hits"],
            "est_llm_tokens_saved": intercept_stats["est_llm_tokens_saved"],
            "est_llm_tokens_saved_is_estimate": intercept_stats["est_llm_tokens_saved_is_estimate"],
            "est_llm_tokens_saved_assumption": intercept_stats["est_llm_tokens_saved_assumption"],
            "intercept_by_result": intercept_stats["by_result"],
            "decisions_today": len(recent_events),
            "avg_confidence": sum(r.get("confidence", 0) for r in recent_events) / max(len(recent_events), 1),
            "avg_intercept_time": None,
            "avg_intercept_time_availability": "not measured",
        },
        "last_event": last_event,
        "timestamp": store.utc_now().isoformat(),
    }


@app.post("/settings/api-keys")
async def create_api_key_route(request: Request, body: CreateApiKeyRequest) -> dict[str, Any]:
    org_id = _get_org_id(request)
    try:
        permissions = validate_api_key_permissions(
            body.permissions or DEFAULT_MCP_API_KEY_PERMISSIONS
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = await store.create_api_key(
        org_id=org_id,
        name=body.name,
        # New keys are safe MCP connector keys by default.  mcp:write remains
        # opt-in because it can compile durable organizational memory.
        permissions=permissions,
    )
    return result


@app.get("/settings/api-keys")
async def list_api_keys_route(request: Request) -> dict[str, Any]:
    org_id = _get_org_id(request)
    keys = await store.list_api_keys(org_id=org_id)
    return {"keys": keys}


@app.delete("/settings/api-keys/{key_id}")
async def revoke_api_key_route(request: Request, key_id: str) -> dict[str, Any]:
    org_id = _get_org_id(request)
    ok = await store.revoke_api_key(key_id, org_id=org_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"revoked": True}


async def _apply_live_config(
    org_id: str,
    metadata_patch: dict[str, Any],
    *,
    run_sag: bool = True,
) -> dict[str, Any]:
    """Persist live config, broadcast SSE, optionally run SAG check (never crash)."""
    config = await store.set_live_config(org_id, metadata_patch)
    await propagator.broadcast(
        SSEEvent(
            type=SSEEventType.CONFIG_UPDATED,
            payload={
                "org_id": org_id,
                "metadata": config.get("metadata"),
            },
        ),
        org_id=org_id,
    )

    sag: dict[str, Any] | None = None
    if run_sag:
        chunk = (config.get("metadata") or {}).get("export_chunk_size_mb")
        skill = await store.get_skill("data-export-large-file-timeout", org_id=org_id)
        if skill is None:
            sag = None
        else:
            try:
                check_req = DecisionCheckRequest(
                    agent_id="engineering-agent-1",
                    decision_text=(
                        "Increase data export chunk size to improve throughput "
                        "on large CSV exports"
                    ),
                    domain="engineering",
                    metadata={"export_chunk_size_mb": chunk} if chunk is not None else {},
                    org_id=org_id,
                )
                resp = await interceptor.check_decision(check_req)
                sag = {
                    "result": resp.result.value if resp.result else None,
                    "applicability_status": resp.applicability_status,
                    "skill_id": resp.matched_skill.skill_id if resp.matched_skill else None,
                    "reason": resp.rationale,
                    "suspension_reason": resp.suspension_reason,
                    "confidence": resp.confidence,
                }
                if resp.matched_skill is not None and resp.result != InterceptResult.CLEAR:
                    await propagator.broadcast_intercept(
                        agent_id=check_req.agent_id,
                        skill=resp.matched_skill,
                        result=resp.result,
                        confidence=resp.confidence,
                        org_id=org_id,
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("live-config SAG check failed (safe null): %s", exc)
                sag = None

    return {
        "org_id": org_id,
        "metadata": config.get("metadata"),
        "updated_at": config.get("updated_at"),
        "sag": sag,
    }


@app.get("/settings/live-config")
async def get_live_config_route(request: Request) -> dict[str, Any]:
    org_id = _get_org_id(request)
    config = await store.get_live_config(org_id)
    return {
        "org_id": org_id,
        "metadata": config.get("metadata"),
        "updated_at": config.get("updated_at"),
    }


@app.post("/settings/live-config")
async def post_live_config_route(
    request: Request, body: LiveConfigUpdateRequest
) -> dict[str, Any]:
    org_id = _get_org_id(request)
    patch: dict[str, Any] = dict(body.metadata or {})
    if body.export_chunk_size_mb is not None:
        patch["export_chunk_size_mb"] = body.export_chunk_size_mb
    if not patch:
        raise HTTPException(status_code=422, detail="Provide export_chunk_size_mb or metadata")
    return await _apply_live_config(org_id, patch, run_sag=True)


@app.post("/integrations/mock-webhook/github")
async def mock_github_webhook(
    request: Request, body: MockGithubWebhookRequest
) -> dict[str, Any]:
    """Stub: external system pushes live config (e.g. export chunk size)."""
    org_id = _get_org_id(request)
    cfg = body.config or {}
    if not cfg:
        raise HTTPException(status_code=422, detail="config object required")
    result = await _apply_live_config(org_id, cfg, run_sag=True)
    return {"ok": True, "source": "mock-webhook/github", **result}


@app.post("/settings/seed-demo-data", response_model=SeedDemoDataResponse)
async def seed_demo_data_route(request: Request) -> SeedDemoDataResponse:
    """Idempotent org-scoped demo seed for the current org (open demo or API key).

    Uses the same org_id resolution as every other endpoint. Reuses the full
    SAG-enabled demo seed and backfills embeddings so SAG/intercept works
    immediately on fresh orgs.
    """
    org_id = _get_org_id(request)
    existing = await store.get_skill_count(active_only=False, org_id=org_id)
    if existing > 0:
        backfilled = await _backfill_org_embeddings(org_id)
        return SeedDemoDataResponse(
            seeded=False,
            org_id=org_id,
            skill_count=existing,
            reason="already seeded",
            embeddings_backfilled=backfilled,
        )
    result = await store.seed_demo_data(org_id=org_id)
    backfilled = await _backfill_org_embeddings(org_id)
    return SeedDemoDataResponse(
        seeded=True,
        org_id=org_id,
        skill_count=result.get("skills_inserted", 0),
        embeddings_backfilled=backfilled,
    )


# ---------- root ----------

@app.get("/")
async def root() -> dict[str, Any]:
    return {
        "service": "Company Brain",
        "track": "MemoryAgent (Qwen Cloud Hackathon 2026)",
        "endpoints": [
            "/health", "/events", "/decisions/check",
            "/brain/skills", "/brain/skills/{skill_id}",
            "/brain/intercepts", "/brain/events",
            "/sessions/{user_id}", "/stream",
            "/mcp/", "/mcp/attestation",
            "/settings/api-keys", "/settings/metrics", "/settings/seed-demo-data",
            "/workflow-templates", "/workflow-runs/{run_id}", "/workflow-sources",
            "/source-connections", "/source-events", "/reality-memory", "/reality-overview",
            "/integrations/slack/events", "/integrations/google-drive/sync", "/integrations/web/fetch",
            "/demo/readiness",
        ],
    }
