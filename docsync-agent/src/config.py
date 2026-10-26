"""Global application settings loaded from environment variables."""

from pydantic_settings import BaseSettings


class GlobalSettings(BaseSettings):
    """Top-level settings shared across all modules."""

    model_config = {"env_prefix": "DOCSYNC_", "case_sensitive": False}

    # Database
    database_url: str = "sqlite+aiosqlite:///docsync.db"

    # GitHub
    github_token: str = ""
    github_webhook_secret: str = ""

    # LLM Provider
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"

    # Runtime
    max_retries: int = 2
    log_level: str = "INFO"


settings = GlobalSettings()