"""Intel TDX quote generation (Alibaba Cloud guest) with soft-fail when unavailable."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

from backend.config import settings

logger = logging.getLogger(__name__)


def tdx_guest_present() -> bool:
    return os.path.exists("/dev/tdx_guest")


def build_report_data(
    skill_id: str,
    metadata: dict[str, Any],
    decision: str,
    timestamp: str,
) -> str:
    sorted_meta = json.dumps(metadata, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(
        f"{skill_id}:{sorted_meta}:{decision}:{timestamp}".encode("utf-8")
    ).hexdigest()
    return digest[:64]


async def generate_tdx_quote(report_data: str) -> bytes:
    binary = settings.TDX_BINARY_PATH
    if not os.path.exists(binary):
        raise FileNotFoundError(binary)

    proc = await asyncio.create_subprocess_exec(
        "sudo",
        binary,
        "-d",
        report_data,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=settings.TDX_TIMEOUT)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.communicate()
        raise TimeoutError(f"TDX quote timed out after {settings.TDX_TIMEOUT}s") from exc

    if proc.returncode != 0:
        detail = (stderr or b"").decode("utf-8", errors="replace")[:500]
        raise RuntimeError(detail or f"TDX binary exited {proc.returncode}")

    return stdout


def encode_quote(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


async def maybe_attest(
    *,
    skill_id: str,
    metadata: dict[str, Any],
    decision: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Try TDX; return either attested quote payload or fallback marker."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    report_data = build_report_data(skill_id, metadata, decision, ts)

    if not tdx_guest_present() and not os.path.exists(settings.TDX_BINARY_PATH):
        return {
            "attested": False,
            "fallback": "RSA_AUDIT",
            "error": "TDX_UNAVAILABLE",
            "report_data": report_data,
            "timestamp": ts,
            "skill_id": skill_id,
            "decision": decision,
        }

    try:
        raw = await generate_tdx_quote(report_data)
        return {
            "attested": True,
            "skill_id": skill_id,
            "decision": decision,
            "report_data": report_data,
            "tdx_quote": encode_quote(raw),
            "timestamp": ts,
        }
    except FileNotFoundError:
        return {
            "attested": False,
            "fallback": "RSA_AUDIT",
            "error": "TDX_UNAVAILABLE",
            "detail": "TDX quote generation binary missing",
            "report_data": report_data,
            "timestamp": ts,
            "skill_id": skill_id,
            "decision": decision,
        }
    except TimeoutError as exc:
        return {
            "attested": False,
            "fallback": "RSA_AUDIT",
            "error": "TDX_TIMEOUT",
            "detail": str(exc),
            "report_data": report_data,
            "timestamp": ts,
            "skill_id": skill_id,
            "decision": decision,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("TDX quote failed: %s", exc)
        return {
            "attested": False,
            "fallback": "RSA_AUDIT",
            "error": "TDX_FAILED",
            "detail": str(exc)[:500],
            "report_data": report_data,
            "timestamp": ts,
            "skill_id": skill_id,
            "decision": decision,
        }
