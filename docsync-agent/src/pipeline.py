"""End-to-end pipeline runner for DocSync."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import httpx

from src.contracts.schemas import (
    ChangeReport,
    DriftReport,
    PublishResult,
    WebhookJob,
)
from src.web_api.github_service import github_publish_context

if TYPE_CHECKING:
    from src.contracts.protocols import (
        AnalyzerProtocol,
        ContextStoreProtocol,
        DriftEngineProtocol,
        OrchestratorProtocol,
    )
    from src.web_api.github_service import GitHubService

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
    """Executes the Stage 1–5 documentation drift and update pipeline.

    Every job is mirrored into ``activity_runs`` so the web dashboard reflects
    real status transitions (``running`` → ``no_drift`` / ``pr_open`` /
    ``failed``). Stage 0 (onboarding) runs earlier when a repository is
    registered and populates the skill/memory consumed by the orchestrator.
    """

    def __init__(
        self,
        analyzer: AnalyzerProtocol,
        drift_engine: DriftEngineProtocol,
        orchestrator: OrchestratorProtocol,
        context_store: ContextStoreProtocol,
        fetcher: GitHubRepoFetcher | None = None,
        github_service: GitHubService | None = None,
    ) -> None:
        self.analyzer = analyzer
        self.drift_engine = drift_engine
        self.orchestrator = orchestrator
        self.context_store = context_store
        self.fetcher = fetcher or GitHubRepoFetcher()
        self.github_service = github_service

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

        await self._start_activity(job)
        commit_message = job.commit_message
        author = job.author
        llm_calls = 0

        # Webhook/manual runs may start without a prior HTTP request syncing the
        # fetcher token; keep it aligned with the OAuth/PAT session token.
        if self.github_service is not None and getattr(
            self.github_service, "token", ""
        ):
            self.fetcher.token = self.github_service.token

        try:
            # Step 1 (Fetch): fetch diff and docs from GitHub if not pre-supplied
            if raw_diff is None:
                if self.github_service is not None:
                    try:
                        comparison = (
                            await self.github_service.fetch_commit_comparison(
                                job.repo_full_name, job.base_sha, job.head_sha
                            )
                        )
                        raw_diff = comparison.get("raw_diff", "")
                        file_blobs = comparison.get("file_blobs") or {}
                        commit_message = (
                            commit_message
                            or comparison.get("commit_message", "")
                        )
                        author = author or comparison.get("author_login", "")
                        if commit_message or author:
                            await self._update_activity(
                                job.delivery_id,
                                commit_message=commit_message or None,
                                author=author or None,
                            )
                    except Exception as exc:
                        logger.exception(
                            "Failed to fetch comparison for %s", job.delivery_id
                        )
                        await self._fail_activity(job.delivery_id, exc)
                        return None
                else:
                    try:
                        raw_diff = await self.fetcher.fetch_diff(
                            job.repo_full_name, job.base_sha, job.head_sha
                        )
                    except Exception as exc:
                        logger.exception(
                            "Failed to fetch diff for %s", job.delivery_id
                        )
                        await self._fail_activity(job.delivery_id, exc)
                        return None

            if docs is None:
                try:
                    docs = await self.fetcher.fetch_docs(
                        job.repo_full_name, job.head_sha
                    )
                except Exception:
                    logger.exception("Failed to fetch docs for %s", job.delivery_id)
                    docs = {}

            # Step 2 (Analyze - No LLM)
            change_report = await self.analyzer.analyze(
                job, raw_diff or "", file_blobs
            )
            if await self._should_skip_internal(change_report):
                logger.info(
                    "Zero public code symbols changed in delivery %s; "
                    "early exit with 0 LLM tokens spent",
                    job.delivery_id,
                )
                await self._no_drift_activity(
                    job.delivery_id,
                    raw_diff or "",
                    change_report,
                    None,
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
                    "Zero documentation drift detected for %s; "
                    "early exit with 0 LLM tokens spent",
                    job.delivery_id,
                )
                await self._no_drift_activity(
                    job.delivery_id,
                    raw_diff or "",
                    change_report,
                    drift_report,
                )
                return None

            logger.info(
                "Drift engine detected %d impacted doc sections for %s",
                len(drift_report.impacted_sections),
                job.delivery_id,
            )

            # Step 4 & 5 (Orchestrate & Persist)
            # PR events carry the head ref in ``ref``; docs PRs must target the
            # PR base branch. Push/manual jobs fall back to their own branch.
            branch = job.base_ref or _branch_from_ref(job.ref)
            with github_publish_context(head_sha=job.head_sha, base_branch=branch):
                try:
                    publish_result = await self.orchestrator.run(drift_report, docs)
                finally:
                    llm_calls = int(
                        getattr(self.orchestrator, "last_llm_calls", 0)
                    )

            logger.info(
                "Orchestrator completed for %s with verification_status=%s "
                "after %d LLM calls",
                job.delivery_id,
                publish_result.verification_status,
                llm_calls,
            )
            await self._finish_activity(
                delivery_id=job.delivery_id,
                raw_diff=raw_diff or "",
                change_report=change_report,
                drift_report=drift_report,
                publish_result=publish_result,
                llm_calls=llm_calls,
            )
            return publish_result
        except Exception as exc:
            logger.exception("Pipeline failed for %s", job.delivery_id)
            await self._fail_activity(
                job.delivery_id, exc, llm_calls=llm_calls
            )
            return None

    # ── Activity tracking helpers ─────────────────────────────────────

    async def _start_activity(self, job: WebhookJob) -> None:
        creator = getattr(self.context_store, "create_activity_run", None)
        if not callable(creator):
            return
        try:
            await creator(
                delivery_id=job.delivery_id,
                repo_full_name=job.repo_full_name,
                commit_sha=job.head_sha,
                commit_message=job.commit_message,
                author=job.author,
                status="running",
                llm_calls=0,
            )
        except Exception:
            logger.warning(
                "Could not create activity run for %s",
                job.delivery_id,
                exc_info=True,
            )

    async def _update_activity(self, delivery_id: str, **fields) -> None:
        updater = getattr(self.context_store, "update_activity_run", None)
        if not callable(updater):
            return
        try:
            await updater(delivery_id, **fields)
        except Exception:
            logger.warning(
                "Could not update activity run %s",
                delivery_id,
                exc_info=True,
            )

    async def _no_drift_activity(
        self,
        delivery_id: str,
        raw_diff: str,
        change_report: ChangeReport,
        drift_report: DriftReport | None,
    ) -> None:
        await self._update_activity(
            delivery_id,
            status="no_drift",
            llm_calls=0,
            diff_preview=_build_diff_preview(
                raw_diff, change_report, drift_report
            ),
        )

    async def _finish_activity(
        self,
        *,
        delivery_id: str,
        raw_diff: str,
        change_report: ChangeReport,
        drift_report: DriftReport,
        publish_result: PublishResult,
        llm_calls: int,
    ) -> None:
        pr_open = bool(publish_result.pr_url)
        failed = publish_result.verification_status == "failed" or bool(
            publish_result.error
        )
        if pr_open:
            status = "pr_open"
        elif failed:
            status = "failed"
        else:
            status = "no_drift"

        evidence = publish_result.evidence_table_md
        if failed and publish_result.error:
            evidence = f"{evidence}\n\nPipeline error: {publish_result.error}".strip()

        await self._update_activity(
            delivery_id,
            status=status,
            llm_calls=llm_calls,
            pr_url=publish_result.pr_url,
            pr_number=publish_result.pr_number,
            evidence_table_md=evidence,
            diff_preview=_build_diff_preview(
                raw_diff, change_report, drift_report
            ),
        )

    async def _fail_activity(
        self,
        delivery_id: str,
        exc: Exception,
        llm_calls: int | None = None,
    ) -> None:
        await self._update_activity(
            delivery_id,
            status="failed",
            evidence_table_md=f"Pipeline error: {exc}",
            llm_calls=llm_calls,
        )

    async def _should_skip_internal(self, change_report: ChangeReport) -> bool:
        """Honor the user's internal-only early-exit setting."""
        loader = getattr(self.context_store, "get_user_settings", None)
        skip_internal = True
        if callable(loader):
            try:
                row = await loader()
                skip_internal = bool(row.get("skip_internal_changes", 1))
            except Exception:
                logger.debug("Could not load user settings", exc_info=True)

        if not skip_internal:
            return False
        return not _has_public_changes(change_report.changed_symbols)


