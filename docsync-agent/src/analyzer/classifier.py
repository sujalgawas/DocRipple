"""Rule engine for classifying changed symbols into semantic categories.

Deterministic heuristics — no LLM calls.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from typing import TYPE_CHECKING

from src.contracts.schemas import ChangeClass

if TYPE_CHECKING:
    import unidiff

logger = logging.getLogger(__name__)

# ── Dependency file patterns ──────────────────────────────────────────────

_DEPS_FILES: set[str] = {
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "requirements-test.txt",
    "requirements.in",
    "package.json",
    "Cargo.toml",
    "go.mod",
    "go.sum",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
}

# ── Env / config path indicators ──────────────────────────────────────────

_ENV_PATH_PATTERNS: tuple[str, ...] = (
    ".env",
    "config",
    "settings",
)

# ── CLI-related decorators & patterns ─────────────────────────────────────

_CLI_DECORATOR_MARKERS: tuple[str, ...] = (
    "@click.",
    "@typer.",
    "@app.command",
    "@cli.command",
    "argparse.ArgumentParser",
    ".add_argument",
    ".add_option",
)

# ── Route / API decorator markers ─────────────────────────────────────────

_ROUTE_DECORATOR_MARKERS: tuple[str, ...] = (
    "@router.",
    "@app.get",
    "@app.post",
    "@app.put",
    "@app.delete",
    "@app.patch",
    "@app.route",
    "@bp.",
    "@blueprint.",
    ".get(",
    ".post(",
    ".put(",
    ".delete(",
    ".patch(",
)

# ── Public API ────────────────────────────────────────────────────────────


def classify_symbol_change(
    file_path: str,
    symbol_name: str,
    symbol_kind: str,
    diff_hunk: str,
    decorators: list[str] | None = None,
    old_signature: str | None = None,
    new_signature: str | None = None,
) -> ChangeClass:
    """Classify a changed symbol into exactly one ``ChangeClass``.

    Priority order (first match wins):
    1. **DEPS** — file is a known dependency manifest.
    2. **ENV_CONFIG** — file path or content matches env/config patterns.
    3. **CLI** — CLI decorators, argparse usage, or ``cli/`` directory.
    4. **API_SURFACE** — route decorators, public signature change, or Pydantic/schema.
    5. **BEHAVIOR** — body-only change (no public signature delta).
    """
    decorators = decorators or []
    file_base = os.path.basename(file_path)
    file_lower = file_path.lower()
    hunk_lower = diff_hunk.lower()

    # 1. Dependency change
    if file_base in _DEPS_FILES:
        return ChangeClass.DEPS

    # 2. Env / Config change
    if _is_env_config(file_path, file_base, diff_hunk, hunk_lower, symbol_name):
        return ChangeClass.ENV_CONFIG

    # 3. CLI change
    if _is_cli_change(file_lower, decorators, hunk_lower, symbol_name, symbol_kind):
        return ChangeClass.CLI

    # 4. API Surface change
    if _is_api_surface(decorators, symbol_name, symbol_kind, old_signature, new_signature, hunk_lower):
        return ChangeClass.API_SURFACE

    # 5. Everything else is behavior
    return ChangeClass.BEHAVIOR


# ── Heuristic helpers ─────────────────────────────────────────────────────


def _is_env_config(
    file_path: str,
    file_base: str,
    diff_hunk: str,
    hunk_lower: str,
    symbol_name: str,
) -> bool:
    """Check if the change is env/config-related."""
    # File-level signals
    if "config" in file_base.lower() and file_path.endswith(".py"):
        return True
    if file_base.startswith(".env"):
        return True
    if any(pattern in file_path.lower() for pattern in _ENV_PATH_PATTERNS):
        pass  # Continue to content checks
    else:
        # Content-level signals
        _env_signals = (
            "os.getenv",
            "os.environ",
            "basesettings",
            "getenv(",
            "environ[",
            "env(",
        )
        if not any(sig in hunk_lower for sig in _env_signals):
            return False

    return True


def _is_cli_change(
    file_lower: str,
    decorators: list[str],
    hunk_lower: str,
    symbol_name: str,
    symbol_kind: str,
) -> bool:
    """Check if the change is CLI-related."""
    # Decorator signals
    decorator_text = " ".join(decorators).lower()
    if any(marker.lower() in decorator_text for marker in _CLI_DECORATOR_MARKERS):
        return True

    # Hunk / symbol signals
    if any(marker.lower() in hunk_lower for marker in _CLI_DECORATOR_MARKERS):
        return True

    # File path signals
    return bool("/cli/" in file_lower or "\\cli\\" in file_lower or file_lower.startswith("cli/"))


def _is_api_surface(
    decorators: list[str],
    symbol_name: str,
    symbol_kind: str,
    old_signature: str | None,
    new_signature: str | None,
    hunk_lower: str,
) -> bool:
    """Check if the change affects the public API surface."""
    # Route decorators
    decorator_text = " ".join(decorators).lower()
    if any(marker.lower() in decorator_text for marker in _ROUTE_DECORATOR_MARKERS):
        return True

    # Public function/class with signature change
    is_public = not symbol_name.startswith("_")
    if (
        is_public
        and old_signature is not None
        and new_signature is not None
        and _normalize_sig(old_signature) != _normalize_sig(new_signature)
    ):
        return True

    # Pydantic schema class
    return bool(symbol_kind == "class" and "base" in hunk_lower and "model" in hunk_lower)


def _normalize_sig(sig: str) -> str:
    """Strip whitespace for comparison."""
    return "".join(sig.split())


# ── Changed-line-range helpers (used by service.py) ───────────────────────

def collect_changed_line_ranges(
    hunk_iter: Iterable[unidiff.Hunk],
) -> tuple[set[int], set[int]]:
    """Return sets of changed line numbers from a unidiff hunk list.

    Returns ``(old_changed_lines, new_changed_lines)`` where each set
    contains 1-based line numbers that were removed (old) or added/context (new).
    """
    old_lines: set[int] = set()
    new_lines: set[int] = set()

    for hunk in hunk_iter:
        old_lineno = hunk.source_start
        new_lineno = hunk.target_start

        for line in hunk:
            if line.line_type == "-":
                old_lines.add(old_lineno)
                old_lineno += 1
            elif line.line_type == "+":
                new_lines.add(new_lineno)
                new_lineno += 1
            else:  # context line
                old_lines.add(old_lineno)
                new_lines.add(new_lineno)
                old_lineno += 1
                new_lineno += 1

    return old_lines, new_lines