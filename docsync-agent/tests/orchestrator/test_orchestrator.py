"""Tests for the LangGraph Orchestrator module (Agent 4).

Covers: happy path, repair loop (verifier/reviewer → writer retry), and max-retries guardrail.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel

from src.contracts.schemas import (
    ChangeClass,
    ChangedSymbol,
    ChangeReport,
    CodeDocEdge,
    DriftReport,
    ImpactedDocSection,
)
from src.orchestrator.config import OrchestratorConfig
from src.orchestrator.schemas import (
    PublishResult,
)
from src.orchestrator.service import OrchestratorService

# ════════════════════════════════════════════════════════════════════════════
# Fakes
# ════════════════════════════════════════════════════════════════════════════


class FakeLLMClient:
    """Deterministic LLM — returns pre-programmed responses from a stack.

    ``generate_text`` responses are consumed FIFO.
    ``generate_json`` raises NotImplementedError (planner falls back to generate_text).
    """

    def __init__(self, text_responses: list[str] | None = None):
        self._text_responses: list[str] = list(text_responses or [])
        self._text_calls: list[tuple[str, str]] = []

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
    ) -> BaseModel:
        raise NotImplementedError("FakeLLMClient.generate_json — use generate_text")

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        self._text_calls.append((system_prompt[:100], user_prompt[:100]))
        if self._text_responses:
            return self._text_responses.pop(0)
        return "APPROVED"


class FakeGitHubPublisher:
    """Records PR creation calls and returns fixed results."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def create_docs_pr(
        self,
        repo_full_name: str,
        base_sha: str,
        branch_name: str,
        updated_docs: dict[str, str],
        pr_title: str,
        pr_body: str,
    ) -> tuple[str, int]:
        self.calls.append({
            "repo_full_name": repo_full_name,
            "base_sha": base_sha,
            "branch_name": branch_name,
            "updated_docs": dict(updated_docs),
            "pr_title": pr_title,
            "pr_body": pr_body,
        })
        return ("https://github.com/owner/repo/pull/42", 42)


class FakeContextStore:
    """In-memory store recording edges and publish results."""

    def __init__(self) -> None:
        self.edges: list[CodeDocEdge] = []
        self.publish_results: list[PublishResult] = []
        self.deliveries: set[tuple[str, str]] = set()

    async def check_and_record_delivery(self, delivery_id: str, repo_full_name: str) -> bool:
        key = (delivery_id, repo_full_name)
        if key in self.deliveries:
            return False
        self.deliveries.add(key)
        return True

    async def get_edges_for_symbols(
        self, repo_full_name: str, symbol_names: list[str]
    ) -> list[CodeDocEdge]:
        return [e for e in self.edges if e.symbol_name in symbol_names]

    async def save_edges(self, edges: list[CodeDocEdge]) -> None:
        self.edges.extend(edges)

    async def save_publish_result(self, result: PublishResult) -> None:
        self.publish_results.append(result)


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════


def _make_changed_symbol(
    name: str,
    file_path: str = "src/app.py",
    new_sig: str = "def foo(x: int) -> str:",
    diff_hunk: str = "@@ -1 +1 @@\n-def foo():\n+def foo(x: int) -> str:",
) -> ChangedSymbol:
    return ChangedSymbol(
        file_path=file_path,
        symbol_name=name,
        symbol_kind="function",
        change_class=ChangeClass.API_SURFACE,
        change_type="modified",
        old_signature="def foo():",
        new_signature=new_sig,
        diff_hunk=diff_hunk,
    )


def _make_change_report(
    delivery_id: str = "test-001",
    repo: str = "owner/repo",
    symbols: list[ChangedSymbol] | None = None,
) -> ChangeReport:
    return ChangeReport(
        delivery_id=delivery_id,
        repo_full_name=repo,
        base_sha="abc123",
        head_sha="def456",
        changed_symbols=symbols or [],
    )


def _make_drift_report(
    change_report: ChangeReport,
    sections: list[ImpactedDocSection] | None = None,
) -> DriftReport:
    return DriftReport(
        change_report=change_report,
        impacted_sections=sections or [],
    )


