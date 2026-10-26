"""Ingest configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class IngestConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DOCSYNC_INGEST_", case_sensitive=False)

    GITHUB_WEBHOOK_SECRET: str = "dev-secret"
    SUPPORTED_EVENTS: tuple[str, ...] = ("push", "pull_request")


ingest_config = IngestConfig()