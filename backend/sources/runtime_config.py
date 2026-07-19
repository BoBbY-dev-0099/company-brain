"""Encrypted, operator-only runtime configuration for source adapters.

This is intentionally a small deployment-admin surface, not a multi-tenant
OAuth marketplace.  It lets the API and the separate source worker share one
sanitised test-workspace configuration without ever returning secret material
to the browser.
"""

from __future__ import annotations

import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from backend.brain import store as brain_store
from backend.config import settings


CONFIG_COLLECTION = "integration_runtime_config"
_DOC_ID = "source-adapters-v1"

_PROVIDER_FIELDS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "slack": (
        ("team_id", "channel_ids"),
        ("signing_secret", "bot_token"),
    ),
    "github": (
        ("repos",),
        ("webhook_secret", "token"),
    ),
    "google_drive": (
        ("folder_id",),
        ("service_account_json",),
    ),
    "web": (
        ("allowed_hosts",),
        (),
    ),
}


def operator_setup_enabled() -> bool:
    """Return whether a deployment has explicitly enabled operator setup."""
    if not settings.INTEGRATION_ADMIN_TOKEN.strip() or not settings.INTEGRATION_CONFIG_ENCRYPTION_KEY.strip():
        return False
    try:
        Fernet(settings.INTEGRATION_CONFIG_ENCRYPTION_KEY.encode("utf-8"))
    except (ValueError, TypeError):
        return False
    return True


def verify_operator_token(value: str | None) -> bool:
    """Constant-time comparison is unnecessary only if setup is disabled."""
    import hmac

    expected = settings.INTEGRATION_ADMIN_TOKEN.encode("utf-8")
    supplied = (value or "").encode("utf-8")
    return bool(expected) and hmac.compare_digest(expected, supplied)


def _fernet() -> Fernet:
    if not operator_setup_enabled():
        raise RuntimeError("Operator Integration Studio is not enabled on this deployment")
    return Fernet(settings.INTEGRATION_CONFIG_ENCRYPTION_KEY.encode("utf-8"))


def _encrypt(value: dict[str, str]) -> str:
    return _fernet().encrypt(json.dumps(value, separators=(",", ":")).encode("utf-8")).decode("utf-8")


