import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY", "")
    QWEN_BASE_URL: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    # Embeddings may need a different compatible-mode endpoint than chat completions.
    QWEN_EMBEDDING_BASE_URL: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    QWEN_COMPILER_MODEL: str = "qwen-plus"
    QWEN_AGENT_MODEL: str = "qwen-plus"
    QWEN_EMBEDDING_MODEL: str = "text-embedding-v3"
    # Explicit context cache on the compiler's frozen system prefix (>1024 tokens).
    QWEN_ENABLE_EXPLICIT_CACHE: bool = True

    MONGODB_URI: str = "mongodb://localhost:27017/companybrain?replicaSet=rs0&directConnection=true"
    MONGODB_DB_NAME: str = "companybrain"

    # Public deployment identity. Leave this empty in local development so
    # callers do not mistake a local server for the public judge deployment.
    # A verified ECS deployment sets this to https://brain.veriflowai.me.
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "")

    # Remote MCP is intentionally opt-in. The production connector uses
    # Streamable HTTP at /mcp/ with an X-Brain-Api-Key on every request.
    MCP_SERVER_URL: str = os.getenv("MCP_SERVER_URL", "http://localhost:8000/mcp/")
    MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "streamable-http")
    MCP_REMOTE_ENABLED: bool = os.getenv("MCP_REMOTE_ENABLED", "false").lower() == "true"
    MCP_REQUIRE_API_KEY: bool = os.getenv("MCP_REQUIRE_API_KEY", "true").lower() == "true"
    # Legacy SSE had no request-scoped API-key enforcement. It is disabled by
    # default and must never be advertised as the production connector.
    MCP_LEGACY_SSE_ENABLED: bool = os.getenv("MCP_LEGACY_SSE_ENABLED", "false").lower() == "true"
    MCP_ALLOWED_ORIGINS: str = os.getenv("MCP_ALLOWED_ORIGINS", "")
    # Browser API access is same-origin in the deployed app.  Extra origins
    # must be explicitly configured rather than using a wildcard in production.
    CORS_ALLOWED_ORIGINS: str = os.getenv("CORS_ALLOWED_ORIGINS", "")

    BRAIN_API_KEY: str = os.getenv("BRAIN_API_KEY", "")

    # Open UI / hackathon sandbox (keep separate from the immutable fixture).
    DEMO_ORG_ID: str = os.getenv("DEMO_ORG_ID", "sandbox")
    # The canonical judge fixture is deliberately separate from the open UI
    # org.  It is seeded once and must not be used as a scratchpad for clicks
    # during a recording or a live judging session.
    JUDGE_DEMO_ORG_ID: str = os.getenv("JUDGE_DEMO_ORG_ID", "judge-demo-v1")
    SANDBOX_ORG_ID: str = os.getenv("SANDBOX_ORG_ID", "sandbox")
    DEMO_SCENARIO_VERSION: str = os.getenv("DEMO_SCENARIO_VERSION", "judge-demo-v1")
    # The public judge playground receives an opaque, signed browser session.
    # It is deliberately separate from API-key organizations and expires quickly.
    JUDGE_SANDBOX_SECRET: str = os.getenv("JUDGE_SANDBOX_SECRET", "local-judge-sandbox-secret")
    JUDGE_SANDBOX_TTL_SECONDS: int = int(os.getenv("JUDGE_SANDBOX_TTL_SECONDS", "3600"))
    BUILD_SHA: str = os.getenv("BUILD_SHA", "unknown")

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    INITIAL_CONFIDENCE: float = 0.60
    CONFIDENCE_INTERCEPT: float = 0.70
    CONFIDENCE_AUTO_EXECUTE: float = 0.85
    RELEVANCE_FLOOR: float = float(os.getenv("RELEVANCE_FLOOR", "0.35"))
    CONFIDENCE_INCREMENT: float = 0.05
    EMBEDDING_DIMENSIONS: int = 1024

    # TDX attestation (Alibaba Confidential VM). Soft-fails to RSA audit.
    TDX_BINARY_PATH: str = os.getenv(
        "TDX_BINARY_PATH",
        "/opt/alibaba/tdx-quote-generation-sample/app",
    )
    TDX_TIMEOUT: float = float(os.getenv("TDX_TIMEOUT", "10"))

    # RSA decision-audit fallback keys
    AUDIT_PRIVATE_KEY_PATH: str = os.getenv(
        "AUDIT_PRIVATE_KEY_PATH",
        "secrets/audit_private.pem",
    )
    AUDIT_PUBLIC_KEY_PATH: str = os.getenv(
        "AUDIT_PUBLIC_KEY_PATH",
        "secrets/audit_public.pem",
    )

    # Optional real GitHub webhook connector
    GITHUB_WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_REPOS: str = os.getenv("GITHUB_REPOS", "")

    # Source adapters are deliberately least-privilege and configured on the
    # server.  The public judge UI never receives these values and cannot
    # create a connection by submitting a credential.
    SOURCE_ORG_ID: str = os.getenv("SOURCE_ORG_ID", "sandbox")

    # Slack Events API: only verified events from explicitly allowlisted
    # workspace/channel IDs are accepted.  A bot token is optional and only
    # required when a future adapter needs to enrich a permitted thread.
    SLACK_SIGNING_SECRET: str = os.getenv("SLACK_SIGNING_SECRET", "")
    SLACK_BOT_TOKEN: str = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_ALLOWED_TEAM_ID: str = os.getenv("SLACK_ALLOWED_TEAM_ID", "")
    SLACK_ALLOWED_CHANNEL_IDS: str = os.getenv("SLACK_ALLOWED_CHANNEL_IDS", "")
    SLACK_EVENT_MAX_AGE_SECONDS: int = int(os.getenv("SLACK_EVENT_MAX_AGE_SECONDS", "300"))

    # Google Drive: a read-only service account is scoped to one explicitly
    # shared folder.  Either a JSON value or a mounted JSON file may be used;
    # the latter is preferred for ECS deployment.
    GOOGLE_SERVICE_ACCOUNT_JSON: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
    GOOGLE_SERVICE_ACCOUNT_FILE: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")
    GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
    GOOGLE_DRIVE_ALLOWED_MIME_TYPES: str = os.getenv(
        "GOOGLE_DRIVE_ALLOWED_MIME_TYPES",
        "application/vnd.google-apps.document,text/plain,application/pdf",
    )
    GOOGLE_DRIVE_SYNC_INTERVAL_SECONDS: int = int(os.getenv("GOOGLE_DRIVE_SYNC_INTERVAL_SECONDS", "300"))
    GOOGLE_DRIVE_MAX_FILE_BYTES: int = int(os.getenv("GOOGLE_DRIVE_MAX_FILE_BYTES", "750000"))

    # Verified web evidence is an authenticated, explicit URL fetch â€” it is
    # not an open web-search connector.  Hosts must be configured to prevent
    # the server becoming an SSRF proxy.
    WEB_EVIDENCE_ALLOWED_HOSTS: str = os.getenv("WEB_EVIDENCE_ALLOWED_HOSTS", "")
    WEB_EVIDENCE_MAX_BYTES: int = int(os.getenv("WEB_EVIDENCE_MAX_BYTES", "250000"))
    WEB_EVIDENCE_TIMEOUT_SECONDS: float = float(os.getenv("WEB_EVIDENCE_TIMEOUT_SECONDS", "8"))

    # The separate worker owns durable source-event processing and optional
    # Drive polling.  The API only accepts authenticated/signed source input.
    SOURCE_WORKER_POLL_SECONDS: float = float(os.getenv("SOURCE_WORKER_POLL_SECONDS", "2"))


settings = Settings()
