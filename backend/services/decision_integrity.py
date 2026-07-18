"""Always attach TDX quote or RSA audit to a SAG decision."""

from __future__ import annotations

import logging
from typing import Any

from backend.brain import store
from backend.services import rsa_audit, tdx_attestation

logger = logging.getLogger(__name__)


async def attest_decision(
    *,
    org_id: str,
    skill_id: str,
    metadata: dict[str, Any],
    decision: str,
) -> dict[str, Any]:
    """Prefer TDX; fall back to RSA. Persist whichever succeeds."""
    tdx = await tdx_attestation.maybe_attest(
        skill_id=skill_id,
        metadata=metadata,
        decision=decision,
    )

    if tdx.get("attested"):
        doc = {
            "org_id": org_id,
            "skill_id": skill_id,
            "decision": decision,
            "report_data": tdx["report_data"],
            "tdx_quote": tdx["tdx_quote"],
            "created_at": tdx["timestamp"],
            "verified": False,
            "mode": "tdx",
        }
        quote_id = await store.save_tdx_quote(doc)
        return {
            "mode": "tdx",
            "attested": True,
            "quote_id": quote_id,
            **tdx,
        }

    signed = rsa_audit.sign_decision(
        skill_id=skill_id,
        metadata=metadata,
        decision=decision,
        timestamp=tdx.get("timestamp"),
    )
    audit_id = await store.save_audit_log(
        {
            "org_id": org_id,
            "skill_id": skill_id,
            "decision": decision,
            "metadata": metadata,
            "signature": signed["signature"],
            "payload": signed["payload"],
            "public_key_fingerprint": signed["public_key_fingerprint"],
            "algorithm": signed["algorithm"],
            "created_at": signed["timestamp"],
            "tdx_fallback": True,
        }
    )
    return {
        "mode": "rsa",
        "attested": False,
        "tdx_fallback": True,
        "audit_id": audit_id,
        "tdx": tdx,
        **signed,
    }
