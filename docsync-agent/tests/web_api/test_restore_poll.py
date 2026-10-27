"""Cold-start recovery, automatic commit polling, and webhook resilience."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.context_store.sqlite_store import SqliteContextStore
from src.contracts.schemas import PublishResult
from src.ingest.router import router as ingest_router
from src.web_api.router import router as web_api_router


class FakeGitHubService:
    """Minimal GitHub surface used by the poll/connect endpoints."""

    def __init__(self) -> None:
        self.token = "test-token"
        self.latest: dict[str, dict] = {}

    async def get_latest_commit(self, repo_full_name: str, branch: str) -> dict:
        if repo_full_name in self.latest:
            return self.latest[repo_full_name]
        return {
            "sha": "a" * 40,
            "parent_sha": "b" * 40,
            "message": "feat: add endpoint",
            "author": "octocat",
        }

    async def get_repo(self, repo_full_name: str) -> dict:
        return {
            "full_name": repo_full_name,
            "default_branch": "main",
            "language": "Python",
            "pushed_at": "2026-01-01T00:00:00Z",
        }


class FakePipeline:
    def __init__(self) -> None:
        self.jobs = []

    async def process_webhook(self, job):
        self.jobs.append(job)
        return PublishResult(
            delivery_id=job.delivery_id,
            pr_url=f"https://github.com/{job.repo_full_name}/pull/7",
            pr_number=7,
            evidence_table_md="| Doc File | Section |\n|---|---|",
        )


@pytest.fixture
async def store(tmp_path: SqliteContextStore):
    s = SqliteContextStore(str(tmp_path / "poll.db"))
    await s.initialize()
    yield s
    await s.close()


@pytest.fixture
def app(store: SqliteContextStore) -> tuple[FastAPI, FakeGitHubService, FakePipeline]:
    test_app = FastAPI()
    test_app.include_router(web_api_router)
    test_app.include_router(ingest_router)
    github = FakeGitHubService()
    pipeline = FakePipeline()
    test_app.state.context_store = store
    test_app.state.github_service = github
    test_app.state.pipeline = pipeline
    test_app.state.onboarding_service = None
    return test_app, github, pipeline


def _sign(body: bytes) -> str:
    digest = hmac.new(
        settings.GITHUB_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return f"sha256={digest}"


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}


# ── Restore ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_reinserts_repositories(app) -> None:
    test_app, _, _ = app
    payload = {
        "repos": [
            {
                "repo_full_name": "acme/docs",
                "watch_branch": "main",
                "doc_paths": ["README.md"],
                "drift_action": "open_pr",
                "status": "listening",
                "last_processed_sha": "abc123",
            },
            {
                "repo_full_name": "acme/api",
                "watch_branch": "develop",
                "doc_paths": ["docs/**/*.md"],
                "drift_action": "open_pr",
                "status": "listening",
                "last_processed_sha": None,
            },
        ]
    }

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post("/api/v1/repos/restore", json=payload)
        dashboard = await client.get("/api/v1/dashboard")

    assert response.status_code == 200
    assert set(response.json()["restored"]) == {"acme/docs", "acme/api"}
    names = {repo["repo_full_name"] for repo in dashboard.json()["repositories"]}
    assert names == {"acme/docs", "acme/api"}
    restored = {
        repo["repo_full_name"]: repo for repo in response.json()["repositories"]
    }
    assert restored["acme/docs"]["last_processed_sha"] == "abc123"


# ── Polling ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_triggers_new_commit(app, store) -> None:
    test_app, github, pipeline = app
    await store.upsert_monitored_repo(
        repo_full_name="acme/docs",
        owner="acme",
        name="docs",
        watch_branch="main",
        status="listening",
        last_processed_sha="old-sha",
    )
    github.latest["acme/docs"] = {
        "sha": "f" * 40,
        "parent_sha": "e" * 40,
        "message": "feat: new route",
        "author": "octocat",
    }

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/repos/poll",
            headers=_auth(),
            json={
                "repos": [
                    {
                        "repo_full_name": "acme/docs",
                        "watch_branch": "main",
                        "last_processed_sha": "old-sha",
                        "status": "listening",
                    }
                ]
            },
        )

    body = response.json()
    assert response.status_code == 200
    assert body["triggered"] == ["acme/docs"]
    assert body["watermarks"]["acme/docs"] == "f" * 40
    assert len(body["new_runs"]) == 1
    assert body["new_runs"][0]["status"] == "pr_open"
    assert [job.delivery_id for job in pipeline.jobs] == ["auto-" + "f" * 12]

    stored = await store.get_monitored_repo("acme/docs")
    assert stored is not None
    assert stored["last_processed_sha"] == "f" * 40


@pytest.mark.asyncio
async def test_poll_ignores_docsync_commit(app, store) -> None:
    test_app, github, pipeline = app
    await store.upsert_monitored_repo(
        repo_full_name="acme/docs",
        owner="acme",
        name="docs",
        last_processed_sha="old-sha",
    )
    github.latest["acme/docs"] = {
        "sha": "9" * 40,
        "parent_sha": "8" * 40,
        "message": "docs: sync for delivery abc",
        "author": "docripple-bot",
    }

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/repos/poll", headers=_auth(), json={"repos": []}
        )

    body = response.json()
    assert body["triggered"] == []
    assert body["skipped"][0]["reason"] == "doc-sync commit"
    assert body["watermarks"]["acme/docs"] == "9" * 40
    assert pipeline.jobs == []


@pytest.mark.asyncio
async def test_poll_skips_already_recorded_commit(app, store) -> None:
    test_app, github, pipeline = app
    sha = "d" * 40
    await store.upsert_monitored_repo(
        repo_full_name="acme/docs",
        owner="acme",
        name="docs",
        last_processed_sha="old-sha",
    )
    await store.create_activity_run(
        delivery_id="manual-existing",
        repo_full_name="acme/docs",
        commit_sha=sha,
        status="no_drift",
    )
    github.latest["acme/docs"] = {
        "sha": sha,
        "parent_sha": "c" * 40,
        "message": "chore: tidy",
        "author": "octocat",
    }

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/repos/poll", headers=_auth(), json={"repos": []}
        )

    body = response.json()
    assert body["triggered"] == []
    assert body["skipped"][0]["reason"] == "already recorded"
    assert pipeline.jobs == []


# ── Webhook resilience ───────────────────────────────────────────────────


def _push_payload(repo: str, ref: str, head: str, base: str) -> dict:
    return {
        "ref": ref,
        "before": base,
        "after": head,
        "repository": {"full_name": repo},
        "head_commit": {"message": "feat: x", "author": {"name": "octocat"}},
    }


@pytest.mark.asyncio
async def test_webhook_ignores_agent_branches(app, store) -> None:
    test_app, _, pipeline = app
    body = json.dumps(
        _push_payload("acme/docs", "refs/heads/docsync/abc", "1" * 40, "2" * 40)
    ).encode()

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Delivery": "deliv-agent-branch",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _sign(body),
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "event_ignored"
    assert pipeline.jobs == []


@pytest.mark.asyncio
async def test_webhook_auto_registers_repo_and_runs_inline(app, store) -> None:
    test_app, _, pipeline = app
    body = json.dumps(
        _push_payload("cold/start-repo", "refs/heads/main", "3" * 40, "4" * 40)
    ).encode()

    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/webhooks/github",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-GitHub-Delivery": "deliv-cold-start",
                "X-GitHub-Event": "push",
                "X-Hub-Signature-256": _sign(body),
            },
        )

    assert response.status_code == 202
    assert response.json()["status"] == "enqueued"
    assert [job.head_sha for job in pipeline.jobs] == ["3" * 40]

    registered = await store.get_monitored_repo("cold/start-repo")
    assert registered is not None
    assert registered["status"] == "listening"
    assert registered["watch_branch"] == "main"
