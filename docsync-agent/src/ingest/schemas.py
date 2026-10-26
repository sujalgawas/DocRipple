"""Ingest-specific schemas."""

from typing import Literal

from pydantic import BaseModel

from src.contracts.schemas import WebhookJob


class GitHubRepository(BaseModel):
    full_name: str


class GitHubPushPayload(BaseModel):
    ref: str
    before: str
    after: str
    repository: GitHubRepository


class GitHubCommitRef(BaseModel):
    sha: str
    ref: str | None = None


class GitHubPRDetail(BaseModel):
    base: GitHubCommitRef
    head: GitHubCommitRef


class GitHubPullRequestPayload(BaseModel):
    action: str
    number: int
    pull_request: GitHubPRDetail
    repository: GitHubRepository


class WebhookAckResponse(BaseModel):
    status: Literal["enqueued", "duplicate_ignored", "event_ignored"] | str
    delivery_id: str
    job: WebhookJob | None = None