def _make_impacted_section(
    doc_path: str = "docs/api.md",
    heading: str = "## create_user",
    symbols: list[str] | None = None,
    markdown: str = "",
) -> ImpactedDocSection:
    return ImpactedDocSection(
        doc_path=doc_path,
        heading=heading,
        start_line=1,
        end_line=5,
        matched_symbols=symbols or [],
        match_method="exact_anchor",
        confidence=0.95,
        current_markdown=markdown,
    )


# ════════════════════════════════════════════════════════════════════════════
# Test 1: Happy Path
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_happy_path_planner_to_publisher():
    """Full Planner→Writer→Verifier→Reviewer→Publisher succeeds on first pass.

    Verifies:
    - All nodes execute
    - PR is created with a valid Evidence Table
    - CodeDocEdge entries and PublishResult are persisted
    """
    # ── Setup ─────────────────────────────────────────────────────────

    symbol = _make_changed_symbol("create_user")
    change_report = _make_change_report(symbols=[symbol])

    original_doc = (
        "## create_user\n\n<!-- doc-anchor: create-user -->\n\n"
        "Creates a user.\n\n```python\n"
        "async def create_user(email: str) -> dict:\n"
        "    ...\n```\n"
    )

    section = _make_impacted_section(
        doc_path="docs/api.md",
        heading="create_user",
        symbols=["create_user"],
        markdown=original_doc,
    )

    drift_report = _make_drift_report(change_report, sections=[section])

    full_docs = {"docs/api.md": original_doc}

    # Planner response: JSON array of SectionEditPlan
    planner_response = json.dumps([
        {
            "doc_path": "docs/api.md",
            "heading": "create_user",
            "target_symbols": ["create_user"],
            "instructions": "Update signature to def create_user(email: str) -> dict:",
        }
    ])

    # Writer response: updated markdown
    writer_response = (
        "Creates a user with email.\n\n"
        "<!-- doc-anchor: create-user -->\n\n"
        "```python\n"
        "async def create_user(email: str) -> dict:\n"
        "    ...\n```\n"
    )

    text_responses = [
        planner_response,   # 0: planner
        writer_response,    # 1: writer
        "APPROVED",         # 2: reviewer
    ]

    fake_llm = FakeLLMClient(text_responses=text_responses)
    fake_github = FakeGitHubPublisher()
    fake_store = FakeContextStore()

    config = OrchestratorConfig(max_retries=2)
    service = OrchestratorService(
        llm_client=fake_llm,
        github_publisher=fake_github,
        context_store=fake_store,
        config=config,
    )

    # ── Run ───────────────────────────────────────────────────────────

    result = await service.run(drift_report, full_docs)

    # ── Assertions ────────────────────────────────────────────────────

    assert result.verification_status == "passed"
    assert result.pr_url == "https://github.com/owner/repo/pull/42"
    assert result.pr_number == 42
    assert "docs/api.md" in result.files_updated
    assert result.error is None

    # Evidence table (header row + data rows)
    assert "Doc File" in result.evidence_table_md
    assert "Changed Symbol" in result.evidence_table_md
    assert "create_user" in result.evidence_table_md
    assert "passed" in result.evidence_table_md

    # GitHub PR was opened, with the evidence table embedded in the body
    assert len(fake_github.calls) == 1
    pr_call = fake_github.calls[0]
    assert "docs/api.md" in pr_call["updated_docs"]
    assert "Evidence Table" in pr_call["pr_body"]
    assert "create_user" in pr_call["pr_body"]

    # ContextStore persisted edges + result
    assert len(fake_store.edges) >= 1
    edge_names = {e.symbol_name for e in fake_store.edges}
    assert "create_user" in edge_names

    assert len(fake_store.publish_results) == 1
    assert fake_store.publish_results[0].pr_url == "https://github.com/owner/repo/pull/42"


