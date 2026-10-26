"""Persistence tests for the web API tables."""

from __future__ import annotations

import pytest

from src.context_store.sqlite_store import SqliteContextStore


@pytest.fixture
async def store(tmp_path):
    context_store = SqliteContextStore(str(tmp_path / "web_api.db"))
    await context_store.initialize()
    yield context_store
    await context_store.close()


@pytest.mark.asyncio
async def test_monitored_repo_lifecycle(store):
    await store.upsert_monitored_repo(
        repo_full_name="octo/docs",
        owner="octo",
        name="docs",
        watch_branch="main",
        doc_paths=["README.md", "docs/**/*.md"],
        language="Python",
        webhook_id=42,
    )

    repo = await store.get_monitored_repo("octo/docs")
    assert repo is not None
    assert repo["doc_paths"] == ["README.md", "docs/**/*.md"]
    assert repo["webhook_id"] == 42
    assert repo["status"] == "listening"

    await store.upsert_monitored_repo(
        repo_full_name="octo/docs",
        owner="octo",
        name="docs",
        watch_branch="develop",
        doc_paths=["README.md"],
    )
    updated = await store.get_monitored_repo("octo/docs")
    assert updated["watch_branch"] == "develop"
    assert updated["doc_paths"] == ["README.md"]
    # Reconnecting without a hook id preserves the existing hook.
    assert updated["webhook_id"] == 42

    repos = await store.list_monitored_repos()
    assert [repo["repo_full_name"] for repo in repos] == ["octo/docs"]

    assert await store.clear_monitored_repos() == 1
    assert await store.list_monitored_repos() == []


@pytest.mark.asyncio
async def test_activity_run_lifecycle_and_stats(store):
    await store.create_activity_run(
        "delivery-1",
        "octo/docs",
        commit_sha="abc1234",
        commit_message="feat: add endpoint",
        author="octocat",
    )
    await store.update_activity_run(
        "delivery-1",
        status="pr_open",
        llm_calls=4,
        pr_url="https://github.com/octo/docs/pull/1",
        pr_number=1,
        evidence_table_md="| doc |",
        diff_preview={"file_path": "README.md", "added_lines": ["+new"]},
    )
    await store.create_activity_run("delivery-2", "octo/docs", status="no_drift")

    run = await store.get_activity_run("delivery-1")
    assert run["status"] == "pr_open"
    assert run["llm_calls"] == 4
    assert run["diff_preview"]["file_path"] == "README.md"

    runs = await store.list_activity_runs(repo_full_name="octo/docs")
    assert len(runs) == 2
    assert {item["delivery_id"] for item in runs} == {"delivery-1", "delivery-2"}

    counts = await store.get_run_counts_by_repo()
    assert counts["octo/docs"] == 2

    stats = await store.get_activity_stats()
    assert stats["runs_this_week"] == 2
    assert stats["skipped_zero_tokens"] == 1
    assert stats["prs_merged"] == 0


@pytest.mark.asyncio
async def test_user_settings_defaults_and_updates(store):
    defaults = await store.get_user_settings()
    assert defaults["require_reviewer_approval"] == 1
    assert defaults["skip_internal_changes"] == 1
    assert defaults["email_on_failed_runs"] == 0

    updated = await store.update_user_settings(
        github_username="octocat",
        require_reviewer_approval=0,
        email_on_failed_runs=1,
    )
    assert updated["github_username"] == "octocat"
    assert updated["require_reviewer_approval"] == 0
    assert updated["email_on_failed_runs"] == 1
    assert updated["skip_internal_changes"] == 1

    await store.clear_github_username()
    assert (await store.get_user_settings())["github_username"] is None
