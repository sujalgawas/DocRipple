"""Ingest router — GitHub webhook endpoints."""

import asyncio
import json
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from src.contracts.protocols import ContextStoreProtocol
from src.contracts.schemas import WebhookJob
from src.ingest.dependencies import (
    get_context_store,
    get_job_queue,
    verify_github_signature,
)
from src.ingest.schemas import WebhookAckResponse
from src.ingest.service import ingest_service

router = APIRouter(prefix="/api/v1/webhooks", tags=["ingest"])
legacy_router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)

# Branches created by the agent itself. Pushes here must never re-trigger a run,
# otherwise the docs PR would cause an infinite sync loop.
DOCSYNC_BRANCH_PREFIXES = ("docripple/", "docsync/")


@router.post(
    "/github",
    response_model=WebhookAckResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@legacy_router.post(
    "/webhook",
    response_model=WebhookAckResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@legacy_router.post(
    "/api/v1/webhook",
    response_model=WebhookAckResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def github_webhook(
    request: Request,
    raw_body: Annotated[bytes, Depends(verify_github_signature)],
    x_github_delivery: Annotated[str, Header(alias="X-GitHub-Delivery")],
    x_github_event: Annotated[str, Header(alias="X-GitHub-Event")],
    store: Annotated[ContextStoreProtocol, Depends(get_context_store)],
    queue: Annotated[asyncio.Queue[WebhookJob], Depends(get_job_queue)],
) -> WebhookAckResponse:
    """Receive GitHub push/pull_request events, dedupe, and run the pipeline."""
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as exc:
        logger.warning("Failed to parse JSON webhook payload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc

    repo_full_name = (payload.get("repository") or {}).get("full_name") or ""
    branch = _event_branch(x_github_event, payload)

    # 1. Never re-run the agent's own documentation branches.
    if branch.startswith(DOCSYNC_BRANCH_PREFIXES):
        logger.info(
            "Ignoring agent branch '%s' for delivery %s", branch, x_github_delivery
        )
        return WebhookAckResponse(
            status="event_ignored", delivery_id=x_github_delivery
        )

    # 2. A cold-started Vercel container has an empty /tmp database. Re-register
    #    the repository instead of dropping its webhook.
    should_process = await _ensure_monitored_repo(store, repo_full_name, branch)

    if not should_process:
        logger.info(
            "Ignoring webhook for paused/unmonitored repo %s (delivery %s)",
            repo_full_name,
            x_github_delivery,
        )
        return WebhookAckResponse(
            status="event_ignored", delivery_id=x_github_delivery
        )

    pipeline = getattr(request.app.state, "pipeline", None)
    run_inline = pipeline is not None

    response = await ingest_service.handle_webhook(
        delivery_id=x_github_delivery,
        event_type=x_github_event,
        payload=payload,
        store=store,
        queue=queue,
        # Vercel freezes the function after the response, so execute inline
        # instead of leaving the job in a queue that will never be drained.
        enqueue=not run_inline,
    )

    if run_inline and response.job is not None:
        try:
            await pipeline.process_webhook(response.job)
        except Exception:
            logger.exception(
                "Inline pipeline execution failed for %s",
                response.job.delivery_id,
            )

    return response


def _event_branch(event_type: str, payload: dict[str, Any]) -> str:
    """Return the head branch name for a push or pull_request event."""
    if event_type == "push":
        return (payload.get("ref") or "").removeprefix("refs/heads/")
    pr_data = payload.get("pull_request") or {}
    return ((pr_data.get("head") or {}).get("ref")) or ""


async def _ensure_monitored_repo(
    store: ContextStoreProtocol,
    repo_full_name: str,
    branch: str,
) -> bool:
    """Auto-register an unknown repo; return whether it should be processed."""
    if not repo_full_name or "/" not in repo_full_name:
        # Without a repository we cannot scope the run; let ingest decide.
        return True

    getter = getattr(store, "get_monitored_repo", None)
    upserter = getattr(store, "upsert_monitored_repo", None)
    if not callable(getter) or not callable(upserter):
        return True

    try:
        existing = await getter(repo_full_name)
        if existing is None:
            owner, name = repo_full_name.split("/", 1)
            await upserter(
                repo_full_name=repo_full_name,
                owner=owner,
                name=name,
                watch_branch=branch or "main",
                status="listening",
            )
            logger.info(
                "Auto-registered %s from webhook (cold-start recovery)",
                repo_full_name,
            )
            return True
        return existing.get("status", "listening") != "paused"
    except Exception:
        logger.warning(
            "Could not verify monitored repo %s; processing anyway",
            repo_full_name,
            exc_info=True,
        )
        return True


@router.get("/status/{delivery_id}")
async def get_delivery_status(delivery_id: str) -> dict:
    """Query status for a given delivery ID."""
    return {"delivery_id": delivery_id, "status": "pending"}
