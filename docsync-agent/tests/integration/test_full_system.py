"""End-to-end integration tests for the Self-Updating Documentation Agent.

Verifies the complete flow from GitHub Webhook to worker execution, AST analysis,
drift computation, LangGraph orchestration, PR creation, and ContextStore persistence.
"""

from __future__ import annotations

import difflib
import hashlib
import hmac
import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from src.analyzer.service import ChangeAnalyzerService
from src.config import settings
from src.context_store.sqlite_store import SqliteContextStore
from src.drift.service import DriftEngineService
from src.ingest.router import router as ingest_router
from src.main import lifespan
from src.onboarding.router import router as onboarding_router
from src.orchestrator.config import OrchestratorConfig
from src.orchestrator.service import OrchestratorService
from src.pipeline import DocSyncPipeline, GitHubRepoFetcher


def make_diff(old: str, new: str, file_path: str) -> str:
    """Generate a realistic unified diff between two file contents."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
    )


OLD_BILLING = """def calc_total(items: list[int]) -> int:
    return sum(items)
"""

NEW_BILLING = """def calc_total(items: list[int], tax_rate: float = 0.05) -> int:
    return int(sum(items) * (1 + tax_rate))
"""

VALID_DIFF = make_diff(OLD_BILLING, NEW_BILLING, "src/billing.py")

OLD_UTILS = """def _secret_helper() -> int:
    return 42
"""

NEW_UTILS = """def _secret_helper() -> float:
    return 42.0
