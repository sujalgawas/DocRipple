"""FastAPI application entry point — lifespan, router mounting, and observability routes."""

from __future__ import annotations

import os

# Vercel runs the app from the read-only /var/task filesystem. This must run
# before any local import, because src.config resolves these values at import
# time. Redirect HOME so libraries writing cache/model files land on the
# writable /tmp mount, and point SQLite at /tmp for the same reason.
if os.getenv("VERCEL"):
    os.environ.setdefault("HOME", "/tmp")
    os.environ.setdefault("SQLITE_DB_PATH", "/tmp/docsync_context.db")
    os.environ.setdefault("CHECKPOINT_DB_PATH", "/tmp/docsync_checkpoints.db")

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.analyzer.service import ChangeAnalyzerService
from src.config import settings
from src.context_store.sqlite_store import SqliteContextStore
from src.contracts.schemas import (
    ChangeReport,
    DocStyleSkill,
    DriftReport,
    MemoryEdge,
    MemoryNode,
    PublishResult,
    RepoMemoryMap,
    WebhookJob,
)
from src.drift.service import DriftEngineService
from src.ingest.router import legacy_router as ingest_legacy_router
from src.ingest.router import router as ingest_router
from src.onboarding.router import router as onboarding_router
from src.onboarding.service import OnboardingService
from src.orchestrator.config import OrchestratorConfig
from src.orchestrator.service import OrchestratorService
from src.pipeline import (
    BackgroundQueueWorker,
    DocSyncPipeline,
    GitHubRepoFetcher,
)
from src.web_api.github_service import GitHubService, GitHubServicePublisher
from src.web_api.router import router as web_api_router

logger = logging.getLogger("docsync")

SEED_REPO_FULL_NAME = "sujalgawas/DocRipple"

# Origins that must always work, regardless of how the env vars are configured.
# A trailing slash in FRONTEND_URL would otherwise make every credentialed
# request fail the CORS check, which the browser reports as a network error.
_CANONICAL_ORIGINS = (
    "https://docripple.vercel.app",
    "https://docsync-agent-lyart.vercel.app",
)

CORS_ORIGIN_REGEX = r"^https://.*\.vercel\.app$|^http://localhost:\d+$"


def _cors_origins() -> list[str]:
    """Return the deduplicated CORS allow-list from environment settings."""
    origins: list[str] = []
    for raw_origin in (
        settings.FRONTEND_URL,
        *_CANONICAL_ORIGINS,
        *settings.ALLOWED_ORIGINS.split(","),
    ):
        origin = raw_origin.strip().rstrip("/")
        if origin and origin not in origins:
            origins.append(origin)
    return origins


def _seed_style_skill() -> DocStyleSkill:
    """Return the default Stage 0 writing skill for the seeded repository."""
    return DocStyleSkill(
        repo_full_name=SEED_REPO_FULL_NAME,
        tone_and_voice=(
            "Direct, practical, developer-first prose. Lead with what changed "
            "and why it matters, then show a short runnable example."
        ),
        heading_conventions=[
            "Use sentence-case H2/H3 headings",
            "Keep one topic per section",
            "Prefer short paragraphs and bullet lists for options",
        ],
        code_block_rules=[
            "Fence every snippet with a language hint",
            "Keep examples copy-paste ready",
            "Show expected output only when it adds clarity",
        ],
        formatting_patterns=[
            "Use inline code for symbols, flags, env vars, and paths",
            "Link the first mention of external services",
            "End how-to sections with a verification step",
        ],
        skill_markdown=(
            "# SKILL: DocRipple\n\n"
            "## Voice\n\n"
            "- Write for developers who want the shortest path to a working result.\n"
            "- Prefer concrete verbs and active voice.\n"
            "- Explain the why before the how, but keep it brief.\n\n"
            "## Structure\n\n"
            "- Use sentence-case H2 and H3 headings.\n"
            "- Keep one topic per section and lead with the outcome.\n"
            "- Use bullet lists for independent options or prerequisites.\n\n"
            "## Code and commands\n\n"
            "- Always add a language hint to fenced code blocks.\n"
            "- Keep snippets runnable and show the verification step.\n"
            "- Use inline code for symbols, flags, environment variables, and paths.\n"
        ),
        generated_at=datetime.now(UTC),
    )


