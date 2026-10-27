"""Tests for the Change Analyzer module (Agent 2).

Covers: API surface changes, CLI flags, env/config, dependencies, and behavior changes.
"""

from __future__ import annotations

import difflib
import textwrap
from datetime import UTC, datetime

import pytest

from src.analyzer.service import ChangeAnalyzerService
from src.contracts.schemas import ChangeClass, WebhookJob

# ── Helpers ───────────────────────────────────────────────────────────────


def _dedent(text: str) -> str:
    return textwrap.dedent(text).strip() + "\n"


def _make_diff(old: str, new: str, file_path: str) -> str:
    """Generate a realistic unified diff between two file contents."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{file_path}",
            tofile=f"b/{file_path}",
        )
    )
    return "".join(diff_lines)


def _make_job(delivery_id: str = "test-001", repo: str = "owner/repo") -> WebhookJob:
    return WebhookJob(
        delivery_id=delivery_id,
        event_type="push",
        repo_full_name=repo,
        base_sha="abc123",
        head_sha="def456",
        ref="refs/heads/main",
        received_at=datetime.now(UTC),
    )


# ── Test 1: API Surface Change ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_api_surface_signature_change():
    """A FastAPI endpoint signature change is classified as API_SURFACE."""
    old_content = _dedent("""\
        from fastapi import APIRouter

        router = APIRouter()

        @router.post("/users")
        async def create_user(email: str) -> dict:
            return {"email": email, "id": 1}
    """)

    new_content = _dedent("""\
        from fastapi import APIRouter

        router = APIRouter()

        @router.post("/users")
        async def create_user(email: str, role: str = "member") -> dict:
            return {"email": email, "role": role, "id": 1}
    """)

    raw_diff = _make_diff(old_content, new_content, "app/routes.py")
    job = _make_job()
    service = ChangeAnalyzerService()

    report = await service.analyze(
        job,
        raw_diff,
        file_blobs={"app/routes.py": (old_content, new_content)},
    )

    assert len(report.changed_symbols) >= 1

    symbol = report.changed_symbols[0]
    assert symbol.symbol_name == "create_user"
    assert symbol.symbol_kind in ("function", "route")
    assert symbol.change_class == ChangeClass.API_SURFACE
    assert symbol.change_type == "modified"
    assert symbol.old_signature is not None
    assert "email" in symbol.old_signature
    assert "role" not in (symbol.old_signature or "")
    assert symbol.new_signature is not None
    assert "role" in symbol.new_signature


# ── Test 2: CLI Flag Change ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cli_flag_change():
    """Adding a CLI flag via argparse is classified as CLI."""
    old_content = _dedent("""\
        import argparse

        def main():
            parser = argparse.ArgumentParser()
            parser.add_argument("name")
            args = parser.parse_args()
            print(args.name)
    """)

    new_content = _dedent("""\
        import argparse

        def main():
            parser = argparse.ArgumentParser()
            parser.add_argument("name")
            parser.add_argument("--dry-run", action="store_true")
            args = parser.parse_args()
            print(args.name)
    """)

    raw_diff = _make_diff(old_content, new_content, "cli/main.py")
    job = _make_job()
    service = ChangeAnalyzerService()

    report = await service.analyze(
        job,
        raw_diff,
        file_blobs={"cli/main.py": (old_content, new_content)},
    )

    symbols = report.changed_symbols
    assert len(symbols) >= 1

    # The function `main` is modified and its diff hunk contains argparse markers
    cli_symbols = [s for s in symbols if s.change_class == ChangeClass.CLI]
    assert len(cli_symbols) >= 1, f"Expected CLI classification, got: {[(s.symbol_name, s.change_class) for s in symbols]}"

    cli_sym = cli_symbols[0]
    assert cli_sym.symbol_name == "main"
    assert "argparse" in cli_sym.diff_hunk.lower()


# ── Test 3: Env / Config Change ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_env_config_change():
    """Adding to a BaseSettings config class is classified as ENV_CONFIG."""
    old_content = _dedent("""\
        from pydantic_settings import BaseSettings

        class Settings(BaseSettings):
            api_key: str = ""
            debug: bool = False
    """)

    new_content = _dedent("""\
        from pydantic_settings import BaseSettings

        class Settings(BaseSettings):
            api_key: str = ""
            debug: bool = False
            max_retries: int = 3
    """)

    raw_diff = _make_diff(old_content, new_content, "app/config.py")
    job = _make_job()
    service = ChangeAnalyzerService()

    report = await service.analyze(
        job,
        raw_diff,
        file_blobs={"app/config.py": (old_content, new_content)},
    )

    symbols = report.changed_symbols
    assert len(symbols) >= 1

    # The class `Settings` body changed — should be ENV_CONFIG
    env_symbols = [s for s in symbols if s.change_class == ChangeClass.ENV_CONFIG]
    assert len(env_symbols) >= 1, (
        f"Expected ENV_CONFIG classification, got: "
        f"{[(s.symbol_name, s.change_class, s.change_type) for s in symbols]}"
    )

    assert env_symbols[0].symbol_name == "Settings"


# ── Test 4: Dependency Change ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dependency_change():
    """Modifying pyproject.toml is classified as DEPS."""
    old_content = _dedent("""\
        [project]
        name = "my-app"
        dependencies = [
            "fastapi>=0.100",
        ]
    """)

    new_content = _dedent("""\
        [project]
        name = "my-app"
        dependencies = [
            "fastapi>=0.100",
            "httpx>=0.27",
        ]
    """)

    raw_diff = _make_diff(old_content, new_content, "pyproject.toml")
    job = _make_job()
    service = ChangeAnalyzerService()

    report = await service.analyze(
        job,
        raw_diff,
        file_blobs={"pyproject.toml": (old_content, new_content)},
    )

    symbols = report.changed_symbols
    # For non-code files with no extractable symbols, the service should still
    # create a DEPS-classified ChangedSymbol based on the file path.
    assert len(symbols) >= 1, "Expected at least one ChangedSymbol for pyproject.toml change"

    deps_symbols = [s for s in symbols if s.change_class == ChangeClass.DEPS]
    assert len(deps_symbols) >= 1, (
        f"Expected DEPS classification, got: {[(s.symbol_name, s.change_class) for s in symbols]}"
    )


# ── Test 5: Internal Behavior Change ──────────────────────────────────────


@pytest.mark.asyncio
async def test_behavior_change():
    """Changing internal logic without altering signature is classified as BEHAVIOR."""
    old_content = _dedent("""\
        def compute_score(x: int) -> int:
            if x > 10:
                return x * 2
            return x
    """)

    new_content = _dedent("""\
        def compute_score(x: int) -> int:
            if x > 10:
                return x * 2 + 1
            return x
    """)

    raw_diff = _make_diff(old_content, new_content, "lib/utils.py")
    job = _make_job()
    service = ChangeAnalyzerService()

    report = await service.analyze(
        job,
        raw_diff,
        file_blobs={"lib/utils.py": (old_content, new_content)},
    )

    symbols = report.changed_symbols
    assert len(symbols) >= 1

    behavior_symbols = [s for s in symbols if s.change_class == ChangeClass.BEHAVIOR]
    assert len(behavior_symbols) >= 1, (
        f"Expected BEHAVIOR classification, got: {[(s.symbol_name, s.change_class) for s in symbols]}"
    )

    sym = behavior_symbols[0]
    assert sym.symbol_name == "compute_score"
    assert sym.change_type == "modified"
    # Signatures should be identical
    assert sym.old_signature is not None
    assert sym.new_signature is not None
    assert sym.old_signature.replace(" ", "") == sym.new_signature.replace(" ", "")


# ── Edge-case: empty diff ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_diff_returns_no_symbols():
    """An empty diff produces a ChangeReport with no symbols."""
    job = _make_job()
    service = ChangeAnalyzerService()
    report = await service.analyze(job, "", file_blobs={})
    assert report.changed_symbols == []
    assert report.delivery_id == job.delivery_id


# ── Edge-case: file_blobs not provided ─────────────────────────────────────


@pytest.mark.asyncio
async def test_hunk_only_extraction():
    """When file_blobs is None, symbols are extracted from diff hunks directly."""
    old_content = _dedent("""\
        def foo(x: int) -> int:
            return x
    """)
    new_content = _dedent("""\
        def foo(x: int) -> int:
            return x + 1
    """)

    raw_diff = _make_diff(old_content, new_content, "lib/utils.py")
    job = _make_job()
    service = ChangeAnalyzerService()

    # No file_blobs provided
    report = await service.analyze(job, raw_diff, file_blobs={})

    # The hunk-only fallback should extract `foo` from added lines
    assert len(report.changed_symbols) >= 1
    names = [s.symbol_name for s in report.changed_symbols]
    assert "foo" in names

# -- Edge-case: tree-sitter native binary unavailable ----------------------


def test_regex_fallback_when_tree_sitter_unavailable(monkeypatch: pytest.MonkeyPatch):
    """A failed tree-sitter load must degrade to regex, not crash the app."""
    from src.analyzer import ast_extractor

    monkeypatch.setattr(ast_extractor, "_get_parser", None)

    source = "export class BillingService {\nexport async function calcTotal() {\n"
    spans = ast_extractor.extract_symbols_from_source(source, "src/billing.ts")

    assert {span.name for span in spans} == {"BillingService", "calcTotal"}
    assert {span.kind for span in spans} == {"class", "function"}


def test_python_ast_still_works_when_tree_sitter_unavailable(
    monkeypatch: pytest.MonkeyPatch,
):
    """Python files keep using the stdlib ast extractor."""
    from src.analyzer import ast_extractor

    monkeypatch.setattr(ast_extractor, "_get_parser", None)

    spans = ast_extractor.extract_symbols_from_source(
        "def compute(x: int) -> int:\n    return x\n", "src/utils.py"
    )

    assert [span.name for span in spans] == ["compute"]
    assert spans[0].kind == "function"
