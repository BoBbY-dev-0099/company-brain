"""Regression checks for the production browser-origin allowlist."""

from backend.config import settings
from backend.main import _cors_origins


def test_public_deployment_uses_explicit_cors_origins(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "https://brain.veriflowai.me/")
    monkeypatch.setattr(settings, "CORS_ALLOWED_ORIGINS", "https://operator.example.test")

    origins = _cors_origins()

    assert origins == ["https://brain.veriflowai.me", "https://operator.example.test"]
    assert "*" not in origins


def test_local_development_has_only_local_vite_origins(monkeypatch):
    monkeypatch.setattr(settings, "PUBLIC_BASE_URL", "")
    monkeypatch.setattr(settings, "CORS_ALLOWED_ORIGINS", "")

    assert _cors_origins() == ["http://127.0.0.1:5173", "http://localhost:5173"]
