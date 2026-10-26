"""ContextStore-specific configuration via pydantic-settings."""

from pydantic_settings import BaseSettings


class ContextStoreConfig(BaseSettings):
    """SQLite persistence configuration.

    Override via ``DOCSYNC_CS_SQLITE_DB_PATH`` env var.
    """

    model_config = {"env_prefix": "DOCSYNC_CS_", "case_sensitive": False}

    sqlite_db_path: str = "docsync_context.db"