"""

INTERNAL_HELPER_DIFF = make_diff(OLD_UTILS, NEW_UTILS, "src/utils.py")


class MockRepoFetcher(GitHubRepoFetcher):
    """Fetcher that supplies predefined diffs and documentation."""

    def __init__(self, diff: str, docs: dict[str, str]) -> None:
        super().__init__(token="mock-token")
        self.diff = diff
        self.docs = docs

    async def fetch_diff(self, repo_full_name: str, base_sha: str, head_sha: str) -> str:
        return self.diff

    async def fetch_docs(self, repo_full_name: str, head_sha: str) -> dict[str, str]:
        return self.docs


class MockLLMClient:
    """Mock LLM client tracking calls and returning valid pipeline outputs."""

    def __init__(self, plan_doc: str, plan_heading: str, plan_symbol: str) -> None:
        self.calls: list[tuple[str, str]] = []
        self.plan_doc = plan_doc
        self.plan_heading = plan_heading
        self.plan_symbol = plan_symbol

    async def generate_text(self, system_prompt: str, user_prompt: str) -> str:
        self.calls.append((system_prompt, user_prompt))
        sys_lower = system_prompt.lower()
        if "planning agent" in sys_lower:
            return json.dumps([
                {
                    "doc_path": self.plan_doc,
                    "heading": self.plan_heading,
                    "target_symbols": [self.plan_symbol],
                    "instructions": f"Update {self.plan_symbol} usage",
                }
            ])
        if "reviewer" in sys_lower:
            return "APPROVED"
        # Writer output
        return (
            f"<!-- doc-anchor: {self.plan_heading.lower()} -->\n\n"
            f"Call `{self.plan_symbol}` with new parameters.\n\n"
            f"```python\n"
            f"res = {self.plan_symbol}([10, 20], tax_rate=0.08)\n"
            f"```\n"
        )


class MockGitHubPublisher:
    """Mock GitHub publisher recording PR creation."""

    def __init__(self) -> None:
        self.created_prs: list[dict[str, Any]] = []

    async def create_docs_pr(
        self,
        repo_full_name: str,
        base_sha: str,
        branch_name: str,
        updated_docs: dict[str, str],
        pr_title: str,
        pr_body: str,
    ) -> tuple[str, int]:
        self.created_prs.append({
            "repo": repo_full_name,
            "branch": branch_name,
            "title": pr_title,
            "updated_docs": updated_docs,
        })
        return "https://github.com/org/repo/pull/101", 101


def sign(payload_bytes: bytes, secret: str = "dev-secret") -> str:
    """Compute GitHub HMAC-SHA256 signature."""
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
def app_with_mocks() -> tuple[FastAPI, MockLLMClient, MockGitHubPublisher, MockRepoFetcher]:
    """Build a configured test application with in-memory stores and mocks."""
    settings.SQLITE_DB_PATH = ":memory:"
    settings.CHECKPOINT_DB_PATH = ":memory:"

    test_app = FastAPI(
        title="DocSync Agent Test",
        lifespan=lifespan,
    )
    test_app.include_router(ingest_router)
    test_app.include_router(onboarding_router)

    from src.main import demo_run, get_run_status, health

    test_app.add_api_route("/health", health, methods=["GET"], tags=["system"])
    test_app.add_api_route(
        "/api/v1/runs/{delivery_id}", get_run_status, methods=["GET"], tags=["runs"]
    )
    test_app.add_api_route(
        "/api/v1/demo/run", demo_run, methods=["POST"], tags=["demo"]
    )

    docs = {
        "README.md": (
            "## Billing\n\n"
            "<!-- doc-anchor: billing -->\n\n"
            "Calculates total invoice.\n\n"
            "```python\n"
            "from src.billing import calc_total\n"
            "total = calc_total([10, 20])\n"
            "```\n"
        )
    }

    mock_llm = MockLLMClient(
        plan_doc="README.md",
        plan_heading="Billing",
        plan_symbol="calc_total",
    )
    mock_gh = MockGitHubPublisher()
    mock_fetcher = MockRepoFetcher(diff=VALID_DIFF, docs=docs)

    return test_app, mock_llm, mock_gh, mock_fetcher


@pytest.mark.asyncio
async def test_webhook_to_worker_e2e(app_with_mocks):
    """1. Webhook-to-Worker E2E test verifying full flow to PR with Evidence Table."""
    app, mock_llm, mock_gh, mock_fetcher = app_with_mocks

    async with app.router.lifespan_context(app):
        store: SqliteContextStore = app.state.context_store
        orch_config = OrchestratorConfig(
            checkpoint_db_path=":memory:",
            max_retries=2,
        )
        orchestrator = OrchestratorService(
            llm_client=mock_llm,
            github_publisher=mock_gh,
            context_store=store,
            config=orch_config,
        )

        pipeline = DocSyncPipeline(
            analyzer=ChangeAnalyzerService(),
            drift_engine=DriftEngineService(),
            orchestrator=orchestrator,
            context_store=store,
            fetcher=mock_fetcher,
        )
        app.state.pipeline = pipeline
        app.state.worker.pipeline = pipeline

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            delivery_id = f"e2e-delivery-{uuid4().hex[:8]}"
            payload = {
                "ref": "refs/heads/main",
                "before": "1111111111111111111111111111111111111111",
                "after": "2222222222222222222222222222222222222222",
                "repository": {"full_name": "org/repo"},
            }
            body = json.dumps(payload).encode("utf-8")

            # 1. Post webhook push event
            resp = await client.post(
                "/api/v1/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Delivery": delivery_id,
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": sign(body),
                },
            )
            assert resp.status_code == 202
            assert resp.json()["status"] == "enqueued"

            # 2. Wait for worker to finish processing
            await app.state.webhook_queue.join()

            # 3. Query run result
            run_resp = await client.get(f"/api/v1/runs/{delivery_id}")
            assert run_resp.status_code == 200
            run_data = run_resp.json()

            assert run_data["delivery_id"] == delivery_id
            assert run_data["pr_url"] == "https://github.com/org/repo/pull/101"
            assert run_data["pr_number"] == 101
            assert run_data["verification_status"] == "passed"
            assert "calc_total" in run_data["evidence_table_md"]

            # 4. Verify ContextStore persistence
            edges = await store.get_edges_for_symbols("org/repo", ["calc_total"])
            assert len(edges) >= 1
            assert edges[0].symbol_name == "calc_total"
            assert edges[0].doc_path == "README.md"


@pytest.mark.asyncio
async def test_no_drift_early_exit(app_with_mocks):
    """2. No-Drift Early Exit test verifying 0 LLM calls and no PR when symbols aren't in docs."""
    app, mock_llm, mock_gh, mock_fetcher = app_with_mocks
    mock_fetcher.diff = INTERNAL_HELPER_DIFF
    mock_fetcher.docs = {"README.md": "## Public API\n\nNo internal helpers documented.\n"}

    async with app.router.lifespan_context(app):
        store: SqliteContextStore = app.state.context_store
        orch_config = OrchestratorConfig(
            checkpoint_db_path=":memory:",
            max_retries=2,
        )
        orchestrator = OrchestratorService(
            llm_client=mock_llm,
            github_publisher=mock_gh,
            context_store=store,
            config=orch_config,
        )

        pipeline = DocSyncPipeline(
            analyzer=ChangeAnalyzerService(),
            drift_engine=DriftEngineService(),
            orchestrator=orchestrator,
            context_store=store,
            fetcher=mock_fetcher,
        )
        app.state.pipeline = pipeline
        app.state.worker.pipeline = pipeline

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            delivery_id = f"no-drift-{uuid4().hex[:8]}"
            payload = {
                "ref": "refs/heads/main",
                "before": "3333333333333333333333333333333333333333",
                "after": "4444444444444444444444444444444444444444",
                "repository": {"full_name": "org/repo"},
            }
            body = json.dumps(payload).encode("utf-8")

            resp = await client.post(
                "/api/v1/webhooks/github",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-GitHub-Delivery": delivery_id,
                    "X-GitHub-Event": "push",
                    "X-Hub-Signature-256": sign(body),
                },
            )
            assert resp.status_code == 202

            await app.state.webhook_queue.join()

            # Zero LLM tokens spent — mock_llm was never invoked!
            assert len(mock_llm.calls) == 0
            assert len(mock_gh.created_prs) == 0

            # Run was not published
            run_resp = await client.get(f"/api/v1/runs/{delivery_id}")
            assert run_resp.status_code == 404


