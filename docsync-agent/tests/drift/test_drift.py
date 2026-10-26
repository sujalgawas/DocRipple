"""Unit tests for the deterministic drift engine."""

from __future__ import annotations

import numpy as np
import pytest

from src.contracts.schemas import (
    ChangeClass,
    ChangedSymbol,
    ChangeReport,
    CodeDocEdge,
)
from src.drift.anchor_parser import parse_markdown_sections
from src.drift.embed_fallback import EmbeddingMatcher, fallback_embed
from src.drift.service import DriftEngineService


def _symbol(
    name: str,
    *,
    file_path: str = "src/service.py",
    diff_hunk: str = "",
    symbol_kind: str = "function",
    change_class: ChangeClass = ChangeClass.BEHAVIOR,
) -> ChangedSymbol:
    return ChangedSymbol(
        file_path=file_path,
        symbol_name=name,
        symbol_kind=symbol_kind,
        change_class=change_class,
        change_type="modified",
        diff_hunk=diff_hunk,
    )


def _report(*symbols: ChangedSymbol) -> ChangeReport:
    return ChangeReport(
        delivery_id="delivery-1",
        repo_full_name="acme/docsync",
        base_sha="base-sha",
        head_sha="head-sha",
        changed_symbols=list(symbols),
    )


def _no_embedding(_: list[str]) -> np.ndarray:
    raise AssertionError("embedding fallback should not run for this case")


def _service_without_embeddings() -> DriftEngineService:
    return DriftEngineService(EmbeddingMatcher(embedder=_no_embedding))


@pytest.mark.asyncio
async def test_explicit_anchor_match() -> None:
    docs = {
        "docs/api.md": (
            "# User API\n"
            "\n"
            "Introduction.\n"
            "\n"
            "## Create User\n"
            "\n"
            "<!-- doc-anchor: create_user -->\n"
            "\n"
            "Use this endpoint to create a user.\n"
        )
    }

    drift = await _service_without_embeddings().compute_drift(
        _report(_symbol("create_user")),
        docs,
    )

    assert len(drift.impacted_sections) == 1
    section = drift.impacted_sections[0]
    assert section.doc_path == "docs/api.md"
    assert section.heading == "Create User"
    assert section.matched_symbols == ["create_user"]
    assert section.match_method == "exact_anchor"
    assert section.confidence == 1.0


@pytest.mark.asyncio
async def test_stored_graph_edge_match() -> None:
    docs = {
        "docs/security.md": (
            "# Security\n"
            "\n"
            "## Webhook Verification\n"
            "\n"
            "Verify the payload signature before accepting a webhook.\n"
        )
    }
    edge = CodeDocEdge(
        repo_full_name="acme/docsync",
        symbol_name="verify_github_signature",
        file_path="src/security.py",
        doc_path="docs/security.md",
        section_heading="Webhook Verification",
        anchor_type="explicit_anchor",
    )

    drift = await _service_without_embeddings().compute_drift(
        _report(_symbol("verify_github_signature")),
        docs,
        stored_edges=[edge],
    )

    assert len(drift.impacted_sections) == 1
    section = drift.impacted_sections[0]
    assert section.heading == "Webhook Verification"
    assert section.matched_symbols == ["verify_github_signature"]
    assert section.match_method == "graph_edge"
    assert section.confidence == 0.95


@pytest.mark.asyncio
async def test_inline_backtick_symbol_match() -> None:
    docs = {
        "docs/configuration.md": (
            "# Configuration\n"
            "\n"
            "## Environment Variables\n"
            "\n"
            "Set `GITHUB_WEBHOOK_SECRET` in your environment before starting the server.\n"
        )
    }

    drift = await _service_without_embeddings().compute_drift(
        _report(
            _symbol(
                "GITHUB_WEBHOOK_SECRET",
                symbol_kind="env_var",
                change_class=ChangeClass.ENV_CONFIG,
            )
        ),
        docs,
    )

    assert len(drift.impacted_sections) == 1
    section = drift.impacted_sections[0]
    assert section.heading == "Environment Variables"
    assert section.matched_symbols == ["GITHUB_WEBHOOK_SECRET"]
    assert section.match_method == "inline_symbol"
    assert section.confidence == 0.85


@pytest.mark.asyncio
async def test_embedding_fallback_for_unanchored_docs() -> None:
    docs = {
        "docs/rate_limiting.md": (
            "# API Guide\n"
            "\n"
            "## Request Throttling and Quotas\n"
            "\n"
            "Rate limit middleware enforces request throttling and protects API quotas.\n"
            "\n"
            "## Authentication\n"
            "\n"
            "OAuth tokens and webhook signature verification are handled elsewhere.\n"
        )
    }
    symbol = _symbol(
        "rate_limit_middleware",
        file_path="src/middleware/rate_limit.py",
        diff_hunk="+def rate_limit_middleware(request):\n+    # throttling and quota enforcement",
    )
    matcher = EmbeddingMatcher(embedder=fallback_embed, similarity_threshold=0.45)
    service = DriftEngineService(embedding_matcher=matcher)

    drift = await service.compute_drift(_report(symbol), docs)

    match = next(
        section
        for section in drift.impacted_sections
        if section.heading == "Request Throttling and Quotas"
    )
    assert match.match_method == "embedding_fallback"
    assert 0.45 <= match.confidence <= 1.0
    assert match.matched_symbols == ["rate_limit_middleware"]
    assert all(section.heading != "Authentication" for section in drift.impacted_sections)


@pytest.mark.asyncio
async def test_deduplicates_sections_and_merges_symbols() -> None:
    docs = {
        "docs/users.md": (
            "# Users\n"
            "\n"
            "## User Management\n"
            "\n"
            "<!-- doc-anchor: create_user, delete_user -->\n"
            "\n"
            "Manage user records.\n"
        )
    }

    drift = await _service_without_embeddings().compute_drift(
        _report(_symbol("delete_user"), _symbol("create_user")),
        docs,
    )

    assert len(drift.impacted_sections) == 1
    section = drift.impacted_sections[0]
    assert section.heading == "User Management"
    assert section.matched_symbols == ["create_user", "delete_user"]
    assert section.match_method == "exact_anchor"
    assert section.confidence == 1.0


def test_parser_tracks_line_ranges_and_code_tokens() -> None:
    markdown = (
        "Preamble outside any section.\n"
        "# Title\n"
        "\n"
        "Intro text.\n"
        "## Environment\n"
        "\n"
        "Set `MAX_RETRIES` and run `docsync --dry-run`.\n"
        "\n"
        "```python\n"
        "create_user()\n"
        "```\n"
    )

    sections = parse_markdown_sections(markdown, "docs/guide.md")

    assert [section.heading for section in sections] == ["Title", "Environment"]
    assert sections[0].level == 1
    assert sections[0].start_line == 2
    assert sections[0].end_line == 4
    assert sections[1].start_line == 5
    assert sections[1].end_line == 11
    assert sections[1].inline_code_tokens >= {
        "MAX_RETRIES",
        "docsync --dry-run",
        "python",
        "create_user",
    }
