import base64
from pathlib import Path

from backend.services import rsa_audit


def test_rsa_sign_roundtrip(tmp_path: Path, monkeypatch):
    priv = tmp_path / "audit_private.pem"
    pub = tmp_path / "audit_public.pem"
    monkeypatch.setattr(rsa_audit.settings, "AUDIT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setattr(rsa_audit.settings, "AUDIT_PUBLIC_KEY_PATH", str(pub))
    rsa_audit._private_key = None

    signed = rsa_audit.sign_decision(
        "data-export-large-file-timeout",
        {"export_chunk_size_mb": 8},
        "suspended",
    )
    assert signed["algorithm"] == "RSA-PSS-SHA256"
    assert base64.b64decode(signed["signature"])
    assert priv.exists()

    verified = rsa_audit.verify_signature(signed["payload"], signed["signature"])
    assert verified["valid"] is True


def test_verify_invalid_signature(tmp_path: Path, monkeypatch):
    priv = tmp_path / "audit_private.pem"
    pub = tmp_path / "audit_public.pem"
    monkeypatch.setattr(rsa_audit.settings, "AUDIT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setattr(rsa_audit.settings, "AUDIT_PUBLIC_KEY_PATH", str(pub))
    rsa_audit._private_key = None

    signed = rsa_audit.sign_decision("s1", {"a": 1}, "suspended")
    bad = rsa_audit.verify_signature(signed["payload"], signed["signature"][:-4] + "AAAA")
    assert bad["valid"] is False


def test_key_generation_on_first_run(tmp_path: Path, monkeypatch):
    priv = tmp_path / "nested" / "audit_private.pem"
    pub = tmp_path / "nested" / "audit_public.pem"
    monkeypatch.setattr(rsa_audit.settings, "AUDIT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setattr(rsa_audit.settings, "AUDIT_PUBLIC_KEY_PATH", str(pub))
    rsa_audit._private_key = None
    rsa_audit.ensure_keys()
    assert priv.exists() and pub.exists()
