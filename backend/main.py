"""FastAPI entry: lifespan + all routes + SSE stream + MCP mount."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sse_starlette.sse import EventSourceResponse

from backend.agents import engineering_agent, product_agent, support_agent
from backend.brain import store
from backend.config import settings
from backend.core import compiler, interceptor, propagator
from backend.core.compiler import check_embedding_health
from backend.core.schema import (
    AgentRunRequest,
    AgentRunResponse,
    DecisionCheckRequest,
    DecisionCheckResponse,
    InterceptResult,
    RawEvent,
    SessionMemory,
    SSEEventType,
)
from pydantic import BaseModel
from backend.demo import seed_data
from backend.mcp import tools as brain_tools
from backend.mcp.server import mcp_server
from backend.middleware.clerk_auth import (
    auth_middleware,
    resolve_org_from_token,
    _verify_clerk_jwt,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_ttl_task: asyncio.Task[None] | None = None
_keepalive_task: asyncio.Task[None] | None = None


class CreateApiKeyRequest(BaseModel):
    name: str
    permissions: Optional[str] = None


class SeedDemoDataResponse(BaseModel):
    seeded: bool
    org_id: str
    skill_count: int = Field(default=0)
    reason: Optional[str] = None


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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _ttl_task, _keepalive_task

    await store.init_db()
    seeded = await seed_data.seed_if_empty()
    logger.info("Seed result: %s", seeded)

    if settings.QWEN_API_KEY and seeded.get("skills_inserted", 0) > 0:
        try:
            filled = await compiler.backfill_seed_embeddings(org_id=seeded.get("org_id", "default"))
            logger.info("Backfilled %d seed embeddings", filled)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Seed embedding backfill failed: %s", exc)

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


app = FastAPI(
    title="Company Brain",
    description="MemoryAgent — Operating Memory Primitive (Qwen Cloud Hackathon 2026)",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.middleware("http")(auth_middleware)

# Mount the FastMCP server. FastMCP exposes /sse and /messages relative to the
# mount point; mounting at /mcp gives /mcp/sse externally (matches MCP_SERVER_URL).
app.mount("/mcp", mcp_server.sse_app())


# ---------- helpers ----------

def _get_org_id(request: Request) -> str:
    return getattr(request.state, "org_id", "default") or "default"


# ---------- health ----------

@app.get("/health")
async def health() -> dict[str, Any]:
    db_status = await store.db_health()
    return {
        "status": "ok" if db_status["connected"] else "degraded",
        "version": "1.0.0",
        "skills_compiled": await store.get_skill_count(),
        "subscribers": propagator.subscriber_count(),
        "db": db_status,
        "qwen_configured": bool(settings.QWEN_API_KEY),
        "embedding_healthy": getattr(app.state, "embedding_healthy", None),
    }


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


# ---------- agents ----------

@app.post("/agents/support/run", response_model=AgentRunResponse)
async def run_support(request: Request, req: AgentRunRequest) -> AgentRunResponse:
    _get_org_id(request)
    if not settings.QWEN_API_KEY:
        raise HTTPException(status_code=503, detail="QWEN_API_KEY not configured")
    result = await support_agent.run(req.user_message, metadata=req.metadata)
    return AgentRunResponse(
        agent_id=support_agent.get_agent().agent_id,
        response=result.response,
        skills_used=result.skills_used,
        intercepted=result.intercepted,
        intercept_skill=result.intercept_skill,
        iterations=result.iterations,
        session_id=req.session_id,
    )


@app.post("/agents/engineering/run", response_model=AgentRunResponse)
async def run_engineering(request: Request, req: AgentRunRequest) -> AgentRunResponse:
    _get_org_id(request)
    if not settings.QWEN_API_KEY:
        raise HTTPException(status_code=503, detail="QWEN_API_KEY not configured")
    result = await engineering_agent.run(req.user_message, metadata=req.metadata)
    return AgentRunResponse(
        agent_id=engineering_agent.get_agent().agent_id,
        response=result.response,
        skills_used=result.skills_used,
        intercepted=result.intercepted,
        intercept_skill=result.intercept_skill,
        iterations=result.iterations,
        session_id=req.session_id,
    )


@app.post("/agents/product/run", response_model=AgentRunResponse)
async def run_product(request: Request, req: AgentRunRequest) -> AgentRunResponse:
    _get_org_id(request)
    if not settings.QWEN_API_KEY:
        raise HTTPException(status_code=503, detail="QWEN_API_KEY not configured")
    result, session_id = await product_agent.run(
        req.user_message,
        user_id=req.user_id,
        session_id=req.session_id,
        metadata=req.metadata,
    )
    return AgentRunResponse(
        agent_id=product_agent.get_agent().agent_id,
        response=result.response,
        skills_used=result.skills_used,
        intercepted=result.intercepted,
        intercept_skill=result.intercept_skill,
        iterations=result.iterations,
        session_id=session_id,
    )


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


# ---------- mock attestation ----------

@app.get("/mcp/attestation")
async def get_attestation(request: Request) -> dict[str, Any]:
    _get_org_id(request)
    return brain_tools.attestation()


# ---------- SSE stream ----------

@app.get("/stream")
async def stream(request: Request, token: Optional[str] = None, jwt: Optional[str] = None) -> EventSourceResponse:
    # Resolve org_id from auth middleware, API key token, or Clerk JWT query param.
    org_id = getattr(request.state, "org_id", None)
    if not org_id and token:
        org_id = await resolve_org_from_token(token)
    if not org_id and jwt:
        try:
            claims = await _verify_clerk_jwt(jwt)
            user_id = claims.get("sub", "")
            org_id = claims.get("org_id") or claims.get("org_slug") or user_id or "default"
        except Exception:  # noqa: BLE001
            return JSONResponse({"error": "Invalid JWT"}, status_code=401)
    if not org_id:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

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
            "intercept_by_result": intercept_stats["by_result"],
            "decisions_today": len(recent_events),
            "avg_confidence": sum(r.get("confidence", 0) for r in recent_events) / max(len(recent_events), 1),
            "avg_intercept_time": 0.0,
            "active_agents": 3,
        },
        "last_event": last_event,
        "timestamp": store.utc_now().isoformat(),
    }


@app.post("/settings/api-keys")
async def create_api_key_route(request: Request, body: CreateApiKeyRequest) -> dict[str, Any]:
    org_id = _get_org_id(request)
    result = await store.create_api_key(
        org_id=org_id,
        name=body.name,
        permissions=body.permissions or "read:skills read:events",
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


@app.post("/settings/seed-demo-data", response_model=SeedDemoDataResponse)
async def seed_demo_data_route(request: Request) -> SeedDemoDataResponse:
    """Idempotent org-scoped demo seed for the current authenticated user/org.

    Requires a valid Clerk JWT or API key; uses the same org_id resolution as
    every other endpoint. Reuses the full SAG-enabled demo seed.
    """
    org_id = _get_org_id(request)
    existing = await store.get_skill_count(active_only=False, org_id=org_id)
    if existing > 0:
        return SeedDemoDataResponse(
            seeded=False,
            org_id=org_id,
            skill_count=existing,
            reason="already seeded",
        )
    result = await store.seed_demo_data(org_id=org_id)
    return SeedDemoDataResponse(
        seeded=True,
        org_id=org_id,
        skill_count=result.get("skills_inserted", 0),
    )


# ---------- clerk webhook ----------

@app.post("/clerk/webhook")
async def clerk_webhook(request: Request) -> dict[str, Any]:
    """Handle Clerk webhooks for org provisioning."""
    body = await request.body()
    svix_id = request.headers.get("svix-id")
    svix_timestamp = request.headers.get("svix-timestamp")
    svix_signature = request.headers.get("svix-signature")

    if not all([svix_id, svix_timestamp, svix_signature]):
        raise HTTPException(status_code=400, detail="Missing Svix headers")

    if not settings.CLERK_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="CLERK_WEBHOOK_SECRET not configured")

    signed_content = f"{svix_id}.{svix_timestamp}.{body.decode()}"
    secret_bytes = base64.b64decode(settings.CLERK_WEBHOOK_SECRET.split("_")[1])
    expected_signature = base64.b64encode(
        hmac.new(secret_bytes, signed_content.encode(), hashlib.sha256).digest()
    ).decode()

    signatures = [sig.split(",")[1] for sig in svix_signature.split(" ")]
    if expected_signature not in signatures:
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Check timestamp (5-minute window)
    import time
    current_time = int(time.time())
    if current_time - int(svix_timestamp) > 300:
        raise HTTPException(status_code=400, detail="Timestamp too old")

    payload = json.loads(body)
    event_type = payload.get("type", "")

    if event_type == "organization.created":
        org_data = payload.get("data", {})
        org_id = org_data.get("id", "")
        org_name = org_data.get("name", "")
        if org_id:
            await store.register_agent(f"org-{org_id}", "organization")
            logger.info("Clerk webhook: created org %s (%s)", org_id, org_name)
            return {"status": "org_created", "org_id": org_id}

    return {"status": "ignored", "type": event_type}


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
            "/agents/{support|engineering|product}/run",
            "/sessions/{user_id}", "/stream",
            "/mcp/sse", "/mcp/attestation",
            "/settings/api-keys", "/settings/metrics", "/settings/seed-demo-data",
            "/clerk/webhook",
        ],
    }
