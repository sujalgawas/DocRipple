"""Ingest-specific schemas."""

from pydantic import BaseModel


class GitHubPushPayload(BaseModel):
    """Minimal push event fields needed by the webhook."""

    ref: str
    after: str
    repository: dict  # full_name, default_branch
    head_commit: dict  # id, message
    commits: list[dict] = []


class WebhookAckResponse(BaseModel):
    status: str
    delivery_id: str
    job_id: str | None = None