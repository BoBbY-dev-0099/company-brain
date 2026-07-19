from __future__ import annotations

from cryptography.fernet import Fernet
import pytest

from backend.sources import runtime_config


def test_operator_setup_requires_both_server_side_secrets(monkeypatch):
    monkeypatch.setattr(runtime_config.settings, "INTEGRATION_ADMIN_TOKEN", "operator-token")
    monkeypatch.setattr(runtime_config.settings, "INTEGRATION_CONFIG_ENCRYPTION_KEY", "")
    assert runtime_config.operator_setup_enabled() is False
    monkeypatch.setattr(runtime_config.settings, "INTEGRATION_CONFIG_ENCRYPTION_KEY", Fernet.generate_key().decode())
    assert runtime_config.operator_setup_enabled() is True
    assert runtime_config.verify_operator_token("operator-token") is True
    assert runtime_config.verify_operator_token("wrong") is False


def test_slack_signed_events_do_not_require_optional_bot_token():
    runtime_config._validate(
        "slack",
        {"team_id": "T123", "channel_ids": "C123"},
        {"signing_secret": "secret", "bot_token": ""},
    )


def test_provider_validation_and_redaction_never_return_secret():
    with pytest.raises(ValueError, match="token"):
        runtime_config._validate(
            "github",
            {"repos": "acme/repo"},
            {"webhook_secret": "hook", "token": ""},
        )
    redacted = runtime_config._redacted(
        "github",
        {"repos": "acme/repo"},
        {"webhook_secret": "very-secret-webhook", "token": "ghp_secret_token"},
    )
    assert redacted["public"] == {"repos": "acme/repo"}
    assert redacted["secrets"] == {"webhook_secret": True, "token": True}
    assert "very-secret-webhook" not in str(redacted)
    assert "ghp_secret_token" not in str(redacted)

