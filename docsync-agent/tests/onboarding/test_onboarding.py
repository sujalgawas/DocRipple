"""Unit and API tests for Stage 0 repository onboarding."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from src.context_store.sqlite_store import SqliteContextStore
from src.contracts.schemas import DocStyleSkill
from src.onboarding.memory_builder import RepoMemoryMapBuilder
from src.onboarding.router import router as onboarding_router
from src.onboarding.service import OnboardingService
from src.onboarding.style_analyzer import DocStyleSkillGenerator

REPO = "acme/billing-service"

CODE_FILES = {
    "src/billing.py": '''"""Billing helpers."""

from src.utils import format_amount


def calc_total(items: list[int], tax_rate: float = 0.05) -> int:
    """Calculate the invoice total with tax."""
    return int(sum(items) * (1 + tax_rate))


def apply_discount(total: int, percent: int) -> int:
    """Apply a percentage discount to a total."""
    return total - int(total * percent / 100)
''',
    "src/utils.py": '''"""Formatting utilities."""


def format_amount(value: float) -> str:
    """Format a numeric amount as currency."""
    return f"${value:.2f}"
''',
}

DOCS = {
    "README.md": """# Billing Service

## Overview

Use the billing service to calculate invoice totals. Run the quickstart below.

| Option | Meaning |
| --- | --- |
| `--tax` | Tax rate |

```bash
curl -X POST http://localhost:8000/billing
```

```python
from src.billing import calc_total

total = calc_total([10, 20], tax_rate=0.08)
```

<!-- doc-anchor: calc_total -->

## API

Call `calc_total` to compute a total.
""",
    "docs/formatting.md": """# Formatting

## Currency values

