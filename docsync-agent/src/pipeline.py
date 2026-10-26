"""End-to-end pipeline runner for DocSync."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx

from src.contracts.schemas import PublishResult, WebhookJob

if TYPE_CHECKING:
    from src.contracts.protocols import (
        AnalyzerProtocol,
        ContextStoreProtocol,
        DriftEngineProtocol,
    )
    from src.orchestrator.schemas import OrchestratorProtocol

logger = logging.getLogger(__name__)


class GitHubRepoFetcher:
    """Fetches raw diffs, file blobs, and markdown documentation from GitHub."""

    def __init__(
        self,
        token: str = "",
        base_url: str = "https://api.github.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._client = client

    def _headers(self, accept: str = "application/vnd.github.v3+json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": "DocSync-Agent",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def fetch_diff(self, repo_full_name: str, base_sha: str, head_sha: str) -> str:
        """Fetch raw unified diff between base_sha and head_sha."""
        url = f"{self.base_url}/repos/{repo_full_name}/compare/{base_sha}...{head_sha}"
        headers = self._headers(accept="application/vnd.github.v3.diff")

        if self._client:
            res = await self._client.get(url, headers=headers)
        else:
            async with httpx.AsyncClient() as client:
                res = await client.get(url, headers=headers)

        res.raise_for_status()
        return res.text

    async def fetch_file_blobs(
        self,
        repo_full_name: str,
        base_sha: str,
        head_sha: str,
        file_paths: list[str],
    ) -> dict[str, tuple[str | None, str | None]]:
        """Fetch before/after file blobs for modified code files."""
        blobs: dict[str, tuple[str | None, str | None]] = {}

        async def _fetch_blob(client: httpx.AsyncClient, path: str, sha: str) -> str | None:
            url = f"{self.base_url}/repos/{repo_full_name}/contents/{path}?ref={sha}"
            headers = self._headers(accept="application/vnd.github.raw")
            try:
                res = await client.get(url, headers=headers)
                if res.status_code == 200:
                    return res.text
                return None
            except httpx.HTTPError:
                return None

        client = self._client or httpx.AsyncClient()
        try:
            for path in file_paths:
                before = await _fetch_blob(client, path, base_sha)
                after = await _fetch_blob(client, path, head_sha)
                blobs[path] = (before, after)
        finally:
            if not self._client:
                await client.aclose()

        return blobs

    async def fetch_docs(self, repo_full_name: str, head_sha: str) -> dict[str, str]:
        """Fetch all Markdown documentation files (README.md, docs/**/*.md) at head_sha."""
        docs: dict[str, str] = {}
        tree_url = f"{self.base_url}/repos/{repo_full_name}/git/trees/{head_sha}?recursive=1"
        headers = self._headers()

        client = self._client or httpx.AsyncClient()
        try:
            res = await client.get(tree_url, headers=headers)
            if res.status_code != 200:
                logger.warning(
                    "Failed to fetch git tree for %s: status %d",
                    repo_full_name,
                    res.status_code,
                )
                return docs

            tree_data = res.json().get("tree", [])
            md_files = [
                item["path"]
                for item in tree_data
                if item.get("type") == "blob"
                and (
                    item["path"].lower() == "readme.md"
                    or item["path"].startswith("docs/")
                    or item["path"].endswith(".md")
                )
            ]

            for path in md_files:
                content_url = f"{self.base_url}/repos/{repo_full_name}/contents/{path}?ref={head_sha}"
                c_res = await client.get(
                    content_url, headers=self._headers(accept="application/vnd.github.raw")
                )
                if c_res.status_code == 200:
                    docs[path] = c_res.text
        finally:
            if not self._client:
                await client.aclose()

        return docs


class DocSyncPipeline:
    """Executes the 5-stage documentation drift and update pipeline."""

    def __init__(
        self,
        analyzer: AnalyzerProtocol,
        drift_engine: DriftEngineProtocol,
        orchestrator: OrchestratorProtocol,
        context_store: ContextStoreProtocol,
        fetcher: GitHubRepoFetcher | None = None,
    ) -> None:
        self.analyzer = analyzer
        self.drift_engine = drift_engine
        self.orchestrator = orchestrator
        self.context_store = context_store
        self.fetcher = fetcher or GitHubRepoFetcher()

    async def execute_job(
        self,
        job: WebhookJob,
        raw_diff: str | None = None,
        file_blobs: dict[str, tuple[str | None, str | None]] | None = None,
        docs: dict[str, str] | None = None,
    ) -> PublishResult | None:
        """Run the end-to-end pipeline for a WebhookJob."""
        logger.info(
            "Executing pipeline for delivery %s (%s on %s)",
            job.delivery_id,
            job.event_type,
            job.repo_full_name,
        )

        # Step 1 (Fetch): fetch diff and docs from GitHub if not pre-supplied
        if raw_diff is None:
            try:
                raw_diff = await self.fetcher.fetch_diff(
                    job.repo_full_name, job.base_sha, job.head_sha
                )
            except Exception:
                logger.exception("Failed to fetch diff for %s", job.delivery_id)
                return None

        if docs is None:
            try:
                docs = await self.fetcher.fetch_docs(job.repo_full_name, job.head_sha)
            except Exception:
                logger.exception("Failed to fetch docs for %s", job.delivery_id)
                docs = {}

        # Step 2 (Analyze - No LLM)
        change_report = await self.analyzer.analyze(job, raw_diff, file_blobs)
        if not change_report.changed_symbols:
            logger.info(
                "Zero code symbols changed in delivery %s; early exit with 0 LLM tokens spent",
                job.delivery_id,
            )
            return None

        logger.info(
            "Analyzer extracted %d changed symbols for %s",
            len(change_report.changed_symbols),
            job.delivery_id,
        )

        # Step 3 (Drift - No LLM)
        symbol_names = [s.symbol_name for s in change_report.changed_symbols]
        stored_edges = await self.context_store.get_edges_for_symbols(
            job.repo_full_name, symbol_names
        )
        drift_report = await self.drift_engine.compute_drift(
            change_report, docs, stored_edges
        )
        if not drift_report.impacted_sections:
            logger.info(
                "Zero documentation drift detected for %s; early exit with 0 LLM tokens spent",
                job.delivery_id,
            )
            return None

        logger.info(
            "Drift engine detected %d impacted doc sections for %s",
            len(drift_report.impacted_sections),
            job.delivery_id,
        )

        # Step 4 & 5 (Orchestrate & Persist)
        publish_result = await self.orchestrator.run(drift_report, docs)
        logger.info(
            "Orchestrator completed for %s with verification_status=%s",
            job.delivery_id,
            publish_result.verification_status,
        )
        return publish_result


class BackgroundQueueWorker:
    """Asynchronous background worker pulling WebhookJob items from the queue."""

    def __init__(
        self,
        queue: asyncio.Queue[WebhookJob],
        pipeline: DocSyncPipeline,
    ) -> None:
        self.queue = queue
        self.pipeline = pipeline
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def run(self) -> None:
        """Main loop pulling jobs and executing them."""
        self._running = True
        logger.info("BackgroundQueueWorker started")
        while self._running:
            try:
                job = await self.queue.get()
            except asyncio.CancelledError:
                break

            try:
                logger.info("BackgroundQueueWorker received job %s", job.delivery_id)
                await self.pipeline.execute_job(job)
            except Exception:
                logger.exception(
                    "Error processing job %s in background worker",
                    getattr(job, "delivery_id", "unknown"),
                )
            finally:
                self.queue.task_done()
        logger.info("BackgroundQueueWorker stopped")

    def start(self) -> asyncio.Task[None]:
        """Start the background worker task."""
        self._task = asyncio.create_task(self.run())
        return self._task

    async def stop(self) -> None:
        """Gracefully stop and await the background worker."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
