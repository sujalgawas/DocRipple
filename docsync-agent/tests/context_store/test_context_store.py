"""Tests for the ContextStore module (Agent 5).

Covers: delivery dedup (incl. concurrent), edge graph upsert/lookup,
empty-query safety, run-result round-trip, and embedding cache invalidation.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from src.context_store.sqlite_store import SqliteContextStore
from src.contracts.schemas import CodeDocEdge
from src.orchestrator.schemas import EvidenceRow, PublishResult


@pytest.fixture
async def store(tmp_path) -> SqliteContextStore:
    """An initialised SqliteContextStore on a temporary SQLite file."""
    db_path = tmp_path / "test.db"
    s = SqliteContextStore(str(db_path))
    await s.initialize()
    yield s
    await s.close()


def _edge(
    repo: str,
    symbol: str,
    doc_path: str = "docs/api.md",
    heading: str = "## create_user",
    file_path: str = "src/app.py",
    anchor_type: str = "explicit_anchor",
) -> CodeDocEdge:
    return CodeDocEdge(
        repo_full_name=repo,
        symbol_name=symbol,
        file_path=file_path,
        doc_path=doc_path,
        section_heading=heading,
        anchor_type=anchor_type,
    )


# ════════════════════════════════════════════════════════════════════════════
# 1. Atomic delivery deduplication
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_delivery_deduplication(store: SqliteContextStore):
    first = await store.check_and_record_delivery("deliv-1", "acme/repo")
    second = await store.check_and_record_delivery("deliv-1", "acme/repo")

    assert first is True
    assert second is False


@pytest.mark.asyncio
async def test_delivery_deduplication_concurrent(store: SqliteContextStore):
    """Concurrent duplicate deliveries never race — exactly one wins."""
    results = await asyncio.gather(
        store.check_and_record_delivery("deliv-2", "acme/repo"),
        store.check_and_record_delivery("deliv-2", "acme/repo"),
        store.check_and_record_delivery("deliv-2", "acme/repo"),
    )

    assert results.count(True) == 1
    assert results.count(False) == 2


# ════════════════════════════════════════════════════════════════════════════
# 2. Code-doc graph edge upsert & lookup
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_edge_upsert_and_lookup(store: SqliteContextStore):
    edges = [
        _edge("acme/repo", "create_user"),
        _edge("acme/repo", "delete_user", doc_path="docs/api.md", heading="## delete_user"),
        _edge("other/repo", "create_user"),  # different repo, same symbol name
    ]
    await store.upsert_edges(edges)

    # Filter by repo + symbol filter
    result = await store.get_edges_for_symbols("acme/repo", ["create_user"])
    assert len(result) == 1
    assert result[0].symbol_name == "create_user"
    assert result[0].repo_full_name == "acme/repo"

    # Multi-symbol query
    result = await store.get_edges_for_symbols("acme/repo", ["create_user", "delete_user"])
    assert len(result) == 2

    # Other repo is isolated
    result = await store.get_edges_for_symbols("acme/repo", ["create_user"])
    assert all(e.repo_full_name == "acme/repo" for e in result)


@pytest.mark.asyncio
async def test_edge_upsert_updates_without_duplicate(store: SqliteContextStore):
    # Insert then re-insert with a modified anchor_type for the SAME key
    await store.upsert_edges([_edge("acme/repo", "create_user", anchor_type="explicit_anchor")])
    await store.upsert_edges([_edge("acme/repo", "create_user", anchor_type="inline_code")])

    result = await store.get_edges_for_symbols("acme/repo", ["create_user"])

    assert len(result) == 1  # no duplicate rows
    assert result[0].anchor_type == "inline_code"  # updated, not duplicated


# ════════════════════════════════════════════════════════════════════════════
# 3. Empty symbol query safety
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_empty_symbol_query(store: SqliteContextStore):
    # Seed a row to prove the early-return doesn't depend on emptiness
    await store.upsert_edges([_edge("acme/repo", "create_user")])

    result = await store.get_edges_for_symbols("acme/repo", [])
    assert result == []


# ════════════════════════════════════════════════════════════════════════════
# 4. Run result persistence & retrieval
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_run_result_round_trip(store: SqliteContextStore):
    evidence_table = (
        "| Doc File | Section | Changed Symbol | Change Class | Match Method | Verification |\n"
        "|----------|---------|----------------|--------------|--------------|-------------|\n"
        "| `docs/api.md` | create_user | `create_user` | `api_surface` | exact_anchor | passed |"
    )

    result = PublishResult(
        delivery_id="deliv-1",
        pr_url="https://github.com/acme/repo/pull/7",
        pr_number=7,
        evidence_table_md=evidence_table,
        verification_status="passed",
        files_updated=["docs/api.md"],
        error=None,
    )

    evidence = [
        EvidenceRow(
            doc_file="docs/api.md",
            section="create_user",
            changed_symbol="create_user",
            change_class="api_surface",
            match_method="exact_anchor",
            verification="passed",
        )
    ]

    await store.save_run_result("deliv-1", "acme/repo", result, evidence)

    fetched = await store.get_run_result("deliv-1")

    assert fetched is not None
    assert fetched.delivery_id == "deliv-1"
    assert fetched.pr_url == "https://github.com/acme/repo/pull/7"
    assert fetched.pr_number == 7
    assert fetched.verification_status == "passed"
    assert fetched.files_updated == ["docs/api.md"]
    # Markdown evidence table preserved byte-for-byte
    assert fetched.evidence_table_md == evidence_table
    assert "create_user" in fetched.evidence_table_md


@pytest.mark.asyncio
async def test_run_result_missing_returns_none(store: SqliteContextStore):
    assert await store.get_run_result("does-not-exist") is None


# ════════════════════════════════════════════════════════════════════════════
# 5. Embedding cache invalidation
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_embedding_cache_hit_and_invalidation(store: SqliteContextStore):
    vector = [0.1, 0.2, 0.3]

    await store.set_cached_embedding(
        "acme/repo", "docs/api.md", "create_user", "hash-abc", vector
    )

    # Match → returns the vector
    cached = await store.get_cached_embedding(
        "acme/repo", "docs/api.md", "create_user", "hash-abc"
    )
    assert cached == vector

    # Different content_hash → None (invalidated / stale)
    stale = await store.get_cached_embedding(
        "acme/repo", "docs/api.md", "create_user", "hash-changed"
    )
    assert stale is None

    # Different section → None (never cached)
    missing = await store.get_cached_embedding(
        "acme/repo", "docs/api.md", "other_section", "hash-abc"
    )
    assert missing is None


# ════════════════════════════════════════════════════════════════════════════
# 6. Read-only path / Vercel path fallback
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_readonly_var_task_path_falls_back_to_writable():
    """A read-only path like /var/task/docsync_context.db must initialize cleanly."""
    store = SqliteContextStore("/var/task/docsync_context.db")
    await store.initialize()
    try:
        normalized_path = store._db_path.replace("\\", "/")
        assert (
            normalized_path.endswith("/tmp/docsync_context.db")
            or store._db_path == ":memory:"
        )

        recorded = await store.check_and_record_delivery(
            f"deliv-{uuid4().hex}", "test/repo"
        )
        assert recorded is True
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_vercel_env_forces_tmp_resolution(monkeypatch: pytest.MonkeyPatch):
    """When VERCEL is set, relative paths are forced into /tmp."""
    monkeypatch.setenv("VERCEL", "1")
    store = SqliteContextStore("docsync_context.db")
    await store.initialize()
    try:
        normalized_path = store._db_path.replace("\\", "/")
        assert (
            normalized_path.endswith("/tmp/docsync_context.db")
            or store._db_path == ":memory:"
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_checkpointer_readonly_path_fallback():
    """_checkpointer falls back to InMemorySaver when given an unwritable path."""
    from src.orchestrator.graph import _checkpointer

    async with _checkpointer("/var/task/checkpoints.db") as saver:
        assert saver is not None


def test_settings_db_path_validator(monkeypatch: pytest.MonkeyPatch):
    """AppSettings validator rewrites relative and unwritable paths to /tmp."""
    from src.config import AppSettings, Settings

    assert Settings is AppSettings

    # Relative path is rewritten to /tmp/...
    s = AppSettings(SQLITE_DB_PATH="custom.db")
    assert s.SQLITE_DB_PATH == "/tmp/custom.db"

    # Memory path is preserved
    s_mem = AppSettings(SQLITE_DB_PATH=":memory:", CHECKPOINT_DB_PATH=":memory:")
    assert s_mem.SQLITE_DB_PATH == ":memory:"
    assert s_mem.CHECKPOINT_DB_PATH == ":memory:"

    # Vercel env rewrites any path outside /tmp
    monkeypatch.setenv("VERCEL", "1")
    s_vercel = AppSettings(
        SQLITE_DB_PATH="/var/task/docsync_context.db",
        CHECKPOINT_DB_PATH="/var/task/checkpoints.db",
        FRONTEND_URL="http://localhost:5173/",
    )
    assert s_vercel.SQLITE_DB_PATH == "/tmp/docsync_context.db"
    assert s_vercel.CHECKPOINT_DB_PATH == "/tmp/checkpoints.db"
    assert s_vercel.FRONTEND_URL == "https://docripple.vercel.app"

    monkeypatch.delenv("VERCEL", raising=False)
    s_local = AppSettings(FRONTEND_URL="http://localhost:5173/")
    assert s_local.FRONTEND_URL == "http://localhost:5173"