@pytest.mark.asyncio
async def test_health_and_demo_endpoints(app_with_mocks):
    """3. Test /health and /api/v1/demo/run endpoints."""
    app, mock_llm, mock_gh, _ = app_with_mocks

    async with app.router.lifespan_context(app):
        store: SqliteContextStore = app.state.context_store
        orch_config = OrchestratorConfig(
            checkpoint_db_path=":memory:",
            max_retries=2,
        )
        orchestrator = OrchestratorService(
            llm_client=mock_llm,
            github_publisher=mock_gh,
            context_store=store,
            config=orch_config,
        )

        pipeline = DocSyncPipeline(
            analyzer=ChangeAnalyzerService(),
            drift_engine=DriftEngineService(),
            orchestrator=orchestrator,
            context_store=store,
        )
        app.state.pipeline = pipeline

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            # 1. Health
            health_resp = await client.get("/health")
            assert health_resp.status_code == 200
            assert health_resp.json()["status"] == "ok"
            assert "queue_size" in health_resp.json()

            # 2. Demo Run
            demo_payload = {
                "delivery_id": f"demo-{uuid4().hex[:8]}",
                "repo_full_name": "demo/repo",
                "raw_diff": VALID_DIFF,
                "docs": {
                    "README.md": (
                        "## Billing\n\n"
                        "<!-- doc-anchor: billing -->\n\n"
                        "Calculates total invoice.\n\n"
                        "```python\n"
                        "from src.billing import calc_total\n"
                        "total = calc_total([10, 20])\n"
                        "```\n"
                    )
                },
            }
            demo_resp = await client.post("/api/v1/demo/run", json=demo_payload)
            assert demo_resp.status_code == 200
            data = demo_resp.json()
            assert len(data["change_report"]["changed_symbols"]) >= 1
            assert len(data["drift_report"]["impacted_sections"]) >= 1
            assert data["publish_result"] is not None
            assert data["publish_result"]["pr_number"] == 101


