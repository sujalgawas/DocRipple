"""Route-level tests for the frontend web API bridge."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.context_store.sqlite_store import SqliteContextStore
from src.contracts.schemas import (
    DocStyleSkill,
    MemoryNode,
    OnboardRepoResult,
    RepoMemoryMap,
)
from src.web_api.router import router


class FakeGitHubService:
    def __init__(self) -> None:
        self.token = "fake-token"
        self.deleted_webhooks: list[tuple[str, int]] = []

    async def get_authenticated_user(self) -> dict:
        return {
            "login": "octocat",
            "avatar_url": "https://avatars.example/octocat.png",
            "repo_count": 4,
        }

    async def list_user_repos(self) -> list[dict]:
        return [
            {
                "full_name": "octo/docs",
                "name": "docs",
                "owner_login": "octo",
                "private": False,
                "default_branch": "main",
                "language": "Python",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ]

    async def fetch_repo_snapshot(self, repo_full_name, branch, doc_globs):
        return (
            {"src/app.py": "def calc_total(items):\n    return sum(items)\n"},
            {"README.md": "# Docs\n\n## Billing\n\nold\n"},
        )

    async def install_repo_webhook(self, repo_full_name, webhook_url, secret):
        return 55

    async def get_repo(self, repo_full_name):
        return {
            "full_name": repo_full_name,
            "default_branch": "main",
            "language": "Python",
            "pushed_at": "2026-01-02T00:00:00Z",
        }

    async def get_latest_commit(self, repo_full_name, branch):
        return {
            "sha": "head456",
            "message": "feat: add endpoint",
            "author": "octocat",
            "parent_sha": "base123",
        }

    async def get_commit(self, repo_full_name, sha):
        return {
            "sha": sha,
            "message": "chosen commit",
            "author": "octocat",
            "parent_sha": "base123",
        }

    async def delete_repo_webhook(self, repo_full_name, hook_id):
        self.deleted_webhooks.append((repo_full_name, hook_id))


class FakeOnboardingService:
    def __init__(self, store: SqliteContextStore) -> None:
        self.store = store

    async def onboard_repository(self, repo_full_name, code_files, docs):
        skill = DocStyleSkill(
            repo_full_name=repo_full_name,
            tone_and_voice="Direct, concise, example-first.",
            heading_conventions=["Sentence case headings"],
            code_block_rules=["Tag code fences"],
            formatting_patterns=["Use tables"],
            skill_markdown="---\nname: test\n---\n# Skill\n",
            generated_at=datetime.now(UTC),
        )
        memory = RepoMemoryMap(
            repo_full_name=repo_full_name,
            nodes=[
                MemoryNode(
                    node_id="file:src/app.py",
                    repo_full_name=repo_full_name,
                    node_type="file",
                    name="app.py",
                    path="src/app.py",
                    summary="Application source",
                )
            ],
            edges=[],
            updated_at=datetime.now(UTC),
        )
        await self.store.save_style_skill(skill)
        await self.store.save_memory_map(memory)
        return OnboardRepoResult(
            repo_full_name=repo_full_name,
            style_skill=skill,
            memory_node_count=1,
            memory_edge_count=0,
            initial_code_doc_edges=1,
        )


@pytest.fixture
async def app(tmp_path, monkeypatch):
    store = SqliteContextStore(str(tmp_path / "router.db"))
    await store.initialize()

    fake_github = FakeGitHubService()
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.state.context_store = store
    test_app.state.github_service = fake_github
    test_app.state.onboarding_service = FakeOnboardingService(store)
    test_app.state.webhook_queue = asyncio.Queue()
    test_app.state.pipeline = SimpleNamespace(fetcher=SimpleNamespace(token=""))

    monkeypatch.setattr(settings, "PUBLIC_WEBHOOK_URL", "https://example.com/hook")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "")
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:5173")

    yield test_app, store, fake_github
    await store.close()


@pytest.mark.asyncio
async def test_auth_repos_connect_dashboard_and_context(app):
    test_app, store, _ = app
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        me = await client.get("/api/v1/auth/me")
        assert me.status_code == 200
        assert me.json() == {
            "connected": True,
            "username": "octocat",
            "avatar_url": "https://avatars.example/octocat.png",
            "plan": "free",
            "authorized_repos_count": 4,
        }

        repos = await client.get("/api/v1/github/repos")
        assert repos.status_code == 200
        assert repos.json()[0]["full_name"] == "octo/docs"

        connected = await client.post(
            "/api/v1/repos/connect",
            json={
                "repo_full_name": "octo/docs",
                "watch_branch": "main",
                "doc_paths": ["README.md", "docs/**/*.md"],
                "drift_action": "Open a pull request",
            },
        )
        assert connected.status_code == 200
        body = connected.json()
        assert body["status"] == "connected"
        assert body["webhook_url"] == "https://example.com/hook"
        assert body["memory_nodes_count"] == 1
        assert body["style_skill_summary"].startswith("Direct")

        repo = await store.get_monitored_repo("octo/docs")
        assert repo["webhook_id"] == 55
        assert repo["drift_action"] == "open_pr"

        await store.create_activity_run(
            "delivery-1",
            "octo/docs",
            commit_sha="head456",
            commit_message="feat: add endpoint",
            author="octocat",
            status="running",
        )
        await store.update_activity_run(
            "delivery-1", status="pr_open", llm_calls=2, pr_number=3
        )

        dashboard = await client.get("/api/v1/dashboard")
        assert dashboard.status_code == 200
        dashboard_body = dashboard.json()
        assert dashboard_body["stats"]["runs_this_week"] == 1
        assert dashboard_body["repositories"][0]["run_count"] == 1
        assert dashboard_body["latest_runs"][0]["delivery_id"] == "delivery-1"

        activity = await client.get("/api/v1/activity")
        assert activity.status_code == 200
        assert activity.json()["runs"][0]["pr_number"] == 3

        triggered = await client.post("/api/v1/repos/octo/docs/trigger")
        assert triggered.status_code == 200
        trigger_body = triggered.json()
        assert trigger_body["status"] == "enqueued"
        assert trigger_body["commit_sha"] == "head456"
        queued = test_app.state.webhook_queue.get_nowait()
        assert queued.head_sha == "head456"
        assert queued.base_sha == "base123"


@pytest.mark.asyncio
async def test_settings_and_disconnect(app):
    test_app, store, fake_github = app
    await store.upsert_monitored_repo(
        repo_full_name="octo/docs",
        owner="octo",
        name="docs",
        webhook_id=55,
    )

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        current = await client.get("/api/v1/settings")
        assert current.status_code == 200
        assert current.json()["require_reviewer_approval"] is True

        patched = await client.patch(
            "/api/v1/settings",
            json={
                "require_reviewer_approval": False,
                "skip_internal_changes": False,
                "email_on_failed_runs": True,
            },
        )
        assert patched.status_code == 200
        assert patched.json()["require_reviewer_approval"] is False
        assert patched.json()["skip_internal_changes"] is False
        assert patched.json()["email_on_failed_runs"] is True

        disconnected = await client.post("/api/v1/settings/disconnect")
        assert disconnected.status_code == 200
        assert disconnected.json()["removed_repositories"] == 1
        assert disconnected.json()["removed_webhooks"] == 1
        assert fake_github.deleted_webhooks == [("octo/docs", 55)]
        assert await store.list_monitored_repos() == []


@pytest.mark.asyncio
async def test_auth_login_redirects_without_oauth(app, monkeypatch):
    test_app, _, _ = app
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "")
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", follow_redirects=False
    ) as client:
        response = await client.get("/api/v1/auth/github/login")
    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:5173/repositories"


@pytest.mark.asyncio
async def test_auth_login_redirects_to_github_when_configured(app, monkeypatch):
    test_app, _, _ = app
    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "client-id")
    transport = ASGITransport(app=test_app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver", follow_redirects=False
    ) as client:
        response = await client.get("/api/v1/auth/github/login")
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://github.com/login/oauth/authorize?")
    assert "client_id=client-id" in location
    assert "state=" in location