Use `format_amount` for display values.
""",
}


@pytest.mark.asyncio
async def test_docstyle_skill_captures_repo_conventions():
    generator = DocStyleSkillGenerator()
    skill = await generator.generate(REPO, DOCS)

    assert isinstance(skill, DocStyleSkill)
    assert skill.repo_full_name == REPO
    assert "tutorial-first" in skill.tone_and_voice or "Direct" in skill.tone_and_voice
    assert any("ATX" in rule for rule in skill.heading_conventions)
    assert any("`bash`" in rule for rule in skill.code_block_rules)
    assert any("`python`" in rule for rule in skill.code_block_rules)
    assert any("pipe tables" in rule.lower() for rule in skill.formatting_patterns)
    assert any("doc-anchor" in rule for rule in skill.formatting_patterns)

    markdown = skill.skill_markdown
    assert markdown.startswith("---\nname: acme-billing-service-doc-style")
    assert "# Billing Service" not in markdown  # styles are rules, not copied docs
    assert "## Heading conventions" in markdown
    assert "`bash`" in markdown
    assert "`python`" in markdown
    assert "pipe tables" in markdown
    assert "doc-anchor" in markdown
    assert "##" in markdown


@pytest.mark.asyncio
async def test_memory_builder_creates_and_persists_all_node_types(tmp_path):
    store = SqliteContextStore(str(tmp_path / "memory.db"))
    await store.initialize()
    try:
        service = OnboardingService(context_store=store)
        result = await service.onboard_repository(REPO, CODE_FILES, DOCS)

        assert result.memory_node_count >= 8
        assert result.memory_edge_count >= 7
        assert result.initial_code_doc_edges >= 2

        skill = await store.get_style_skill(REPO)
        assert skill is not None
        assert skill.skill_markdown == result.style_skill.skill_markdown

        memory_map = await store.get_memory_subgraph(REPO, [])
        node_types = {node.node_type for node in memory_map.nodes}
        assert node_types == {"module", "file", "symbol", "doc_section"}

        relations = {edge.relation for edge in memory_map.edges}
        assert {"CONTAINS", "DEFINES", "IMPORTS", "DOCUMENTED_IN"} <= relations

        node_ids = {node.node_id for node in memory_map.nodes}
        assert "module:src" in node_ids
        assert "file:src/billing.py" in node_ids
        assert "symbol:src/billing.py::calc_total" in node_ids
        assert "doc:README.md#API" in node_ids

        edges = await store.get_edges_for_symbols(REPO, ["calc_total"])
        assert edges
        assert any(
            edge.doc_path == "README.md"
            and edge.section_heading == "Overview"
            and edge.anchor_type == "explicit_anchor"
            for edge in edges
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_memory_subgraph_traverses_two_hops(tmp_path):
    store = SqliteContextStore(str(tmp_path / "subgraph.db"))
    await store.initialize()
    try:
        service = OnboardingService(context_store=store)
        await service.onboard_repository(REPO, CODE_FILES, DOCS)

        subgraph = await store.get_memory_subgraph(REPO, ["calc_total"], max_hops=2)
        node_ids = {node.node_id for node in subgraph.nodes}

        # Seed symbol, its file, sibling symbol at hop 2, parent module, and doc.
        assert "symbol:src/billing.py::calc_total" in node_ids
        assert "file:src/billing.py" in node_ids
        assert "symbol:src/billing.py::apply_discount" in node_ids
        assert "module:src" in node_ids
        assert "doc:README.md#API" in node_ids
        assert "doc:README.md#Overview" in node_ids

        # A symbol reached through IMPORTS is 3 hops away from the seed.
        assert "symbol:src/utils.py::format_amount" not in node_ids

        # All returned edges stay inside the induced subgraph.
        for edge in subgraph.edges:
            assert edge.source_id in node_ids
            assert edge.target_id in node_ids
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_onboarding_router_endpoints(tmp_path):
    store = SqliteContextStore(str(tmp_path / "api.db"))
    await store.initialize()

    app = FastAPI()
    app.include_router(onboarding_router)
    app.state.context_store = store
    app.state.onboarding_service = OnboardingService(context_store=store)

    transport = ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            onboard = await client.post(
                "/api/v1/repos/onboard",
                json={
                    "repo_full_name": REPO,
                    "code_files": CODE_FILES,
                    "docs": DOCS,
                },
            )
            assert onboard.status_code == 200
            payload = onboard.json()
            assert payload["repo_full_name"] == REPO
            assert payload["memory_node_count"] > 0
            assert payload["style_skill"]["skill_markdown"].startswith("---")

            skill = await client.get("/api/v1/repos/acme/billing-service/skill")
            assert skill.status_code == 200
            assert skill.json()["skill_markdown"] == payload["style_skill"]["skill_markdown"]

            memory = await client.get("/api/v1/repos/acme/billing-service/memory")
            assert memory.status_code == 200
            memory_data = memory.json()
            assert {node["node_type"] for node in memory_data["nodes"]} == {
                "module",
                "file",
                "symbol",
                "doc_section",
            }

            subgraph = await client.get(
                "/api/v1/repos/acme/billing-service/memory",
                params={"symbols": "calc_total"},
            )
            assert subgraph.status_code == 200
            subgraph_ids = {node["node_id"] for node in subgraph.json()["nodes"]}
            assert subgraph_ids
            assert len(subgraph_ids) < len(memory_data["nodes"])
            assert "symbol:src/billing.py::calc_total" in subgraph_ids
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_repo_memory_builder_returns_map_and_edges():
    result = await RepoMemoryMapBuilder().build_with_edges(REPO, CODE_FILES, DOCS)
    assert result.memory_map.repo_full_name == REPO
    assert any(edge.relation == "IMPORTS" for edge in result.memory_map.edges)
    assert result.code_doc_edges


@pytest.mark.asyncio
async def test_memory_builder_indexes_cli_flags_and_config_vars():
    code = {
        "src/cli.py": '''"""CLI entrypoint."""

import os

API_KEY = os.getenv("API_KEY")
TIMEOUT_SECONDS = 30


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", action="store_true")
    return parser
''',
    }
    docs = {
        "README.md": (
            "## Configuration\n\n"
            "Set `API_KEY` and `TIMEOUT_SECONDS`, then pass `--verbose`.\n"
        )
    }

    result = await RepoMemoryMapBuilder().build_with_edges(REPO, code, docs)
    symbols = {
        node.name: node
        for node in result.memory_map.nodes
        if node.node_type == "symbol"
    }
    assert symbols["--verbose"].node_id == "symbol:src/cli.py::--verbose"
    assert "API_KEY" in symbols
    assert "TIMEOUT_SECONDS" in symbols

    documented = {
        (edge.source_id, edge.target_id)
        for edge in result.memory_map.edges
        if edge.relation == "DOCUMENTED_IN"
    }
    assert (
        "symbol:src/cli.py::--verbose",
        "doc:README.md#Configuration",
    ) in documented
    assert (
        "symbol:src/cli.py::API_KEY",
        "doc:README.md#Configuration",
    ) in documented
