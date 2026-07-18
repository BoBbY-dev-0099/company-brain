"""RSA-PSS-SHA256 decision audit fallback when TDX is unavailable."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from backend.config import settings

logger = logging.getLogger(__name__)

_private_key: RSAPrivateKey | None = None


def _key_paths() -> tuple[Path, Path]:
    priv = Path(settings.AUDIT_PRIVATE_KEY_PATH)
    pub = Path(settings.AUDIT_PUBLIC_KEY_PATH or str(priv.with_name("audit_public.pem")))
    return priv, pub


def ensure_keys() -> RSAPrivateKey:
    global _private_key
    if _private_key is not None:
        return _private_key

    priv_path, pub_path = _key_paths()
    priv_path.parent.mkdir(parents=True, exist_ok=True)

    if priv_path.exists():
        _private_key = serialization.load_pem_private_key(
            priv_path.read_bytes(),
            password=None,
        )
        assert isinstance(_private_key, RSAPrivateKey)
        return _private_key

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    logger.info("Generated RSA audit keypair at %s", priv_path)
    _private_key = key
    return key


def public_key_pem() -> str:
    key = ensure_keys()
    return key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("ascii")


def public_key_fingerprint() -> str:
    der = ensure_keys().public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha256(der).hexdigest()


def canonical_payload(
    skill_id: str,
    metadata: dict[str, Any],
    decision: str,
    timestamp: str,
) -> str:
    return json.dumps(
        {
            "skill_id": skill_id,
            "metadata": metadata,
            "decision": decision,
            "timestamp": timestamp,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def sign_decision(
    skill_id: str,
    metadata: dict[str, Any],
    decision: str,
    timestamp: str | None = None,
) -> dict[str, Any]:
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    payload = canonical_payload(skill_id, metadata, decision, ts)
    key = ensure_keys()
    signature = key.sign(
        payload.encode("utf-8"),
        padding.PSS(
            mgf=padding.MGF1(hashes.SHA256()),
            salt_length=padding.PSS.MAX_LENGTH,
        ),
        hashes.SHA256(),
    )
    return {
        "skill_id": skill_id,
        "decision": decision,
        "payload": payload,
        "signature": base64.b64encode(signature).decode("ascii"),
        "public_key_fingerprint": public_key_fingerprint(),
        "algorithm": "RSA-PSS-SHA256",
        "timestamp": ts,
        "tdx_fallback": True,
    }


def verify_signature(payload: str, signature_b64: str, public_key_pem_str: str | None = None) -> dict[str, Any]:
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    pem = (public_key_pem_str or public_key_pem()).encode("utf-8")
    pub = load_pem_public_key(pem)
    sig = base64.b64decode(signature_b64)
    payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    try:
        pub.verify(
            sig,
            payload.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {"valid": True, "payload_hash": payload_hash}
    except Exception:  # noqa: BLE001
        return {"valid": False, "payload_hash": payload_hash}
