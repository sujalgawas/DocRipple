"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Global application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    GITHUB_TOKEN: str = ""
    GITHUB_CLIENT_ID: str = ""
    GITHUB_CLIENT_SECRET: str = ""
    PUBLIC_WEBHOOK_URL: str = (
        "https://docripple-api.onrender.com/api/v1/webhooks/github"
    )
    GITHUB_WEBHOOK_SECRET: str = "docripple-secret"
    FRONTEND_URL: str = "http://localhost:5173"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = "dev-key"
    LLM_MODEL: str = "gpt-4o-mini"
    SQLITE_DB_PATH: str = "docsync_context.db"
    CHECKPOINT_DB_PATH: str = ":memory:"

    # Local embedding backend: "tfidf" keeps the Render free tier under 512 MB.
    # Set to "fastembed" only when the optional fastembed extra is installed.
    EMBEDDING_MODE: str = "tfidf"

    # Runtime / Observability
    LOG_LEVEL: str = "INFO"
    MAX_RETRIES: int = 2


settings = AppSettings()