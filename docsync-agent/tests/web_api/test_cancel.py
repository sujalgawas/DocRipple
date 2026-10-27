"""Cancelling a running (or stuck) pipeline run."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.context_store.sqlite_store import SqliteContextStore
from src.contracts.schemas import (
    ChangeClass,
    ChangedSymbol,
    ChangeReport,
    DriftReport,
    ImpactedDocSection,
    PublishResult,
    WebhookJob,
)
from src.pipeline import DocSyncPipeline
from src.web_api.router import router as web_api_router


def _job(delivery_id: str = "manual-cancel") -> WebhookJob:
    return WebhookJob(
        delivery_id=delivery_id,
        event_type="push",
        repo_full_name="acme/docs",
        base_sha="1" * 40,
        head_sha="2" * 40,
        ref="refs/heads/main",
        received_at=datetime.now(UTC),
        commit_message="feat: billing",
        author="octocat",
    )


class FakeStore:
    def __init__(self) -> None:
        self.updated: list[tuple[str, dict]] = []
        self.created: list[str] = []

    async def get_edges_for_symbols(self, repo_full_name, symbol_names):
        return []

    async def get_user_settings(self):
        return {"skip_internal_changes": 1}

    async def create_activity_run(self, delivery_id, repo_full_name, **kwargs):
        self.created.append(delivery_id)

    async def update_activity_run(self, delivery_id, **fields):
        self.updated.append((delivery_id, fields))


class FakeFetcher:
    token = ""

    async def fetch_diff(self, repo_full_name, base_sha, head_sha):
        return "diff --git a/src/billing.py b/src/billing.py\n"

    async def fetch_docs(self, repo_full_name, head_sha):
        return {"README.md": "# Docs\n"}


class FakeAnalyzer:
    async def analyze(self, job, raw_diff, file_blobs=None):
        return ChangeReport(
            delivery_id=job.delivery_id,
            repo_full_name=job.repo_full_name,
            base_sha=job.base_sha,
            head_sha=job.head_sha,
            changed_symbols=[
                ChangedSymbol(
                    file_path="src/billing.py",
                    symbol_name="calc_total",
                    symbol_kind="function",
                    change_class=ChangeClass.API_SURFACE,
                    change_type="modified",
                    old_signature="def calc_total(items):",
                    new_signature="def calc_total(items, tax):",
                    diff_hunk="@@ -1 +1 @@",
                )
            ],
        )


class FakeDrift:
    def __init__(self, on_run=None) -> None:
        self.on_run = on_run

    async def compute_drift(self, change_report, docs, stored_edges=None):
        if self.on_run is not None:
            self.on_run()
        return DriftReport(
            change_report=change_report,
            impacted_sections=[
                ImpactedDocSection(
                    doc_path="README.md",
                    heading="Billing",
                    start_line=1,
                    end_line=3,
                    matched_symbols=["calc_total"],
                    match_method="exact_anchor",
                    confidence=1.0,
                    current_markdown="## Billing\n",
                )
            ],
        )


class FakeOrchestrator:
    def __init__(self) -> None:
        self.calls = 0
        self.last_llm_calls = 0

    async def run(self, drift_report, docs):
        self.calls += 1
        return PublishResult(delivery_id=drift_report.change_report.delivery_id)


def _pipeline(
    store: FakeStore,
    drift: FakeDrift,
    orchestrator: FakeOrchestrator,
    cancelled: set[str],
) -> DocSyncPipeline:
    return DocSyncPipeline(
        analyzer=FakeAnalyzer(),
        drift_engine=drift,
        orchestrator=orchestrator,
        context_store=store,
        fetcher=FakeFetcher(),
        cancelled_deliveries=cancelled,
    )


@pytest.mark.asyncio
async def test_cancel_before_run_skips_immediately() -> None:
    store, orchestrator = FakeStore(), FakeOrchestrator()
    cancelled = {"manual-cancel"}
    pipeline = _pipeline(store, FakeDrift(), orchestrator, cancelled)

    result = await pipeline.process_webhook(_job())

    assert result is None
    assert orchestrator.calls == 0
    assert any(
        fields.get("status") == "failed"
        and fields.get("evidence_table_md") == "Cancelled by user"
        for _, fields in store.updated
    )


@pytest.mark.asyncio
async def test_cancel_mid_pipeline_skips_orchestrator() -> None:
    store, orchestrator = FakeStore(), FakeOrchestrator()
    cancelled: set[str] = set()
    drift = FakeDrift(
        on_run=lambda: cancelled.add("manual-cancel")  # cancel arrives during drift
    )
    pipeline = _pipeline(store, drift, orchestrator, cancelled)

    result = await pipeline.process_webhook(_job())

    assert result is None
    assert orchestrator.calls == 0
    assert pipeline.active_run_tasks == {}
    assert any(
        fields.get("status") == "failed" for _, fields in store.updated
    )


@pytest.mark.asyncio
async def test_cancel_endpoint_marks_run_and_cancels_task(tmp_path) -> None:
    store = SqliteContextStore(str(tmp_path / "cancel.db"))
    await store.initialize()
    await store.create_activity_run(
        delivery_id="manual-cancel",
        repo_full_name="acme/docs",
        commit_sha="2" * 40,
        status="running",
    )

    class DummyTask:
        def __init__(self) -> None:
            self.cancelled = False

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            self.cancelled = True

    dummy = DummyTask()
    test_app = FastAPI()
    test_app.include_router(web_api_router)
    test_app.state.context_store = store
    test_app.state.active_run_tasks = {"manual-cancel": dummy}
    test_app.state.cancelled_deliveries = set()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/activity/manual-cancel/cancel"
            )

        assert response.status_code == 200
        assert response.json() == {
            "status": "cancelled",
            "delivery_id": "manual-cancel",
        }
        assert dummy.cancelled is True
        assert "manual-cancel" in test_app.state.cancelled_deliveries

        run = await store.get_activity_run("manual-cancel")
        assert run is not None
        assert run["status"] == "failed"
        assert run["llm_calls"] == 0
        assert run["evidence_table_md"] == "Cancelled by user"
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_cancel_endpoint_accepts_commit_sha(tmp_path) -> None:
    store = SqliteContextStore(str(tmp_path / "cancel-sha.db"))
    await store.initialize()
    sha = "abcdef1234567890"
    await store.create_activity_run(
        delivery_id="manual-sha-run",
        repo_full_name="acme/docs",
        commit_sha=sha,
        status="running",
    )

    test_app = FastAPI()
    test_app.include_router(web_api_router)
    test_app.state.context_store = store
    test_app.state.active_run_tasks = {}
    test_app.state.cancelled_deliveries = set()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            response = await client.post(f"/api/v1/activity/{sha}/cancel")

        assert response.status_code == 200
        # The real delivery id is remembered so the pipeline sees the flag.
        assert "manual-sha-run" in test_app.state.cancelled_deliveries
        run = await store.get_activity_run("manual-sha-run")
        assert run is not None
        assert run["status"] == "failed"
    finally:
        await store.close()