def _decrypt(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        decoded = _fernet().decrypt(value.encode("utf-8"))
        result = json.loads(decoded.decode("utf-8"))
    except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Stored connector configuration could not be decrypted") from exc
    return {str(key): str(item) for key, item in result.items()}


def _masked(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "••••••"
    return f"{value[:3]}••••{value[-3:]}"


def _apply(provider: str, public: dict[str, str], secret: dict[str, str]) -> None:
    """Apply an approved config to this process only; never log it."""
    if provider == "slack":
        settings.SLACK_ALLOWED_TEAM_ID = public.get("team_id", "")
        settings.SLACK_ALLOWED_CHANNEL_IDS = public.get("channel_ids", "")
        settings.SLACK_SIGNING_SECRET = secret.get("signing_secret", "")
        settings.SLACK_BOT_TOKEN = secret.get("bot_token", "")
    elif provider == "github":
        settings.GITHUB_REPOS = public.get("repos", "")
        settings.GITHUB_WEBHOOK_SECRET = secret.get("webhook_secret", "")
        settings.GITHUB_TOKEN = secret.get("token", "")
    elif provider == "google_drive":
        settings.GOOGLE_DRIVE_FOLDER_ID = public.get("folder_id", "")
        settings.GOOGLE_SERVICE_ACCOUNT_JSON = secret.get("service_account_json", "")
        # A browser-driven setup uses encrypted JSON in Mongo instead of a
        # host file path.  Leave an environment-provided path untouched when
        # this provider has not been configured through the operator screen.
        if secret.get("service_account_json"):
            settings.GOOGLE_SERVICE_ACCOUNT_FILE = ""
    elif provider == "web":
        settings.WEB_EVIDENCE_ALLOWED_HOSTS = public.get("allowed_hosts", "")


def _validate(provider: str, public: dict[str, str], secret: dict[str, str]) -> None:
    required_public, required_secret = _PROVIDER_FIELDS[provider]
    missing = [name for name in required_public if not public.get(name, "").strip()]
    # Slack's bot token is only used for the optional auth.test helper. Signed
    # Event delivery itself is verified with the signing secret, so requiring a
    # bot token here would falsely block a valid read-only event connection.
    effective_required_secret = tuple(
        name for name in required_secret if not (provider == "slack" and name == "bot_token")
    )
    missing.extend(name for name in effective_required_secret if not secret.get(name, "").strip())
    if missing:
        raise ValueError(f"Missing required configuration: {', '.join(missing)}")
    if provider == "google_drive":
        try:
            parsed = json.loads(secret["service_account_json"])
        except json.JSONDecodeError as exc:
            raise ValueError("service_account_json must be valid JSON") from exc
        required_keys = {"client_email", "private_key", "token_uri"}
        absent = sorted(required_keys - set(parsed)) if isinstance(parsed, dict) else sorted(required_keys)
        if absent:
            raise ValueError(f"service_account_json is missing: {', '.join(absent)}")


def _redacted(provider: str, public: dict[str, str], secret: dict[str, str], updated_at: Any = None) -> dict[str, Any]:
    public_fields, secret_fields = _PROVIDER_FIELDS[provider]
    return {
        "provider": provider,
        "configured": bool(public or secret),
        "public": {key: public.get(key, "") for key in public_fields},
        "secrets": {key: bool(secret.get(key, "")) for key in secret_fields},
        "masked": {key: _masked(secret.get(key, "")) for key in secret_fields if secret.get(key, "")},
        "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else updated_at,
    }


async def load_runtime_config() -> dict[str, dict[str, Any]]:
    """Load encrypted provider values and apply them to the current process."""
    if not operator_setup_enabled():
        return {}
    doc = await brain_store.get_db()[CONFIG_COLLECTION].find_one({"_id": _DOC_ID})
    if not doc:
        return {}
    loaded: dict[str, dict[str, Any]] = {}
    for provider in _PROVIDER_FIELDS:
        item = (doc.get("providers") or {}).get(provider)
        if not isinstance(item, dict):
            continue
        public = {str(key): str(value) for key, value in (item.get("public") or {}).items()}
        secret = _decrypt(item.get("secret_ciphertext"))
        _apply(provider, public, secret)
        loaded[provider] = _redacted(provider, public, secret, item.get("updated_at"))
    return loaded


async def list_runtime_config() -> dict[str, dict[str, Any]]:
    if not operator_setup_enabled():
        return {provider: {"provider": provider, "configured": False, "public": {}, "secrets": {}, "masked": {}, "updated_at": None} for provider in _PROVIDER_FIELDS}
    doc = await brain_store.get_db()[CONFIG_COLLECTION].find_one({"_id": _DOC_ID}) or {}
    result: dict[str, dict[str, Any]] = {}
    for provider in _PROVIDER_FIELDS:
        item = (doc.get("providers") or {}).get(provider) or {}
        public = {str(key): str(value) for key, value in (item.get("public") or {}).items()}
        secret = _decrypt(item.get("secret_ciphertext")) if item.get("secret_ciphertext") else {}
        result[provider] = _redacted(provider, public, secret, item.get("updated_at"))
    return result


async def save_runtime_config(provider: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist and apply a complete provider configuration.

    Empty secret fields preserve an existing secret so an operator can change a
    channel, repository allowlist, or folder without re-pasting credentials.
    """
    if provider not in _PROVIDER_FIELDS:
        raise ValueError("Unsupported integration provider")
    if not operator_setup_enabled():
        raise RuntimeError("Operator Integration Studio is not enabled on this deployment")
    db = brain_store.get_db()
    current = await db[CONFIG_COLLECTION].find_one({"_id": _DOC_ID}) or {}
    existing = ((current.get("providers") or {}).get(provider) or {})
    existing_public = {str(key): str(value) for key, value in (existing.get("public") or {}).items()}
    existing_secret = _decrypt(existing.get("secret_ciphertext")) if existing.get("secret_ciphertext") else {}
    public_fields, secret_fields = _PROVIDER_FIELDS[provider]
    public = {
        key: str(payload[key]).strip() if key in payload else existing_public.get(key, "")
        for key in public_fields
    }
    secret = {
        key: str(payload[key]).strip() if str(payload.get(key, "")).strip() else existing_secret.get(key, "")
        for key in secret_fields
    }
    _validate(provider, public, secret)
    from backend.core.schema import utc_now

    updated_at = utc_now()
    item = {"public": public, "secret_ciphertext": _encrypt(secret), "updated_at": updated_at}
    await db[CONFIG_COLLECTION].update_one(
        {"_id": _DOC_ID},
        {"$set": {f"providers.{provider}": item, "updated_at": updated_at}},
        upsert=True,
    )
    _apply(provider, public, secret)
    return _redacted(provider, public, secret, updated_at)


def setup_instructions() -> dict[str, Any]:
    """Static, safe setup detail rendered by the browser without secrets."""
    return {
        "enabled": operator_setup_enabled(),
        "providers": {
            "slack": {
                "fields": ["team_id", "channel_ids", "signing_secret", "bot_token"],
                "endpoint": "/integrations/slack/events",
                "steps": ["Create a Slack app", "Set the signed Events API request URL", "Install it to the chosen workspace and invite it to the incident channel"],
            },
            "github": {
                "fields": ["repos", "webhook_secret", "token"],
                "endpoint": "/integrations/github/pr",
                "steps": ["Create a fine-grained read-only token", "Add a Pull requests webhook", "Use the exact repository allowlist"],
            },
            "google_drive": {
                "fields": ["folder_id", "service_account_json"],
                "endpoint": "/integrations/google-drive/sync",
                "steps": ["Enable Google Drive API", "Share one folder with the service-account Viewer email", "Paste the service-account JSON only into the operator form"],
            },
            "web": {
                "fields": ["allowed_hosts"],
                "endpoint": "/integrations/web/fetch",
                "steps": ["Allowlist exact public HTTPS hosts", "Use an MCP write-scoped key for explicit fetches"],
            },
        },
    }
