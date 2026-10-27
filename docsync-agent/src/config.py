"""Application settings loaded from environment variables."""

import os

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

    # The Render hostname is only a sensible default off Vercel. On Vercel the
    # deployment has its own hostname, so leave this unset unless configured:
    # connect_repo then skips webhook installation instead of registering a
    # webhook that points at a different service.
    PUBLIC_WEBHOOK_URL: str = (
        ""
        if os.getenv("VERCEL")
        else "https://docripple-api.onrender.com/api/v1/webhooks/github"
    )
    GITHUB_WEBHOOK_SECRET: str = "docripple-secret"
    FRONTEND_URL: str = "http://localhost:5173"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"
    LLM_BASE_URL: str = "https://openrouter.ai/api/v1"
    LLM_API_KEY: str = "dev-key"
    LLM_MODEL: str = "qwen/qwen-2.5-coder-32b-instruct"

    # Vercel mounts the deployment bundle at the read-only /var/task path, so
    # SQLite must live on the writable /tmp mount instead.
    SQLITE_DB_PATH: str = (
        "/tmp/docsync_context.db" if os.getenv("VERCEL") else "docsync_context.db"
    )
    CHECKPOINT_DB_PATH: str = (
        "/tmp/docsync_checkpoints.db" if os.getenv("VERCEL") else ":memory:"
    )

    # Local embedding backend: "tfidf" keeps the Vercel function bundle and
    # Render free tier well under their memory limits.
    # Set to "fastembed" only when the optional fastembed extra is installed.
    EMBEDDING_MODE: str = "tfidf"

    # Job execution strategy. "inline" runs each job inside the request that
    # enqueued it, so Vercel Functions never leave work stranded in a queue
    # that freezes once the response is returned. Set to "queue" on a
    # long-running host (Render/Fly) to use the background worker instead.
    EXECUTION_MODE: str = "inline" if os.getenv("VERCEL") else "inline"  # noqa: RUF034

    # Runtime / Observability
    LOG_LEVEL: str = "INFO"
    MAX_RETRIES: int = 2


settings = AppSettings()