# ════════════════════════════════════════════════════════════════════════════
# Regression: untouched docs must not be published or verified
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_only_changed_docs_are_published():
    """Docs that were not rewritten stay out of the PR and the verifier.

    ``docs/other.md`` deliberately contains a pre-existing unbalanced code
    fence: it must not fail the run because no edit plan targets it.
    """
    symbol = _make_changed_symbol("create_user")
    change_report = _make_change_report(
        delivery_id="test-only-changed", symbols=[symbol]
    )

    original_doc = (
        "## create_user\n\n<!-- doc-anchor: create-user -->\n\n"
        "Creates a user.\n\n```python\n"
        "async def create_user(email: str) -> dict:\n"
        "    ...\n```\n"
    )
    untouched_doc = "# Other\n\n```python\nprint('unclosed')\n"

    section = _make_impacted_section(
        doc_path="docs/api.md",
        heading="create_user",
        symbols=["create_user"],
        markdown=original_doc,
    )
    drift_report = _make_drift_report(change_report, sections=[section])
    full_docs = {"docs/api.md": original_doc, "docs/other.md": untouched_doc}

    planner_response = json.dumps(
        [
            {
                "doc_path": "docs/api.md",
                "heading": "create_user",
                "target_symbols": ["create_user"],
                "instructions": "Document the email parameter.",
            }
        ]
    )
    writer_response = (
        "Creates a user with an email address.\n\n"
        "<!-- doc-anchor: create-user -->\n\n"
        "```python\nasync def create_user(email: str) -> dict:\n    ...\n```\n"
    )

    fake_llm = FakeLLMClient(
        text_responses=[planner_response, writer_response, "APPROVED"]
    )
    fake_github = FakeGitHubPublisher()
    fake_store = FakeContextStore()
    service = OrchestratorService(
        llm_client=fake_llm,
        github_publisher=fake_github,
        context_store=fake_store,
        config=OrchestratorConfig(max_retries=2),
    )

    result = await service.run(drift_report, full_docs)

    assert result.verification_status == "passed"
    assert len(fake_github.calls) == 1
    assert set(fake_github.calls[0]["updated_docs"]) == {"docs/api.md"}
    assert result.files_updated == ["docs/api.md"]


# ════════════════════════════════════════════════════════════════════════════
# Test 2: Verifier/Reviewer Repair Loop
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_repair_loop_verifier_flags_error_then_fixes():
    """First draft omits the changed symbol → verifier flags error →
    reviewer routes back to writer → second draft fixes it → publisher completes.
    """
    # ── Setup ─────────────────────────────────────────────────────────

    symbol = _make_changed_symbol("compute_score")
    change_report = _make_change_report(delivery_id="test-002", symbols=[symbol])

    original_doc = (
        "## compute_score\n\n"
        "<!-- doc-anchor: compute-score -->\n\n"
        "Computes a score.\n\n```python\n"
        "def compute_score(x: int) -> int:\n"
        "    return x\n```\n"
    )

    section = _make_impacted_section(
        doc_path="docs/utils.md",
        heading="compute_score",
        symbols=["compute_score"],
        markdown=original_doc,
    )

    drift_report = _make_drift_report(change_report, sections=[section])

    full_docs = {"docs/utils.md": original_doc}

    planner_plan = json.dumps([
        {
            "doc_path": "docs/utils.md",
            "heading": "compute_score",
            "target_symbols": ["compute_score"],
            "instructions": "Update compute_score signature",
        }
    ])

    # First writer output: OMITS the symbol name and has unbalanced code fence
    bad_writer_output = (
        "Computes a score.\n\n"
        "<!-- doc-anchor: compute-score -->\n\n"
        "```python\n"
        "# Bad: no compute_score symbol, unbalanced ```\n"
        "return x + 1\n"
    )

    # Second writer output: FIXED — includes symbol and balanced fences
    good_writer_output = (
        "Computes a score with bonus.\n\n"
        "<!-- doc-anchor: compute-score -->\n\n"
        "```python\n"
        "def compute_score(x: int) -> int:\n"
        "    return x + 1\n```\n"
    )

    text_responses = [
        planner_plan,       # 0: planner
        bad_writer_output,  # 1: writer (first attempt)
        # reviewer will auto-reject because verifier found errors; no LLM call for reviewer in this case
        good_writer_output, # 2: writer (retry)
        "APPROVED",         # 3: reviewer (second pass)
    ]

    fake_llm = FakeLLMClient(text_responses=text_responses)
    fake_github = FakeGitHubPublisher()
    fake_store = FakeContextStore()

    config = OrchestratorConfig(max_retries=2)
    service = OrchestratorService(
        llm_client=fake_llm,
        github_publisher=fake_github,
        context_store=fake_store,
        config=config,
    )

    # ── Run ───────────────────────────────────────────────────────────

    result = await service.run(drift_report, full_docs)

    # ── Assertions ────────────────────────────────────────────────────

    assert result.verification_status == "repaired"
    assert result.pr_url is not None

    # Evidence table should show repaired status
    assert "Doc File" in result.evidence_table_md
    assert "repaired" in result.evidence_table_md

    # GitHub PR was opened
    assert len(fake_github.calls) == 1

    # Edges persisted
    assert len(fake_store.edges) >= 1
    assert "compute_score" in {e.symbol_name for e in fake_store.edges}


