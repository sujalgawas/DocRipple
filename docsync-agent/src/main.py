"""FastAPI application entry point — lifespan, router mounting, and observability routes."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from pydantic import BaseModel, Field

from src.analyzer.service import ChangeAnalyzerService
from src.config import settings
from src.context_store.sqlite_store import SqliteContextStore
from src.contracts.schemas import ChangeReport, DriftReport, PublishResult, WebhookJob
from src.drift.service import DriftEngineService
from src.ingest.router import router as ingest_router
from src.onboarding.router import router as onboarding_router
from src.onboarding.service import OnboardingService
from src.orchestrator.config import OrchestratorConfig
from src.orchestrator.service import OrchestratorService
from src.pipeline import BackgroundQueueWorker, DocSyncPipeline, GitHubRepoFetcher
from src.web_api.github_service import GitHubService, GitHubServicePublisher
from src.web_api.router import router as web_api_router

logger = logging.getLogger("docsync")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize resources, background workers, and teardown on shutdown."""
    logging.basicConfig(level=settings.LOG_LEVEL)
    logger.info("Starting DocSync application...")

    # 1. Initialize ContextStore
    store = SqliteContextStore(settings.SQLITE_DB_PATH)
    await store.initialize()

    # 2. Shared Webhook Queue
    queue: asyncio.Queue[WebhookJob] = asyncio.Queue()

    # 3. Domain module services
    analyzer = ChangeAnalyzerService()
    drift_engine = DriftEngineService()
    onboarding_service = OnboardingService(context_store=store)
    orchestrator_config = OrchestratorConfig(
        llm_base_url=settings.LLM_BASE_URL,
        llm_api_key=settings.LLM_API_KEY,
        llm_model=settings.LLM_MODEL,
        github_token=settings.GITHUB_TOKEN,
        checkpoint_db_path=settings.CHECKPOINT_DB_PATH,
        max_retries=settings.MAX_RETRIES,
    )
    github_service = GitHubService(token=settings.GITHUB_TOKEN)
    orchestrator = OrchestratorService(
        context_store=store,
        config=orchestrator_config,
        github_publisher=GitHubServicePublisher(github_service),
    )

    fetcher = GitHubRepoFetcher(token=settings.GITHUB_TOKEN)
    pipeline = DocSyncPipeline(
        analyzer=analyzer,
        drift_engine=drift_engine,
        orchestrator=orchestrator,
        context_store=store,
        fetcher=fetcher,
        github_service=github_service,
    )

    worker = BackgroundQueueWorker(queue=queue, pipeline=pipeline)
    worker.start()

    # Attach to app.state
    app.state.webhook_queue = queue
    app.state.context_store = store
    app.state.onboarding_service = onboarding_service
    app.state.pipeline = pipeline
    app.state.worker = worker
    app.state.settings = settings
    app.state.github_service = github_service
    app.state.github_oauth_token = ""

    logger.info("DocSync application startup complete")
    try:
        yield
    finally:
        logger.info("Shutting down DocSync application...")
        await worker.stop()
        await store.close()
        logger.info("DocSync shutdown complete")


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="DocSync Agent",
    description="Autonomous Documentation Drift Detection & Remediation",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Stage 1 webhook router, Stage 0 onboarding router, and web API bridge
app.include_router(ingest_router)
app.include_router(onboarding_router)
app.include_router(web_api_router)


# ── Observability & Demo Endpoints ──────────────────────────────────────────


@app.get("/health", tags=["system"])
async def health(request: Request) -> dict[str, Any]:
    """Health check returning queue size and status."""
    queue = getattr(request.app.state, "webhook_queue", None)
    qsize = queue.qsize() if queue is not None else 0
    return {"status": "ok", "queue_size": qsize}


@app.get(
    "/api/v1/runs/{delivery_id}",
    response_model=PublishResult,
    tags=["runs"],
)
async def get_run_status(delivery_id: str, request: Request) -> PublishResult:
    """Retrieve the PublishResult for a specific delivery ID."""
    store: SqliteContextStore = request.app.state.context_store
    result = await store.get_run_result(delivery_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found for delivery_id: {delivery_id}",
        )
    return result


class DemoRunRequest(BaseModel):
    """Payload for executing a live demo of the pipeline."""

    delivery_id: str = Field(default_factory=lambda: f"demo-{uuid4().hex[:8]}")
    repo_full_name: str = "demo/repo"
    base_sha: str = "0000000000000000000000000000000000000001"
    head_sha: str = "0000000000000000000000000000000000000002"
    ref: str = "refs/heads/main"
    pr_number: int | None = None
    raw_diff: str
    file_blobs: dict[str, tuple[str | None, str | None]] | None = None
    docs: dict[str, str] = Field(default_factory=dict)


class DemoRunResponse(BaseModel):
    """Result of running the demo pipeline."""

    delivery_id: str
    change_report: ChangeReport
    drift_report: DriftReport
    publish_result: PublishResult | None


@app.post(
    "/api/v1/demo/run",
    response_model=DemoRunResponse,
    tags=["demo"],
)
async def demo_run(req: DemoRunRequest, request: Request) -> DemoRunResponse:
    """Run Stage 2 -> Stage 3 -> Stage 4 -> Stage 5 synchronously for demonstrations."""
    pipeline: DocSyncPipeline = request.app.state.pipeline

    job = WebhookJob(
        delivery_id=req.delivery_id,
        event_type="push",
        repo_full_name=req.repo_full_name,
        base_sha=req.base_sha,
        head_sha=req.head_sha,
        ref=req.ref,
        pr_number=req.pr_number,
        received_at=datetime.now(UTC),
    )

    # 1. Analyze
    change_report = await pipeline.analyzer.analyze(
        job, req.raw_diff, req.file_blobs
    )

    # 2. Drift
    symbol_names = [s.symbol_name for s in change_report.changed_symbols]
    stored_edges = await pipeline.context_store.get_edges_for_symbols(
        job.repo_full_name, symbol_names
    )
    drift_report = await pipeline.drift_engine.compute_drift(
        change_report, req.docs, stored_edges
    )

    # 3. Orchestrate if drift detected
    publish_result = None
    if drift_report.impacted_sections:
        publish_result = await pipeline.orchestrator.run(
            drift_report, req.docs
        )

    return DemoRunResponse(
        delivery_id=req.delivery_id,
        change_report=change_report,
        drift_report=drift_report,
        publish_result=publish_result,
    )