def _has_public_changes(changed_symbols: list) -> bool:
    """Return True when at least one changed symbol is not private."""
    return any(
        bool(symbol.symbol_name) and not symbol.symbol_name.startswith("_")
        for symbol in changed_symbols
    )


def _branch_from_ref(ref: str) -> str:
    if ref.startswith("refs/heads/"):
        return ref.removeprefix("refs/heads/")
    if ref.startswith("refs/pull/"):
        return "main"
    return ref or "main"


def _build_diff_preview(
    raw_diff: str,
    change_report: ChangeReport,
    drift_report: DriftReport | None,
) -> dict:
    """Summarize a raw diff and pipeline findings for the activity drawer."""
    file_path = ""
    deleted: list[str] = []
    added: list[str] = []
    context = ""

    for line in raw_diff.splitlines():
        if line.startswith("+++ b/"):
            file_path = line.removeprefix("+++ b/")
        elif line.startswith("diff --git ") and not file_path:
            parts = line.split(" b/")
            if len(parts) > 1:
                file_path = parts[-1]
        elif line.startswith("@@") and not context:
            context = line
        elif line.startswith("+") and not line.startswith("+++"):
            if len(added) < 6:
                added.append(line)
        elif (
            line.startswith("-")
            and not line.startswith("---")
            and len(deleted) < 6
        ):
            deleted.append(line)

    if not context:
        for line in raw_diff.splitlines():
            if line.startswith(" "):
                context = line.strip()
                if context:
                    break

    symbols = [
        {
            "file_path": symbol.file_path,
            "symbol_name": symbol.symbol_name,
            "symbol_kind": symbol.symbol_kind,
            "change_class": str(symbol.change_class),
            "change_type": symbol.change_type,
            "old_signature": symbol.old_signature,
            "new_signature": symbol.new_signature,
        }
        for symbol in change_report.changed_symbols
    ]

    sections = []
    if drift_report is not None:
        sections = [
            {
                "doc_path": section.doc_path,
                "heading": section.heading,
                "anchor": None,
                "matched_symbols": section.matched_symbols,
                "match_method": section.match_method,
                "confidence_score": section.confidence,
                "start_line": section.start_line,
                "end_line": section.end_line,
            }
            for section in drift_report.impacted_sections
        ]

    return {
        "file_path": file_path,
        "deleted_lines": deleted,
        "added_lines": added,
        "context": context,
        "changed_symbols": symbols,
        "impacted_sections": sections,
    }


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