def _seed_memory_map() -> RepoMemoryMap:
    """Return a small Stage 0 memory graph so the dashboard is populated."""
    return RepoMemoryMap(
        repo_full_name=SEED_REPO_FULL_NAME,
        nodes=[
            MemoryNode(
                node_id="module:src/main.py",
                repo_full_name=SEED_REPO_FULL_NAME,
                node_type="module",
                name="main",
                path="src/main.py",
                summary=(
                    "FastAPI entry point with lifespan startup, CORS, health "
                    "checks, and the demo pipeline route."
                ),
            ),
            MemoryNode(
                node_id="module:src/web_api/router.py",
                repo_full_name=SEED_REPO_FULL_NAME,
                node_type="module",
                name="web_api.router",
                path="src/web_api/router.py",
                summary=(
                    "Dashboard API for authentication, repositories, activity, "
                    "manual triggers, and settings."
                ),
            ),
            MemoryNode(
                node_id="symbol:src/main.py::seed_default_repository",
                repo_full_name=SEED_REPO_FULL_NAME,
                node_type="symbol",
                name="seed_default_repository",
                path="src/main.py",
                summary=(
                    "Seeds the demo workspace when a fresh container starts "
                    "with an empty SQLite database."
                ),
            ),
            MemoryNode(
                node_id="doc_section:README.md::getting-started",
                repo_full_name=SEED_REPO_FULL_NAME,
                node_type="doc_section",
                name="getting-started",
                path="README.md",
                summary="Local setup, environment variables, and deployment overview.",
            ),
        ],
        edges=[
            MemoryEdge(
                repo_full_name=SEED_REPO_FULL_NAME,
                source_id="module:src/main.py",
                target_id="symbol:src/main.py::seed_default_repository",
                relation="CONTAINS",
            ),
            MemoryEdge(
                repo_full_name=SEED_REPO_FULL_NAME,
                source_id="module:src/main.py",
                target_id="module:src/web_api/router.py",
                relation="IMPORTS",
            ),
            MemoryEdge(
                repo_full_name=SEED_REPO_FULL_NAME,
                source_id="symbol:src/main.py::seed_default_repository",
                target_id="doc_section:README.md::getting-started",
                relation="DOCUMENTED_IN",
            ),
        ],
        updated_at=datetime.now(UTC),
    )


