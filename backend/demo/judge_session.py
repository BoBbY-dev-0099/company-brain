"""Opaque, short-lived browser sessions for the public judge playground."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import uuid
from dataclasses import dataclass

from backend.config import settings


COOKIE_NAME = "company_brain_judge_session"
ORG_PREFIX = "judge-sandbox"


@dataclass(frozen=True)
class JudgeSession:
    session_id: str
    expires_at: int

    @property
    def org_id(self) -> str:
        return f"{ORG_PREFIX}:{self.session_id}"


def _signature(payload: str) -> str:
    digest = hmac.new(
        settings.JUDGE_SANDBOX_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def issue_judge_session(*, now: int | None = None) -> tuple[str, JudgeSession]:
    issued_at = int(now if now is not None else time.time())
    session = JudgeSession(
        session_id=uuid.uuid4().hex,
        expires_at=issued_at + settings.JUDGE_SANDBOX_TTL_SECONDS,
    )
    payload = f"v1.{session.session_id}.{session.expires_at}"
    return f"{payload}.{_signature(payload)}", session


def parse_judge_session(token: str | None, *, now: int | None = None) -> JudgeSession | None:
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "v1":
        return None
    _version, session_id, expiry_text, signature = parts
    if len(session_id) != 32 or not all(char in "0123456789abcdef" for char in session_id):
        return None
    try:
        expires_at = int(expiry_text)
    except ValueError:
        return None
    payload = ".".join(parts[:3])
    if not hmac.compare_digest(signature, _signature(payload)):
        return None
    current = int(now if now is not None else time.time())
    if expires_at <= current:
        return None
    return JudgeSession(session_id=session_id, expires_at=expires_at)


def is_judge_sandbox_org(org_id: str | None) -> bool:
    return bool(org_id and org_id.startswith(f"{ORG_PREFIX}:"))
