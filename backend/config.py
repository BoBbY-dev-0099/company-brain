import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    QWEN_API_KEY: str = ""
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

    CLERK_PUBLISHABLE_KEY: str = ""
    CLERK_SECRET_KEY: str = ""
    CLERK_JWKS_URL: str = "https://api.clerk.com/v1/jwks"
    CLERK_WEBHOOK_SECRET: str = ""

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    INITIAL_CONFIDENCE: float = 0.60
    CONFIDENCE_INTERCEPT: float = 0.70
    CONFIDENCE_AUTO_EXECUTE: float = 0.85
    RELEVANCE_FLOOR: float = float(os.getenv("RELEVANCE_FLOOR", "0.35"))
    CONFIDENCE_INCREMENT: float = 0.05
    EMBEDDING_DIMENSIONS: int = 1024


settings = Settings()
