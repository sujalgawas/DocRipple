"""Deployment tests for health probes, CORS, embeddings, and demo seeding."""

from __future__ import annotations

import builtins

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import settings
from src.context_store.sqlite_store import SqliteContextStore
from src.drift import embed_fallback
from src.main import SEED_REPO_FULL_NAME, app, seed_default_repository


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/", "/health", "/api/v1/health"])
async def test_health_supports_get_and_head(path: str) -> None:
    """Render, Vercel, and uptime pingers use /, /health, or /api/v1/health with GET or HEAD."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        get_response = await client.get(path)
        assert get_response.status_code == 200
        assert get_response.json() == {
            "status": "ok",
            "service": "docripple-api",
        }

        head_response = await client.head(path)
        assert head_response.status_code == 200
        assert head_response.content == b""


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "origin",
    [
        "https://docripple.vercel.app",
        "https://docsync-agent-lyart.vercel.app",
        "https://docripple-git-main-sujalgawas.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
)
async def test_cors_allows_configured_and_preview_origins(origin: str) -> None:
    """Configured origins and Vercel previews pass preflight checks."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-credentials"] == "true"


@pytest.mark.asyncio
async def test_cors_ignores_unknown_origin() -> None:
    """Origins outside the allow-list must not receive CORS headers."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.options(
            "/health",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.asyncio
async def test_unhandled_exception_returns_cors_readable_json() -> None:
    """A 500 must stay readable from the browser instead of a CORS failure."""
    from fastapi import APIRouter

    boom = APIRouter()

    @boom.get("/__boom_for_test")
    async def _boom() -> dict:
        raise RuntimeError("kaboom")

    app.include_router(boom)
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.get(
                "/__boom_for_test",
                headers={"Origin": "https://docripple.vercel.app"},
            )
    finally:
        app.router.routes = [
            route
            for route in app.router.routes
            if getattr(route, "path", None) != "/__boom_for_test"
        ]

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.asyncio
async def test_tfidf_mode_never_imports_fastembed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default Render mode must stay under the 512 MB limit."""
    monkeypatch.setattr(settings, "EMBEDDING_MODE", "tfidf")

    original_import = builtins.__import__
    attempts: list[str] = []

    def guarded_import(
        name: str,
        globals_: dict | None = None,
        locals_: dict | None = None,
        fromlist: tuple | None = (),
        level: int = 0,
    ):
        if name == "fastembed" or name.startswith("fastembed."):
            attempts.append(name)
            raise AssertionError("fastembed must not be imported in tfidf mode")
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    embedder = embed_fallback._build_default_embedder()
    assert embedder is embed_fallback.fallback_embed
    assert attempts == []


@pytest.mark.asyncio
async def test_fastembed_mode_falls_back_when_package_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Opt-in fastembed mode degrades to TF-IDF when the extra is missing."""
    monkeypatch.setattr(settings, "EMBEDDING_MODE", "fastembed")

    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals_: dict | None = None,
        locals_: dict | None = None,
        fromlist: tuple | None = (),
        level: int = 0,
    ):
        if name == "fastembed" or name.startswith("fastembed."):
            raise ImportError("fastembed is not installed")
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    assert embed_fallback._build_default_embedder() is embed_fallback.fallback_embed


@pytest.mark.asyncio
async def test_auth_config_callback_uses_request_host() -> None:
    """Deployed origins must never advertise a localhost OAuth callback."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="https://docripple.vercel.app"
    ) as client:
        response = await client.get("/api/v1/auth/config")

    assert response.status_code == 200
    callback_url = response.json()["callback_url"]
    assert "docripple.vercel.app" in callback_url
    assert "localhost" not in callback_url


def test_public_webhook_url_defaults_on_vercel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On Vercel, default to the Vercel deployment URLs and strip localhost."""
    import importlib

    import src.config as config_module

    monkeypatch.setenv("VERCEL", "1")
    try:
        reloaded = importlib.reload(config_module)
        assert (
            reloaded.AppSettings().PUBLIC_WEBHOOK_URL
            == "https://docsync-agent-lyart.vercel.app/api/v1/webhooks/github"
        )
        assert (
            reloaded.AppSettings().FRONTEND_URL == "https://docripple.vercel.app"
        )
    finally:
        monkeypatch.delenv("VERCEL", raising=False)
        importlib.reload(config_module)


@pytest.mark.asyncio
async def test_seed_default_repository_is_idempotent(tmp_path) -> None:
    """Cold boots populate the demo workspace exactly once."""
    store = SqliteContextStore(str(tmp_path / "seed.db"))
    await store.initialize()
    try:
        assert await seed_default_repository(store) is True
        assert await seed_default_repository(store) is False

        repos = await store.list_monitored_repos()
        assert [repo["repo_full_name"] for repo in repos] == [SEED_REPO_FULL_NAME]
        assert repos[0]["watch_branch"] == "main"

        runs = await store.list_activity_runs(repo_full_name=SEED_REPO_FULL_NAME)
        assert [run["delivery_id"] for run in runs] == [
            "seed-docripple-0003",
            "seed-docripple-0002",
            "seed-docripple-0001",
        ]
        assert {run["status"] for run in runs} == {
            "merged",
            "no_drift",
            "pr_open",
        }
        assert any(run["pr_number"] == 13 for run in runs)

        skill = await store.get_style_skill(SEED_REPO_FULL_NAME)
        assert skill is not None
        assert skill.skill_markdown.startswith("# SKILL: DocRipple")

        memory = await store.get_memory_map(SEED_REPO_FULL_NAME)
        assert memory.nodes
        assert memory.edges
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_lifespan_never_raises_on_startup_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Startup exceptions must never prevent lifespan from yielding."""
    from fastapi import FastAPI
    from src.main import lifespan

    test_fastapi = FastAPI(lifespan=lifespan)

    orig_init = SqliteContextStore.__init__
    called = False

    def failing_init(self, db_path="docsync_context.db"):
        nonlocal called
        if not called:
            called = True
            raise RuntimeError("Simulated startup disk failure")
        orig_init(self, db_path)

    monkeypatch.setattr(SqliteContextStore, "__init__", failing_init)

    async with lifespan(test_fastapi):
        assert test_fastapi.state.context_store is not None
        assert test_fastapi.state.context_store._db_path == ":memory:"
