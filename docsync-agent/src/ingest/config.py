"""Ingest-specific configuration."""

from pydantic_settings import BaseSettings


class IngestConfig(BaseSettings):
    model_config = {"env_prefix": "DOCSYNC_INGEST_", "case_sensitive": False}

    github_webhook_secret: str = ""


ingest_config = IngestConfig()