@pytest.mark.asyncio
async def test_stage0_onboarding_feeds_style_and_memory_into_orchestrator(app_with_mocks):
    """Stage 0 runs first; Stage 4 receives the skill and 2-hop memory subgraph."""
    app, mock_llm, mock_gh, _ = app_with_mocks

    onboarding_docs = {
        "README.md": (
            "# Billing Service\n\n"
            "## Overview\n\n"
            "Use the billing API to calculate invoice totals. Run the example below.\n\n"
            "| Option | Meaning |\n"
            "| --- | --- |\n"
            "| `--tax` | Tax rate |\n\n"
            "```bash\n"
            "curl -X POST http://localhost:8000/billing\n"
            "```\n\n"
            "```python\n"
            "from src.billing import calc_total\n"
            "total = calc_total([10, 20], tax_rate=0.08)\n"
            "```\n\n"
            "<!-- doc-anchor: calc_total -->\n\n"
            "## Billing\n\n"
            "Calculates invoice totals with `calc_total`.\n"
        )
    }
    onboarding_code = {
        "src/billing.py": NEW_BILLING,
        "src/formatting.py": (
            '"""Formatting helpers."""\n\n\n'
            "def format_amount(value: float) -> str:\n"
            '    """Format an amount for display."""\n'
            '    return f"${value:.2f}"\n'
        ),
    }

    async with app.router.lifespan_context(app):
        store: SqliteContextStore = app.state.context_store
        orchestrator = OrchestratorService(
            llm_client=mock_llm,
            github_publisher=mock_gh,
            context_store=store,
            config=OrchestratorConfig(checkpoint_db_path=":memory:", max_retries=2),
        )
        pipeline = DocSyncPipeline(
            analyzer=ChangeAnalyzerService(),
            drift_engine=DriftEngineService(),
            orchestrator=orchestrator,
            context_store=store,
        )
        app.state.pipeline = pipeline
        app.state.worker.pipeline = pipeline

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            onboard_resp = await client.post(
                "/api/v1/repos/onboard",
                json={
                    "repo_full_name": "org/repo",
                    "code_files": onboarding_code,
                    "docs": onboarding_docs,
                },
            )
            assert onboard_resp.status_code == 200
            onboard_data = onboard_resp.json()
            assert onboard_data["style_skill"]["skill_markdown"].startswith("---")
            assert onboard_data["initial_code_doc_edges"] >= 1

            skill_resp = await client.get("/api/v1/repos/org/repo/skill")
            assert skill_resp.status_code == 200

            memory_resp = await client.get(
                "/api/v1/repos/org/repo/memory",
                params={"symbols": "calc_total"},
            )
            assert memory_resp.status_code == 200
            memory_ids = {node["node_id"] for node in memory_resp.json()["nodes"]}
            assert "symbol:src/billing.py::calc_total" in memory_ids

            demo_resp = await client.post(
                "/api/v1/demo/run",
                json={
                    "delivery_id": f"stage0-{uuid4().hex[:8]}",
                    "repo_full_name": "org/repo",
                    "raw_diff": VALID_DIFF,
                    "docs": {
                        "README.md": (
                            "## Billing\n\n"
                            "<!-- doc-anchor: billing -->\n\n"
                            "Calculates total invoice.\n\n"
                            "```python\n"
                            "total = calc_total([10, 20])\n"
                            "```\n"
                        )
                    },
                },
            )
            assert demo_resp.status_code == 200
            assert demo_resp.json()["publish_result"]["pr_number"] == 101

            updated_memory = await client.get(
                "/api/v1/repos/org/repo/memory",
                params={"symbols": "calc_total"},
            )
            assert updated_memory.status_code == 200
            updated_nodes = {
                node["node_id"]: node for node in updated_memory.json()["nodes"]
            }
            symbol_metadata = json.loads(
                updated_nodes["symbol:src/billing.py::calc_total"]["metadata_json"]
            )
            assert "last_published_delivery" in symbol_metadata
            doc_node = next(
                node
                for node in updated_nodes.values()
                if node["node_type"] == "doc_section"
                and node["path"] == "README.md"
                and node["name"] == "Billing"
            )
            assert "last_published_delivery" in json.loads(doc_node["metadata_json"])

    planner_calls = [
        (system, user)
        for system, user in mock_llm.calls
        if "planning agent" in system.lower()
    ]
    assert planner_calls
    planner_prompt = planner_calls[-1][1]
    assert "Repository Memory Subgraph" in planner_prompt
    assert "Connected documentation sections" in planner_prompt
    assert "README.md#Billing" in planner_prompt

    writer_systems = [
        system for system, _ in mock_llm.calls if "documentation writer" in system.lower()
    ]
    assert writer_systems
    assert "Repository DocStyleSkill" in writer_systems[-1]
    assert "org-repo-doc-style" in writer_systems[-1]

    reviewer_systems = [
        system for system, _ in mock_llm.calls if "documentation reviewer" in system.lower()
    ]
    assert reviewer_systems
    assert "DocStyleSkill" in reviewer_systems[-1]

