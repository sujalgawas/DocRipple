"""Ingest service — normalize events, deduplicate deliveries, and enqueue WebhookJobs."""

import asyncio
import logging
from datetime import UTC, datetime

from src.contracts.protocols import ContextStoreProtocol
from src.contracts.schemas import WebhookJob
from src.ingest.schemas import WebhookAckResponse

logger = logging.getLogger(__name__)

ZERO_SHA = "0000000000000000000000000000000000000000"


class IngestService:
    """Handles event filtering, deduplication, job normalization, and queue dispatch."""

    async def handle_webhook(
        self,
        delivery_id: str,
        event_type: str,
        payload: dict,
        store: ContextStoreProtocol,
        queue: asyncio.Queue[WebhookJob],
        enqueue: bool = True,
    ) -> WebhookAckResponse:
        """Process an incoming GitHub webhook event."""
        # 1. Event type filtering (ignore ping, unsupported events)
        if event_type == "ping" or event_type not in ("push", "pull_request"):
            logger.info("Ignoring event '%s' for delivery %s", event_type, delivery_id)
            return WebhookAckResponse(status="event_ignored", delivery_id=delivery_id)

        # 2. PR action filtering (only opened and synchronize)
        if event_type == "pull_request":
            action = payload.get("action", "")
            if action not in {"opened", "synchronize"}:
                logger.info(
                    "Ignoring PR action '%s' for delivery %s", action, delivery_id
                )
                return WebhookAckResponse(status="event_ignored", delivery_id=delivery_id)

        # 3. Branch deletion filtering (zero-commit pushes)
        if event_type == "push":
            after = payload.get("after", "")
            if after == ZERO_SHA or after == "0" * 40:
                logger.info(
                    "Ignoring zero-commit branch deletion push for delivery %s",
                    delivery_id,
                )
                return WebhookAckResponse(status="event_ignored", delivery_id=delivery_id)

        # 4. Extract repository information
        repo_data = payload.get("repository") or {}
        repo_full_name = repo_data.get("full_name") or ""

        # 5. Deduplication check via ContextStore
        is_new = await store.check_and_record_delivery(delivery_id, repo_full_name)
        if not is_new:
            logger.warning(
                "Duplicate delivery ID %s for repo %s; ignoring",
                delivery_id,
                repo_full_name,
            )
            return WebhookAckResponse(
                status="duplicate_ignored", delivery_id=delivery_id
            )

        # 6. Normalize into frozen WebhookJob
        if event_type == "push":
            base_sha = payload.get("before", "")
            head_sha = payload.get("after", "")
            ref = payload.get("ref", "")
            base_ref = ""
            pr_number = None
            head_commit = payload.get("head_commit") or {}
            commit_message = head_commit.get("message", "")
            author = (
                (head_commit.get("author") or {}).get("username")
                or (head_commit.get("author") or {}).get("name")
                or (payload.get("pusher") or {}).get("name")
                or (payload.get("sender") or {}).get("login")
                or ""
            )
        else:  # pull_request
            pr_data = payload.get("pull_request") or {}
            base_data = pr_data.get("base") or {}
            head_data = pr_data.get("head") or {}
            base_sha = base_data.get("sha", "")
            head_sha = head_data.get("sha", "")
            ref = head_data.get("ref") or base_data.get("ref") or ""
            base_ref = base_data.get("ref", "")
            pr_number = payload.get("number")
            commit_message = pr_data.get("title", "")
            author = (
                (pr_data.get("user") or {}).get("login")
                or (payload.get("sender") or {}).get("login")
                or ""
            )

        job = WebhookJob(
            delivery_id=delivery_id,
            event_type=event_type,
            repo_full_name=repo_full_name,
            base_sha=base_sha,
            head_sha=head_sha,
            ref=ref,
            base_ref=base_ref,
            pr_number=pr_number,
            received_at=datetime.now(UTC),
            commit_message=commit_message,
            author=author,
        )

        # 7. Dispatch: queue for a background worker, or hand back to the
        # caller for immediate inline execution (required on Vercel).
        if enqueue:
            await queue.put(job)
            logger.info(
                "Enqueued WebhookJob for %s (%s) from delivery %s",
                repo_full_name,
                event_type,
                delivery_id,
            )
        else:
            logger.info(
                "Handing WebhookJob for %s (%s) from delivery %s to inline runner",
                repo_full_name,
                event_type,
                delivery_id,
            )

        return WebhookAckResponse(
            status="enqueued",
            delivery_id=delivery_id,
            job=job,
        )


ingest_service = IngestService()