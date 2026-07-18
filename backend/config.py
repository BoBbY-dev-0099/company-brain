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

    MCP_SERVER_URL: str = "http://localhost:8000/mcp/sse"

    BRAIN_API_KEY: str = os.getenv("BRAIN_API_KEY", "")

    # Open UI / hackathon demo org (keep separate from polluted local `default`).
    DEMO_ORG_ID: str = os.getenv("DEMO_ORG_ID", "integrations-demo")

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


settings = Settings()
