"""Application settings loaded from environment variables."""

import os
from pathlib import Path

from pydantic import field_validator
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
    # Local development talks to the Vite dev server; deployed Vercel builds
    # must redirect back to the public frontend, never to localhost.
    FRONTEND_URL: str = (
        "https://docripple.vercel.app"
        if os.getenv("VERCEL")
        else "http://localhost:5173"
    )
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

    @field_validator("SQLITE_DB_PATH", "CHECKPOINT_DB_PATH", mode="after")
    @classmethod
    def _normalize_db_paths(cls, v: str) -> str:
        if not v or v == ":memory:":
            return v
        p = Path(v)
        posix = p.as_posix().lower()
        is_in_tmp = (
            posix.startswith("/tmp")
            or posix.startswith("tmp/")
            or "/tmp/" in posix
            or posix == "/tmp"
        )
        is_relative = not p.is_absolute() and not (p.anchor in ("/", "\\"))
        try:
            cwd_read_only = not os.access(str(Path.cwd()), os.W_OK)
        except OSError:
            cwd_read_only = True
        try:
            parent_read_only = p.is_absolute() and not os.access(str(p.parent), os.W_OK)
        except OSError:
            parent_read_only = False

        if is_relative or (
            (bool(os.getenv("VERCEL")) or cwd_read_only or parent_read_only)
            and not is_in_tmp
        ):
            return f"/tmp/{p.name}"
        return v


Settings = AppSettings
settings = AppSettings()