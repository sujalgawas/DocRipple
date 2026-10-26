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

    GITHUB_WEBHOOK_SECRET: str = "dev-secret"
    GITHUB_TOKEN: str = ""
    LLM_BASE_URL: str = "https://api.openai.com/v1"
    LLM_API_KEY: str = "dev-key"
    LLM_MODEL: str = "gpt-4o-mini"
    SQLITE_DB_PATH: str = "docsync_context.db"
    CHECKPOINT_DB_PATH: str = ":memory:"

    # Runtime / Observability
    LOG_LEVEL: str = "INFO"
    MAX_RETRIES: int = 2


settings = AppSettings()