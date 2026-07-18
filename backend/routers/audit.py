"""RSA decision audit API (TDX fallback)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from backend.brain import store
from backend.config import settings
from backend.services import rsa_audit

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditSignRequest(BaseModel):
    skill_id: str = Field(min_length=1)
    decision: Literal["suspended", "auto_execute", "intercepted"]
    metadata: dict[str, Any]
    timestamp: str | None = None

    @field_validator("metadata")
    @classmethod
    def metadata_nonempty(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError("metadata must include at least one key")
        return v


class AuditVerifyRequest(BaseModel):
    payload: str
    signature: str
    public_key: str | None = None


def _org(request: Request) -> str:
    return getattr(request.state, "org_id", None) or settings.DEMO_ORG_ID


@router.post("/sign")
async def sign_audit(body: AuditSignRequest, request: Request) -> dict[str, Any]:
    org_id = _org(request)
    ts = body.timestamp or datetime.utcnow().isoformat() + "Z"
    signed = rsa_audit.sign_decision(
        body.skill_id, body.metadata, body.decision, timestamp=ts
    )
    audit_id = await store.save_audit_log(
        {
            "org_id": org_id,
            "skill_id": body.skill_id,
            "decision": body.decision,
            "metadata": body.metadata,
            "signature": signed["signature"],
            "payload": signed["payload"],
            "public_key_fingerprint": signed["public_key_fingerprint"],
            "algorithm": signed["algorithm"],
            "created_at": signed["timestamp"],
            "tdx_fallback": True,
        }
    )
    await store.upsert_public_audit_key(
        org_id, signed["public_key_fingerprint"], rsa_audit.public_key_pem()
    )
    return {**signed, "audit_id": audit_id}


@router.get("/verify")
async def verify_get(
    payload: str,
    signature: str,
    public_key: str | None = None,
) -> dict[str, Any]:
    return rsa_audit.verify_signature(payload, signature, public_key)


@router.post("/verify")
async def verify_post(body: AuditVerifyRequest) -> dict[str, Any]:
    return rsa_audit.verify_signature(body.payload, body.signature, body.public_key)


@router.get("/public-key")
async def get_public_key() -> dict[str, Any]:
    return {
        "algorithm": "RSA-PSS-SHA256",
        "fingerprint": rsa_audit.public_key_fingerprint(),
        "public_key": rsa_audit.public_key_pem(),
    }


@router.get("/chain/{skill_id}")
async def audit_chain(skill_id: str, request: Request) -> dict[str, Any]:
    org_id = _org(request)
    records = await store.list_audit_chain(skill_id, org_id)
    return {"skill_id": skill_id, "count": len(records), "records": records}
