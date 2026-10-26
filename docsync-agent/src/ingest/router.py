"""Ingest router — GitHub webhook endpoints."""

import asyncio
import json
import logging
from typing import Annotated

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
    """Receive GitHub push and pull_request events, verify HMAC, deduplicate, and enqueue."""
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except Exception as exc:
        logger.warning("Failed to parse JSON webhook payload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid JSON payload: {exc}",
        ) from exc

    response = await ingest_service.handle_webhook(
        delivery_id=x_github_delivery,
        event_type=x_github_event,
        payload=payload,
        store=store,
        queue=queue,
    )

    # On Vercel the function freezes as soon as the response is returned, so a
    # queued job would never be processed. Run it inside this request instead.
    if getattr(request.app.state, "inline_execution", False):
        await _drain_queue_inline(request, queue)

    return response


async def _drain_queue_inline(
    request: Request,
    queue: asyncio.Queue[WebhookJob],
) -> None:
    """Execute every queued job synchronously within the current request."""
    pipeline = getattr(request.app.state, "pipeline", None)
    while not queue.empty():
        job = queue.get_nowait()
        try:
            if pipeline is not None:
                await pipeline.execute_job(job)
        except Exception:
            logger.exception(
                "Inline pipeline execution failed for %s",
                getattr(job, "delivery_id", "unknown"),
            )
        finally:
            queue.task_done()


@router.get("/status/{delivery_id}")
async def get_delivery_status(delivery_id: str) -> dict:
    """Query status for a given delivery ID."""
    return {"delivery_id": delivery_id, "status": "pending"}