# ════════════════════════════════════════════════════════════════════════════
# Test 3: Max Retries Guardrail
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_max_retries_guardrail():
    """FakeLLM keeps returning invalid output → loop terminates at max_retries=2
    instead of looping forever.
    """
    # ── Setup ─────────────────────────────────────────────────────────

    symbol = _make_changed_symbol("bad_func")
    change_report = _make_change_report(delivery_id="test-003", symbols=[symbol])

    original_doc = (
        "## bad_func\n\n"
        "<!-- doc-anchor: bad-func -->\n\n"
        "Does something.\n\n```python\n"
        "def bad_func():\n"
        "    pass\n```\n"
    )

    section = _make_impacted_section(
        doc_path="docs/bad.md",
        heading="bad_func",
        symbols=["bad_func"],
        markdown=original_doc,
    )

    drift_report = _make_drift_report(change_report, sections=[section])
    full_docs = {"docs/bad.md": original_doc}

    planner_plan = json.dumps([
        {
            "doc_path": "docs/bad.md",
            "heading": "bad_func",
            "target_symbols": ["bad_func"],
            "instructions": "Update bad_func",
        }
    ])

    # Always-bad writer output: missing symbol name, unbalanced fence
    always_bad = (
        "Does something.\n\n"
        "```python\n"
        "# no symbol, no close\n"
    )

    text_responses = [
        planner_plan,   # 0: planner
        always_bad,     # 1: writer (1st)
        always_bad,     # 2: writer (2nd — retry_count=1)
        always_bad,     # 3: writer (3rd — retry_count=2, but max_retries=2 means force-approve)
        "APPROVED",     # 4: reviewer (force-approve, but let's say it still approved)
    ]

    fake_llm = FakeLLMClient(text_responses=text_responses)
    fake_github = FakeGitHubPublisher()
    fake_store = FakeContextStore()

    config = OrchestratorConfig(max_retries=2)
    service = OrchestratorService(
        llm_client=fake_llm,
        github_publisher=fake_github,
        context_store=fake_store,
        config=config,
    )

    # ── Run ───────────────────────────────────────────────────────────

    result = await service.run(drift_report, full_docs)

    # ── Assertions ────────────────────────────────────────────────────

    # Pipeline should complete (not loop forever)
    assert result is not None
    assert result.delivery_id == "test-003"

    # Should have detected a problem and either published anyway or failed
    # The PR may be opened or errored, but the pipeline terminates
    if len(fake_github.calls) > 0:
        # Published despite errors (force-approved at max_retries)
        assert result.verification_status in ("repaired", "failed")
    else:
        # Failed before publishing
        assert result.error is not None or result.verification_status == "failed"

    # Ensure we didn't loop more than max_retries+1 times (planner + 3 writes)
    # Each cycle: verifier sets errors → reviewer increments retry_count → loops to writer
    # At retry_count >= max_retries, reviewer forces approve → publisher
    assert len(fake_llm._text_calls) <= 6  # planner(1) + writer(3) + reviewer(1) = 5 max