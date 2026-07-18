"""TDX attestation HTTP API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from backend.brain import store
from backend.config import settings
from backend.services import tdx_attestation

router = APIRouter(prefix="/attestation", tags=["attestation"])


class TDXQuoteRequest(BaseModel):
    skill_id: str = Field(min_length=1)
    decision: Literal["suspended", "auto_execute", "intercepted"]
    metadata: dict[str, Any]
    timestamp: str

    @field_validator("metadata")
    @classmethod
    def metadata_nonempty(cls, v: dict[str, Any]) -> dict[str, Any]:
        if not v:
            raise ValueError("metadata must include at least one key")
        return v

    @field_validator("timestamp")
    @classmethod
    def iso_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("timestamp must be ISO 8601") from exc
        return v


def _org(request: Request) -> str:
    return getattr(request.state, "org_id", None) or settings.DEMO_ORG_ID


@router.post("/quote")
async def create_quote(body: TDXQuoteRequest, request: Request) -> dict[str, Any]:
    org_id = _org(request)
    try:
        if not tdx_attestation.tdx_guest_present() and not __import__("os").path.exists(
            settings.TDX_BINARY_PATH
        ):
            raise FileNotFoundError(settings.TDX_BINARY_PATH)

        report_data = tdx_attestation.build_report_data(
            body.skill_id, body.metadata, body.decision, body.timestamp
        )
        raw = await tdx_attestation.generate_tdx_quote(report_data)
        quote_b64 = tdx_attestation.encode_quote(raw)
        quote_id = await store.save_tdx_quote(
            {
                "org_id": org_id,
                "skill_id": body.skill_id,
                "decision": body.decision,
                "report_data": report_data,
                "tdx_quote": quote_b64,
                "created_at": body.timestamp,
                "verified": False,
                "mode": "tdx",
            }
        )
        return {
            "skill_id": body.skill_id,
            "decision": body.decision,
            "report_data": report_data,
            "tdx_quote": quote_b64,
            "attested": True,
            "timestamp": body.timestamp,
            "quote_id": quote_id,
        }
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail={"error": "TDX_TIMEOUT", "detail": str(exc)}) from exc
    except FileNotFoundError as exc:
        # Soft path: RSA sign even when Mongo is unavailable (hackathon r9i hosts).
        from backend.services import rsa_audit

        signed = rsa_audit.sign_decision(
            body.skill_id, body.metadata, body.decision, timestamp=body.timestamp
        )
        audit_id = None
        try:
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
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            status_code=503,
            detail={
                "error": "TDX_UNAVAILABLE",
                "detail": "TDX quote generation failed",
                "fallback": "RSA_AUDIT",
                "audit": {
                    "audit_id": audit_id,
                    "signature": signed.get("signature"),
                    "public_key_fingerprint": signed.get("public_key_fingerprint"),
                    "algorithm": signed.get("algorithm"),
                },
                "missing": str(exc),
            },
        ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail={"error": "TDX_FAILED", "detail": str(exc)[:500]},
        ) from exc


@router.get("/verify/{quote_id}")
async def verify_quote(quote_id: str, request: Request) -> dict[str, Any]:
    org_id = _org(request)
    doc = await store.get_tdx_quote(quote_id, org_id=org_id)
    if not doc:
        raise HTTPException(status_code=404, detail={"error": "QUOTE_NOT_FOUND"})
    return {**doc, "verification_status": "stored" if doc.get("tdx_quote") else "missing"}


@router.get("/status")
async def attestation_status() -> dict[str, Any]:
    guest = tdx_attestation.tdx_guest_present()
    binary = __import__("os").path.exists(settings.TDX_BINARY_PATH)
    return {
        "tdx_guest": guest,
        "tdx_binary": binary,
        "mode": "tdx" if guest and binary else "rsa_fallback",
        "binary_path": settings.TDX_BINARY_PATH,
    }
