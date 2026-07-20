"""Tests for truthful, configuration-derived integration catalog output."""

from __future__ import annotations

from backend.routers import integration_catalog as catalog


def test_catalog_defaults_to_setup_or_preview_without_claiming_connections(monkeypatch):
    monkeypatch.setattr(catalog.settings, "PUBLIC_BASE_URL", "")
    monkeypatch.setattr(catalog.settings, "GITHUB_WEBHOOK_SECRET", "")
    monkeypatch.setattr(catalog.settings, "GITHUB_TOKEN", "")
    monkeypatch.setattr(catalog.settings, "GITHUB_REPOS", "")
    monkeypatch.setattr(catalog.settings, "MCP_REMOTE_ENABLED", False)
    monkeypatch.setattr(catalog.settings, "MCP_REQUIRE_API_KEY", True)
    monkeypatch.setattr(catalog.settings, "MCP_TRANSPORT", "streamable-http")

    response = catalog.build_integration_catalog()
    boundaries = {item["id"]: item for item in response["connection_boundaries"]}

    assert boundaries["evidence"]["status"] == "setup_required"
    assert boundaries["workflow"]["status"] == "contract_ready"
    assert "curl -X POST http://localhost:8000/workflow-runs" in boundaries["workflow"]["example"]["code"]
    assert [item["source_type"] for item in boundaries["workflow"]["example"]["body"]["evidence"]] == [
        "alibaba_oss_object",
        "slack_message",
        "github_pull_request",
    ]
    assert boundaries["workflow"]["example"]["body"]["evidence"][0]["occurred_at"]
    assert boundaries["agent"]["status"] == "preview"
    assert response["connections"] == response["connection_boundaries"]
    assert boundaries["agent"]["endpoint"] == "/mcp/"


def test_catalog_reports_only_fully_configured_github_and_authenticated_https_mcp(monkeypatch):
    monkeypatch.setattr(catalog.settings, "PUBLIC_BASE_URL", "https://brain.veriflowai.me/")
    monkeypatch.setattr(catalog.settings, "GITHUB_WEBHOOK_SECRET", "secret")
    monkeypatch.setattr(catalog.settings, "GITHUB_TOKEN", "token")
    monkeypatch.setattr(catalog.settings, "GITHUB_REPOS", "acme/service")
    monkeypatch.setattr(catalog.settings, "MCP_REMOTE_ENABLED", True)
    monkeypatch.setattr(catalog.settings, "MCP_REQUIRE_API_KEY", True)
    monkeypatch.setattr(catalog.settings, "MCP_TRANSPORT", "streamable-http")

    response = catalog.build_integration_catalog()
    boundaries = {item["id"]: item for item in response["connection_boundaries"]}

    assert boundaries["evidence"]["status"] == "connected"
    assert boundaries["evidence"]["endpoint"] == "https://brain.veriflowai.me/api/integrations/github/pr"
    assert boundaries["agent"]["status"] == "connected"
    assert boundaries["agent"]["endpoint"] == "https://brain.veriflowai.me/mcp/"
    assert boundaries["agent"]["configuration"]["legacy_sse_retired"] is True


def test_catalog_does_not_treat_non_https_or_unscoped_mcp_as_connected(monkeypatch):
    monkeypatch.setattr(catalog.settings, "PUBLIC_BASE_URL", "http://8.218.174.77")
    monkeypatch.setattr(catalog.settings, "MCP_REMOTE_ENABLED", True)
    monkeypatch.setattr(catalog.settings, "MCP_REQUIRE_API_KEY", False)
    monkeypatch.setattr(catalog.settings, "MCP_TRANSPORT", "streamable-http")

    response = catalog.build_integration_catalog()
    agent = next(item for item in response["connection_boundaries"] if item["id"] == "agent")

    assert agent["status"] == "preview"
