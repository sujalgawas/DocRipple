"""Pipeline activity-state transition tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

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

RAW_DIFF = """diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,2 +1,2 @@
-def calc_total(items: list[int]) -> int:
+def calc_total(items: list[int], tax: float = 0.0) -> int:
"""

DOCS = {"README.md": "## Billing\n\n<!-- doc-anchor: billing -->\n\nold\n"}


class FakeAnalyzer:
    def __init__(self, symbols: list[ChangedSymbol]) -> None:
        self.symbols = symbols

    async def analyze(self, job, raw_diff, file_blobs=None) -> ChangeReport:
        return ChangeReport(
            delivery_id=job.delivery_id,
            repo_full_name=job.repo_full_name,
            base_sha=job.base_sha,
            head_sha=job.head_sha,
            changed_symbols=self.symbols,
        )


class FakeDriftEngine:
    def __init__(self, sections: list[ImpactedDocSection]) -> None:
        self.sections = sections

    async def compute_drift(self, change_report, docs, stored_edges=None):
        return DriftReport(
            change_report=change_report,
            impacted_sections=self.sections,
        )


class FakeOrchestrator:
    def __init__(
        self,
        result: PublishResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.last_llm_calls = 3
        self.called = False

    async def run(self, drift_report, full_docs):
        self.called = True
        if self.error is not None:
            raise self.error
        assert self.result is not None
        return self.result


class CapturingOrchestrator(FakeOrchestrator):
    """Record the publish context the pipeline exposes to the publisher."""

    def __init__(self, result: PublishResult) -> None:
        super().__init__(result)
        self.base_branch: str | None = None
        self.head_sha: str | None = None

    async def run(self, drift_report, full_docs):
        from src.web_api.github_service import (
            _current_base_branch,
            _current_head_sha,
        )

        self.base_branch = _current_base_branch.get()
        self.head_sha = _current_head_sha.get()
        return await super().run(drift_report, full_docs)


def make_symbol(name: str = "calc_total") -> ChangedSymbol:
    return ChangedSymbol(
        file_path="src/app.py",
        symbol_name=name,
        symbol_kind="function",
        change_class=ChangeClass.API_SURFACE,
        change_type="modified",
        old_signature="def calc_total(items: list[int]) -> int",
        new_signature="def calc_total(items: list[int], tax: float = 0.0) -> int",
        diff_hunk="@@ -1,2 +1,2 @@",
    )


def make_section() -> ImpactedDocSection:
    return ImpactedDocSection(
        doc_path="README.md",
        heading="Billing",
        start_line=1,
        end_line=5,
        matched_symbols=["calc_total"],
        match_method="exact_anchor",
        confidence=1.0,
        current_markdown="old",
    )


def make_job(delivery_id: str = "delivery-1") -> WebhookJob:
    return WebhookJob(
        delivery_id=delivery_id,
        event_type="push",
        repo_full_name="octo/docs",
        base_sha="base123",
        head_sha="head456",
        ref="refs/heads/main",
        received_at=datetime.now(UTC),
        commit_message="feat: add tax",
        author="octocat",
    )


@pytest.fixture
async def store(tmp_path):
    context_store = SqliteContextStore(str(tmp_path / "pipeline.db"))
    await context_store.initialize()
    yield context_store
    await context_store.close()


def build_pipeline(store, analyzer, drift, orchestrator) -> DocSyncPipeline:
    return DocSyncPipeline(
        analyzer=analyzer,
        drift_engine=drift,
        orchestrator=orchestrator,
        context_store=store,
    )


@pytest.mark.asyncio
async def test_pipeline_marks_pr_open(store):
    orchestrator = FakeOrchestrator(
        PublishResult(
            delivery_id="delivery-1",
            pr_url="https://github.com/octo/docs/pull/9",
            pr_number=9,
            evidence_table_md="| doc | symbol |\n| README.md | calc_total |",
            verification_status="passed",
        )
    )
    pipeline = build_pipeline(
        store,
        FakeAnalyzer([make_symbol()]),
        FakeDriftEngine([make_section()]),
        orchestrator,
    )

    result = await pipeline.execute_job(
        make_job(), raw_diff=RAW_DIFF, docs=DOCS, file_blobs={}
    )

    assert result is not None
    assert orchestrator.called
    run = await store.get_activity_run("delivery-1")
    assert run["status"] == "pr_open"
    assert run["llm_calls"] == 3
    assert run["pr_number"] == 9
    assert run["commit_message"] == "feat: add tax"
    assert run["diff_preview"]["changed_symbols"][0]["symbol_name"] == "calc_total"
    assert run["diff_preview"]["impacted_sections"][0]["heading"] == "Billing"


@pytest.mark.asyncio
async def test_pull_request_publishes_against_base_branch(store):
    orchestrator = CapturingOrchestrator(
        PublishResult(
            delivery_id="delivery-pr",
            pr_url="https://github.com/octo/docs/pull/11",
            pr_number=11,
            verification_status="passed",
        )
    )
    pipeline = build_pipeline(
        store,
        FakeAnalyzer([make_symbol()]),
        FakeDriftEngine([make_section()]),
        orchestrator,
    )

    job = make_job("delivery-pr").model_copy(
        update={
            "event_type": "pull_request",
            "ref": "feature/docs",
            "base_ref": "main",
        }
    )
    result = await pipeline.execute_job(
        job, raw_diff=RAW_DIFF, docs=DOCS, file_blobs={}
    )

    assert result is not None
    assert orchestrator.base_branch == "main"
    assert orchestrator.head_sha == "head456"


@pytest.mark.asyncio
async def test_pipeline_marks_no_drift_without_llm(store):
    orchestrator = FakeOrchestrator()
    pipeline = build_pipeline(
        store,
        FakeAnalyzer([make_symbol()]),
        FakeDriftEngine([]),
        orchestrator,
    )

    result = await pipeline.execute_job(
        make_job(), raw_diff=RAW_DIFF, docs=DOCS, file_blobs={}
    )

    assert result is None
    assert not orchestrator.called
    run = await store.get_activity_run("delivery-1")
    assert run["status"] == "no_drift"
    assert run["llm_calls"] == 0


@pytest.mark.asyncio
async def test_pipeline_skips_private_symbols_by_default(store):
    orchestrator = FakeOrchestrator()
    pipeline = build_pipeline(
        store,
        FakeAnalyzer([make_symbol("_internal_helper")]),
        FakeDriftEngine([make_section()]),
        orchestrator,
    )

    result = await pipeline.execute_job(
        make_job(), raw_diff=RAW_DIFF, docs=DOCS, file_blobs={}
    )

    assert result is None
    assert not orchestrator.called
    assert (await store.get_activity_run("delivery-1"))["status"] == "no_drift"


@pytest.mark.asyncio
async def test_pipeline_runs_private_symbols_when_setting_disabled(store):
    await store.update_user_settings(skip_internal_changes=0)
    orchestrator = FakeOrchestrator(
        PublishResult(
            delivery_id="delivery-1",
            pr_url="https://github.com/octo/docs/pull/10",
            pr_number=10,
            verification_status="passed",
        )
    )
    pipeline = build_pipeline(
        store,
        FakeAnalyzer([make_symbol("_internal_helper")]),
        FakeDriftEngine([make_section()]),
        orchestrator,
    )

    await pipeline.execute_job(
        make_job(), raw_diff=RAW_DIFF, docs=DOCS, file_blobs={}
    )

    assert orchestrator.called
    assert (await store.get_activity_run("delivery-1"))["status"] == "pr_open"


@pytest.mark.asyncio
async def test_pipeline_marks_failed_on_exception(store):
    pipeline = build_pipeline(
        store,
        FakeAnalyzer([make_symbol()]),
        FakeDriftEngine([make_section()]),
        FakeOrchestrator(error=RuntimeError("LLM unavailable")),
    )

    result = await pipeline.execute_job(
        make_job(), raw_diff=RAW_DIFF, docs=DOCS, file_blobs={}
    )

    assert result is None
    run = await store.get_activity_run("delivery-1")
    assert run["status"] == "failed"
    assert run["llm_calls"] == 3
    assert "LLM unavailable" in run["evidence_table_md"]
