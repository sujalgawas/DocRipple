"""Ingest service — enqueue verified WebhookJob for background processing."""

import logging

from src.contracts.schemas import WebhookJob
from src.ingest.schemas import GitHubPushPayload

logger = logging.getLogger(__name__)


async def enqueue_webhook_job(payload: GitHubPushPayload, delivery_id: str) -> WebhookJob:
    """Create and enqueue a WebhookJob from a verified GitHub push payload."""
    repo = payload.repository
    diff = ""  # TODO: Fetch diff from GitHub API or accept it from payload
    job = WebhookJob(
        delivery_id=delivery_id,
        repo_full_name=repo.get("full_name", ""),
        default_branch=repo.get("default_branch", "main"),
        head_commit=payload.after,
        diff=diff,
    )
    logger.info("Enqueued job %s for repo %s", job.job_id, job.repo_full_name)
    # TODO: push to background queue / task runner
    return job