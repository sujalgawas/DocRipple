"""Unit tests for the Ingest module."""

import asyncio
import hashlib
import hmac
import json

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from src.contracts.schemas import WebhookJob
from src.ingest.dependencies import get_context_store, get_job_queue
from src.ingest.router import router


class MockContextStore:
    """In-memory mock ContextStore implementation for testing."""

    def __init__(self) -> None:
        self.recorded_deliveries: set[str] = set()

    async def check_and_record_delivery(self, delivery_id: str, repo_full_name: str) -> bool:
        if delivery_id in self.recorded_deliveries:
            return False
        self.recorded_deliveries.add(delivery_id)
        return True

    async def get_edges_for_symbols(
        self, repo_full_name: str, symbol_names: list[str]
    ) -> list:
        return []


def sign_payload(body: bytes, secret: str = "dev-secret") -> str:
    """Compute HMAC-SHA256 signature for test payload bytes."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
def queue() -> asyncio.Queue[WebhookJob]:
    return asyncio.Queue()


@pytest.fixture
def store() -> MockContextStore:
    return MockContextStore()


@pytest.fixture
async def client(queue: asyncio.Queue[WebhookJob], store: MockContextStore):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_job_queue] = lambda: queue
    app.dependency_overrides[get_context_store] = lambda: store

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.mark.asyncio
async def test_valid_push_event_enqueued(client: httpx.AsyncClient, queue: asyncio.Queue[WebhookJob]):
    """1. Valid push event with valid HMAC signature -> 202 'enqueued' and job in queue."""
    payload = {
        "ref": "refs/heads/main",
        "before": "1111111111111111111111111111111111111111",
        "after": "2222222222222222222222222222222222222222",
        "repository": {"full_name": "sujalgawas/DocRipple"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    signature = sign_payload(raw_body)

    response = await client.post(
        "/api/v1/webhooks/github",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Delivery": "delivery-push-001",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": signature,
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "enqueued"
    assert data["delivery_id"] == "delivery-push-001"
    assert data["job"] is not None
    assert data["job"]["event_type"] == "push"
    assert data["job"]["repo_full_name"] == "sujalgawas/DocRipple"
    assert data["job"]["head_sha"] == "2222222222222222222222222222222222222222"
    assert data["job"]["pr_number"] is None

    # Verify queue received the job
    assert queue.qsize() == 1
    enqueued_job = await queue.get()
    assert enqueued_job.delivery_id == "delivery-push-001"
    assert enqueued_job.head_sha == "2222222222222222222222222222222222222222"


@pytest.mark.asyncio
async def test_valid_pull_request_synchronize_enqueued(
    client: httpx.AsyncClient, queue: asyncio.Queue[WebhookJob]
):
    """2. Valid pull_request (synchronize) event -> 202 'enqueued' with pr_number populated."""
    payload = {
        "action": "synchronize",
        "number": 88,
        "pull_request": {
            "base": {"sha": "base-sha-123", "ref": "main"},
            "head": {"sha": "head-sha-456", "ref": "feature/docs"},
        },
        "repository": {"full_name": "sujalgawas/DocRipple"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    signature = sign_payload(raw_body)

    response = await client.post(
        "/api/v1/webhooks/github",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Delivery": "delivery-pr-002",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": signature,
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "enqueued"
    assert data["delivery_id"] == "delivery-pr-002"
    assert data["job"] is not None
    assert data["job"]["event_type"] == "pull_request"
    assert data["job"]["pr_number"] == 88
    assert data["job"]["base_sha"] == "base-sha-123"
    assert data["job"]["head_sha"] == "head-sha-456"
    assert data["job"]["ref"] == "feature/docs"

    assert queue.qsize() == 1
    enqueued_job = await queue.get()
    assert enqueued_job.pr_number == 88


@pytest.mark.asyncio
async def test_invalid_signature_unauthorized(
    client: httpx.AsyncClient, queue: asyncio.Queue[WebhookJob]
):
    """3. Invalid X-Hub-Signature-256 -> 401 Unauthorized, queue remains empty."""
    payload = {"repository": {"full_name": "sujalgawas/DocRipple"}}
    raw_body = json.dumps(payload).encode("utf-8")

    response = await client.post(
        "/api/v1/webhooks/github",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Delivery": "delivery-invalid-sig",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": "sha256=0000000000000000000000000000000000000000000000000000000000000000",
        },
    )

    assert response.status_code == 401
    assert queue.empty() is True


@pytest.mark.asyncio
async def test_duplicate_delivery_ignored(
    client: httpx.AsyncClient, queue: asyncio.Queue[WebhookJob]
):
    """4. Duplicate X-GitHub-Delivery ID -> returns 202 'duplicate_ignored', queue not doubled."""
    payload = {
        "ref": "refs/heads/main",
        "before": "1111",
        "after": "2222",
        "repository": {"full_name": "sujalgawas/DocRipple"},
    }
    raw_body = json.dumps(payload).encode("utf-8")
    signature = sign_payload(raw_body)
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Delivery": "delivery-dup-004",
        "X-GitHub-Event": "push",
        "X-Hub-Signature-256": signature,
    }

    # First delivery: enqueued
    res1 = await client.post("/api/v1/webhooks/github", content=raw_body, headers=headers)
    assert res1.status_code == 202
    assert res1.json()["status"] == "enqueued"
    assert queue.qsize() == 1

    # Second delivery with identical delivery ID: duplicate_ignored
    res2 = await client.post("/api/v1/webhooks/github", content=raw_body, headers=headers)
    assert res2.status_code == 202
    data2 = res2.json()
    assert data2["status"] == "duplicate_ignored"
    assert data2["delivery_id"] == "delivery-dup-004"
    assert data2["job"] is None

    # Queue still has only the initial job
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_ignored_events(
    client: httpx.AsyncClient, queue: asyncio.Queue[WebhookJob]
):
    """5. Ignored events (ping, branch deletion 0000..., PR closed) -> 202 'event_ignored'."""
    # 5a. Ping event
    ping_payload = {"zen": "Keep it logically awesome."}
    raw_ping = json.dumps(ping_payload).encode("utf-8")
    res_ping = await client.post(
        "/api/v1/webhooks/github",
        content=raw_ping,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Delivery": "delivery-ping",
            "X-GitHub-Event": "ping",
            "X-Hub-Signature-256": sign_payload(raw_ping),
        },
    )
    assert res_ping.status_code == 202
    assert res_ping.json()["status"] == "event_ignored"
    assert queue.empty() is True

    # 5b. Branch deletion (zero commit push)
    del_payload = {
        "ref": "refs/heads/feature-old",
        "before": "abcdef1234567890",
        "after": "0000000000000000000000000000000000000000",
        "repository": {"full_name": "sujalgawas/DocRipple"},
    }
    raw_del = json.dumps(del_payload).encode("utf-8")
    res_del = await client.post(
        "/api/v1/webhooks/github",
        content=raw_del,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Delivery": "delivery-branch-del",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sign_payload(raw_del),
        },
    )
    assert res_del.status_code == 202
    assert res_del.json()["status"] == "event_ignored"
    assert queue.empty() is True

    # 5c. PR event with action other than opened/synchronize (e.g. closed)
    closed_payload = {
        "action": "closed",
        "number": 99,
        "pull_request": {
            "base": {"sha": "base", "ref": "main"},
            "head": {"sha": "head", "ref": "feat"},
        },
        "repository": {"full_name": "sujalgawas/DocRipple"},
    }
    raw_closed = json.dumps(closed_payload).encode("utf-8")
    res_closed = await client.post(
        "/api/v1/webhooks/github",
        content=raw_closed,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Delivery": "delivery-pr-closed",
            "X-GitHub-Event": "pull_request",
            "X-Hub-Signature-256": sign_payload(raw_closed),
        },
    )
    assert res_closed.status_code == 202
    assert res_closed.json()["status"] == "event_ignored"
    assert queue.empty() is True