async def seed_default_repository(store: SqliteContextStore) -> bool:
    """Populate a fresh store with the DocRipple demo workspace.

    Returns ``True`` when seeding ran and ``False`` when a monitored
    repository already exists. All writes are idempotent, so a retry is safe.
    """
    if await store.list_monitored_repos():
        return False

    now = datetime.now(UTC)
    owner, name = SEED_REPO_FULL_NAME.split("/", 1)

    await store.upsert_monitored_repo(
        repo_full_name=SEED_REPO_FULL_NAME,
        owner=owner,
        name=name,
        watch_branch="main",
        doc_paths=["README.md", "docs/**/*.md"],
        drift_action="open_pr",
        status="listening",
        language="Python",
        last_pushed_at=now.isoformat(),
    )
    await store.save_style_skill(_seed_style_skill())
    await store.save_memory_map(_seed_memory_map())

    seed_runs = [
        {
            "delivery_id": "seed-docripple-0003",
            "commit_sha": "c72a5f9d1e8b4a6c0f2d3e5a7b9c1d3e5f7a9b1c",
            "commit_message": "docs: document Render deployment and health checks",
            "author": "sujalgawas",
            "llm_calls": 2,
            "status": "pr_open",
            "pr_number": 13,
            "pr_url": f"https://github.com/{SEED_REPO_FULL_NAME}/pull/13",
            "diff_preview": {
                "file_path": "src/main.py",
                "deleted_lines": ["-@app.get(\"/health\")"],
                "added_lines": [
                    "+@app.api_route(\"/health\", methods=[\"GET\", \"HEAD\"])",
                ],
                "context": "@@ -129,7 +129,7 @@",
                "changed_symbols": [
                    {
                        "file_path": "src/main.py",
                        "symbol_name": "health",
                        "symbol_kind": "route",
                        "change_class": "api_surface",
                        "change_type": "modified",
                        "old_signature": "GET /health",
                        "new_signature": "GET, HEAD /health",
                    }
                ],
                "impacted_sections": [
                    {
                        "doc_path": "README.md",
                        "heading": "Deployment",
                        "anchor": None,
                        "matched_symbols": ["health"],
                        "match_method": "exact_anchor",
                        "confidence_score": 0.88,
                    }
                ],
            },
        },
        {
            "delivery_id": "seed-docripple-0002",
            "commit_sha": "8b1d4e0f2a6c9b7d5e3f1a0c8b6d4e2f0a9c7b5d",
            "commit_message": "refactor: simplify documentation drift matching internals",
            "author": "sujalgawas",
            "llm_calls": 0,
            "status": "no_drift",
            "pr_number": None,
            "pr_url": None,
            "diff_preview": {
                "file_path": "src/drift/embed_fallback.py",
                "deleted_lines": ["-    return np.clip(scores, 0.0, 1.0)"],
                "added_lines": ["+    return np.clip(similarities, 0.0, 1.0)"],
                "context": "@@ -420,7 +420,7 @@",
                "changed_symbols": [
                    {
                        "file_path": "src/drift/embed_fallback.py",
                        "symbol_name": "_cosine_similarities",
                        "symbol_kind": "function",
                        "change_class": "behavior",
                        "change_type": "modified",
                        "old_signature": None,
                        "new_signature": None,
                    }
                ],
                "impacted_sections": [],
            },
        },
        {
            "delivery_id": "seed-docripple-0001",
            "commit_sha": "3f9c2a1d4b5e6f708192a3b4c5d6e7f8091a2b3c",
            "commit_message": "feat(api): add repository sync trigger endpoint",
            "author": "sujalgawas",
            "llm_calls": 3,
            "status": "merged",
            "pr_number": 12,
            "pr_url": f"https://github.com/{SEED_REPO_FULL_NAME}/pull/12",
            "diff_preview": {
                "file_path": "src/web_api/router.py",
                "deleted_lines": [],
                "added_lines": [
                    "+@router.post(\"/repos/{owner}/{repo}/trigger\")",
                    "+async def trigger_repo(...):",
                ],
                "context": "@@ -463,6 +463,8 @@",
                "changed_symbols": [
                    {
                        "file_path": "src/web_api/router.py",
                        "symbol_name": "trigger_repo",
                        "symbol_kind": "route",
                        "change_class": "api_surface",
                        "change_type": "added",
                        "old_signature": None,
                        "new_signature": "POST /api/v1/repos/{owner}/{repo}/trigger",
                    }
                ],
                "impacted_sections": [
                    {
                        "doc_path": "README.md",
                        "heading": "API Reference",
                        "anchor": None,
                        "matched_symbols": ["trigger_repo"],
                        "match_method": "graph_edge",
                        "confidence_score": 0.92,
                    }
                ],
            },
        },
    ]

    # Insert oldest first so the newest run (pr_open) sorts to the top.
    for run in reversed(seed_runs):
        await store.create_activity_run(
            run["delivery_id"],
            SEED_REPO_FULL_NAME,
            commit_sha=run["commit_sha"],
            commit_message=run["commit_message"],
            author=run["author"],
            status=run["status"],
            llm_calls=run["llm_calls"],
            diff_preview=run["diff_preview"],
        )
        if run["pr_number"] is not None:
            await store.update_activity_run(
                run["delivery_id"],
                pr_number=run["pr_number"],
                pr_url=run["pr_url"],
            )

    logger.info("Seeded demo workspace for %s", SEED_REPO_FULL_NAME)
    return True


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialize resources, background workers, and teardown on shutdown."""
    logging.basicConfig(level=settings.LOG_LEVEL)
    logger.info("Starting DocSync application...")

    store: SqliteContextStore | None = None
    worker: BackgroundQueueWorker | None = None

    try:
        # 1. Initialize ContextStore
        store = SqliteContextStore(settings.SQLITE_DB_PATH)
        await store.initialize()

        # 2. Seed a fresh deployment so the dashboard is never empty. Render's
        #    free tier resets /tmp on each redeploy, so this runs on cold boot.
        try:
            await seed_default_repository(store)
        except Exception:
            logger.exception("Could not seed the demo workspace; continuing startup")

        # 3. Shared Webhook Queue
        queue: asyncio.Queue[WebhookJob] = asyncio.Queue()

        # 4. Domain module services
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

        # Vercel Functions freeze background tasks once the response is returned,
        # so a long-lived queue worker would strand work forever. In inline mode
        # the request handlers execute the job directly instead of starting it.
        execution_mode = (settings.EXECUTION_MODE or "inline").strip().lower()
        inline_execution = bool(os.getenv("VERCEL")) and execution_mode != "queue"

        worker = BackgroundQueueWorker(queue=queue, pipeline=pipeline)
        if not inline_execution:
            worker.start()

        # Attach to app.state
        app.state.queue = queue
        app.state.webhook_queue = queue
        app.state.context_store = store
        app.state.onboarding_service = onboarding_service
        app.state.pipeline = pipeline
        app.state.worker = worker
        app.state.execution_mode = execution_mode
        app.state.inline_execution = inline_execution
        app.state.settings = settings
        app.state.github_service = github_service
        app.state.github_oauth_token = ""

        logger.info("DocSync application startup complete")
    except Exception as exc:
        logger.exception("DocSync startup failed; falling back to memory store: %s", exc)
        try:
            if store is not None:
                try:
                    await store.close()
                except Exception:
                    pass
            store = SqliteContextStore(":memory:")
            await store.initialize()
            try:
                await seed_default_repository(store)
            except Exception:
                pass
            queue = asyncio.Queue()
            analyzer = ChangeAnalyzerService()
            drift_engine = DriftEngineService()
            onboarding_service = OnboardingService(context_store=store)
            orchestrator_config = OrchestratorConfig(
                llm_base_url=settings.LLM_BASE_URL,
                llm_api_key=settings.LLM_API_KEY,
                llm_model=settings.LLM_MODEL,
                github_token=settings.GITHUB_TOKEN,
                checkpoint_db_path=":memory:",
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
            app.state.queue = queue
            app.state.webhook_queue = queue
            app.state.context_store = store
            app.state.onboarding_service = onboarding_service
            app.state.pipeline = pipeline
            app.state.worker = worker
            app.state.execution_mode = "inline"
            app.state.inline_execution = True
            app.state.settings = settings
            app.state.github_service = github_service
            app.state.github_oauth_token = ""
            logger.info("DocSync fallback startup complete")
        except Exception:
            logger.exception("Fallback initialization also encountered error; continuing to yield")

    try:
        yield
    finally:
        logger.info("Shutting down DocSync application...")
        if worker is not None:
            try:
                await worker.stop()
            except Exception:
                pass
        if store is not None:
            try:
                await store.close()
            except Exception:
                pass
        logger.info("DocSync shutdown complete")


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="DocSync Agent",
    description="Autonomous Documentation Drift Detection & Remediation",
    version="0.1.0",
    lifespan=lifespan,
)

# Starlette applies user middleware outermost-first, and add_middleware prepends,
# so this stays the outermost layer: CORS headers are attached even when a route
# raises before reaching the router.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_origin_regex=CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    """Return a CORS-readable JSON error instead of an opaque network failure.

    Unhandled exceptions bypass CORSMiddleware, so without an explicit header the
    browser reports a CORS/network error and the dashboard shows
    "Backend not reachable" even though the server answered.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "path": request.url.path},
        headers={"Access-Control-Allow-Origin": "*"},
    )

# Mount Stage 1 webhook router, Stage 0 onboarding router, and web API bridge
app.include_router(ingest_router)
app.include_router(ingest_legacy_router)
app.include_router(onboarding_router)
app.include_router(web_api_router)


# ── Observability & Demo Endpoints ──────────────────────────────────────────


@app.api_route("/", methods=["GET", "HEAD"], tags=["system"])
@app.api_route("/health", methods=["GET", "HEAD"], tags=["system"])
@app.api_route("/api/v1/health", methods=["GET", "HEAD"], tags=["system"])
async def health() -> dict[str, str]:
    """Lightweight liveness probe used by Render, Vercel, and keep-alive pingers."""
    return {"status": "ok", "service": "docripple-api"}


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