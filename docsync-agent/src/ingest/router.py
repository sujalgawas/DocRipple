"""Ingest router — GitHub webhook endpoints."""

import logging

from fastapi import APIRouter, Depends, Request, HTTPException

from src.ingest.dependencies import verify_github_hmac, verify_unique_delivery
from src.ingest.exceptions import InvalidSignatureError, DuplicateDeliveryError
from src.ingest.schemas import GitHubPushPayload, WebhookAckResponse
from src.ingest.service import enqueue_webhook_job

router = APIRouter(tags=["ingest"])
logger = logging.getLogger(__name__)


@router.post("/webhooks/github", response_model=WebhookAckResponse)
async def github_webhook(
    request: Request,
    payload: GitHubPushPayload,
    delivery_id: str = Depends(verify_unique_delivery),
) -> WebhookAckResponse:
    """Receive GitHub push events, verify HMAC, deduplicate, enqueue."""
    await verify_github_hmac(request)
    job = await enqueue_webhook_job(payload, delivery_id)
    return WebhookAckResponse(status="accepted", delivery_id=delivery_id, job_id=job.job_id)


@router.get("/ingest/status/{delivery_id}")
async def ingest_status(delivery_id: str) -> dict:
    """Query processing status for a given delivery."""
    return {"delivery_id": delivery_id, "status": "pending"}