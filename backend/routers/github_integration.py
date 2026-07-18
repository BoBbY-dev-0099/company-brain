"""Real GitHub PR webhook → compile skill via Qwen."""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, Response

from backend.config import settings
from backend.core import compiler
from backend.core.schema import RawEvent

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/github", tags=["integrations"])


def _allowed_repo(full_name: str) -> bool:
    allow = [r.strip() for r in settings.GITHUB_REPOS.split(",") if r.strip()]
    if not allow:
        return True
    return full_name in allow


def _verify_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    if not secret:
        return False
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature_header)


@router.post("/pr")
async def github_pr_webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
) -> Any:
    raw = await request.body()
    secret = settings.GITHUB_WEBHOOK_SECRET
    if not secret:
        raise HTTPException(
            status_code=503,
            detail={"error": "GITHUB_WEBHOOK_NOT_CONFIGURED"},
        )
    if not _verify_signature(secret, raw, x_hub_signature_256):
        raise HTTPException(status_code=401, detail={"error": "INVALID_SIGNATURE"})

    if x_github_event != "pull_request":
        return Response(status_code=204)

    import json

    payload = json.loads(raw.decode("utf-8"))
    action = payload.get("action")
    pr = payload.get("pull_request") or {}
    if action != "closed" or not pr.get("merged"):
        return Response(status_code=204)

    repo = (payload.get("repository") or {}).get("full_name") or ""
    if not _allowed_repo(repo):
        return Response(status_code=204)

    if not settings.GITHUB_TOKEN:
        raise HTTPException(status_code=502, detail={"error": "GITHUB_TOKEN_MISSING"})

    pr_number = pr.get("number")
    title = pr.get("title") or ""
    body = pr.get("body") or ""
    diff_url = pr.get("diff_url")
    html_url = pr.get("html_url")
    merge_commit = pr.get("merge_commit_sha")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            diff_resp = await client.get(
                diff_url,
                headers={
                    "Authorization": f"Bearer {settings.GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3.diff",
                    "User-Agent": "company-brain",
                },
            )
            diff_resp.raise_for_status()
            diff_text = diff_resp.text[:12000]
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail={"error": "GITHUB_API_FAILURE", "detail": str(exc)[:300]},
        ) from exc

    org_id = getattr(request.state, "org_id", None) or settings.DEMO_ORG_ID
    narrative = (
        f"Merged GitHub PR #{pr_number} in {repo}: {title}\n\n"
        f"{body}\n\nDiff summary:\n{diff_text}"
    )

    try:
        event = RawEvent(
            event_id=f"gh-pr-{repo.replace('/', '-')}-{pr_number}-{uuid.uuid4().hex[:8]}",
            agent_id="github-integration",
            event_type="resolution",
            content=narrative,
            outcome="merged_pr_compiled",
            org_id=org_id,
            metadata={
                "source": "github_pr",
                "repo": repo,
                "pr_number": pr_number,
                "commit_sha": merge_commit,
                "html_url": html_url,
                "files_changed": len(pr.get("changed_files") or []) or None,
            },
        )
        skill = await compiler.compile_event_to_skill(event)
    except Exception as exc:  # noqa: BLE001
        logger.exception("GitHub PR skill compile failed")
        raise HTTPException(
            status_code=500,
            detail={"error": "QWEN_COMPILE_FAILED", "detail": str(exc)[:400]},
        ) from exc

    return {
        "ok": True,
        "skill_id": skill.skill_id,
        "repo": repo,
        "pr_number": pr_number,
        "commit_sha": merge_commit,
        "html_url": html_url,
        "source": "github_pr",
    }
