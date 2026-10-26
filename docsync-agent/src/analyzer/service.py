"""Change Analyzer service — deterministic diff parsing, symbol extraction, and classification.

Implements ``AnalyzerProtocol`` from ``src/contracts/protocols.py``.
All synchronous work is offloaded via ``fastapi.concurrency.run_in_threadpool``.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import unidiff
from fastapi.concurrency import run_in_threadpool

from src.analyzer.ast_extractor import extract_symbols_from_source
from src.analyzer.classifier import classify_symbol_change, collect_changed_line_ranges
from src.analyzer.exceptions import DiffParseError, SymbolExtractionError
from src.analyzer.schemas import ExtractedSymbolSpan
from src.contracts.protocols import AnalyzerProtocol
from src.contracts.schemas import (
    ChangeClass,
    ChangedSymbol,
    ChangeReport,
    WebhookJob,
)

logger = logging.getLogger(__name__)

# ── Public service class ──────────────────────────────────────────────────


class ChangeAnalyzerService(AnalyzerProtocol):
    """Deterministic diff-to-symbol analyzer.

    *No LLM calls.* Parses a unified diff with ``unidiff``, extracts symbols
    via tree-sitter (with Python ``ast`` fallback), and classifies each
    changed symbol into a ``ChangeClass``.
    """

    # Async entry point (required by AnalyzerProtocol) ─────────────────

    async def analyze(
        self,
        job: WebhookJob,
        raw_diff: str,
        file_blobs: dict[str, tuple[str | None, str | None]] | None = None,
    ) -> ChangeReport:
        """Analyze a unified diff for changed symbols.

        Offloads all synchronous work to a thread pool so the FastAPI
        event loop is never blocked.
        """
        return await run_in_threadpool(self._analyze_sync, job, raw_diff, file_blobs)

    # ── Synchronous core ──────────────────────────────────────────────

    def _analyze_sync(
        self,
        job: WebhookJob,
        raw_diff: str,
        file_blobs: dict[str, tuple[str | None, str | None]] | None = None,
    ) -> ChangeReport:
        """Parse diff, extract changed symbols, classify, deduplicate."""
        if file_blobs is None:
            file_blobs = {}

        try:
            patch_set = unidiff.PatchSet(raw_diff)
        except Exception as exc:
            raise DiffParseError(f"Failed to parse unified diff: {exc}") from exc

        changed_symbols: list[ChangedSymbol] = []
        seen: set[tuple[str, str]] = set()  # (file_path, symbol_name)

        for patched_file in patch_set:
            file_path = patched_file.path
            if not file_path:
                continue

            old_blob, new_blob = file_blobs.get(file_path, (None, None))

            # Collect changed line ranges from hunks
            old_changed, new_changed = collect_changed_line_ranges(patched_file)

            # Extract symbols from old and new source
            old_symbols = (
                extract_symbols_from_source(old_blob, file_path)
                if old_blob
                else []
            )
            new_symbols = (
                extract_symbols_from_source(new_blob, file_path)
                if new_blob
                else []
            )

            # Index new symbols by name for fast lookup
            new_by_name: dict[str, ExtractedSymbolSpan] = {}
            for s in new_symbols:
                new_by_name.setdefault(s.name, s)

            old_by_name: dict[str, ExtractedSymbolSpan] = {}
            for s in old_symbols:
                old_by_name.setdefault(s.name, s)

            # ── Added symbols (exist in new but not old, overlap changed lines) ─
            for sym in new_symbols:
                if sym.name in old_by_name:
                    continue
                if sym.start_line in new_changed or any(
                    sym.start_line <= ln <= sym.end_line for ln in new_changed
                ):
                    cs = self._build_changed_symbol(
                        file_path=file_path,
                        symbol=sym,
                        change_type="added",
                        old_signature=None,
                        new_signature=sym.signature,
                        raw_diff=raw_diff,
                    )
                    if (cs.file_path, cs.symbol_name) not in seen:
                        seen.add((cs.file_path, cs.symbol_name))
                        changed_symbols.append(cs)

            # ── Removed symbols (exist in old but not new, overlap changed lines) ─
            for sym in old_symbols:
                if sym.name in new_by_name:
                    continue
                if sym.start_line in old_changed or any(
                    sym.start_line <= ln <= sym.end_line for ln in old_changed
                ):
                    cs = self._build_changed_symbol(
                        file_path=file_path,
                        symbol=sym,
                        change_type="removed",
                        old_signature=sym.signature,
                        new_signature=None,
                        raw_diff=raw_diff,
                    )
                    if (cs.file_path, cs.symbol_name) not in seen:
                        seen.add((cs.file_path, cs.symbol_name))
                        changed_symbols.append(cs)

            # ── Modified symbols (exist in both, overlap changed lines) ─
            for sym in new_symbols:
                if sym.name not in old_by_name:
                    continue
                old_sym = old_by_name[sym.name]
                # Check if symbol spans overlap changed lines
                touches_old = sym.start_line in old_changed or any(
                    sym.start_line <= ln <= sym.end_line for ln in old_changed
                )
                touches_new = sym.start_line in new_changed or any(
                    sym.start_line <= ln <= sym.end_line for ln in new_changed
                )
                if touches_old or touches_new:
                    cs = self._build_changed_symbol(
                        file_path=file_path,
                        symbol=sym,
                        change_type="modified",
                        old_signature=old_sym.signature,
                        new_signature=sym.signature,
                        raw_diff=raw_diff,
                    )
                    if (cs.file_path, cs.symbol_name) not in seen:
                        seen.add((cs.file_path, cs.symbol_name))
                        changed_symbols.append(cs)

            # ── Diff-hunk-only fallback (no file_blobs provided) ─
            if not old_blob and not new_blob:
                hunk_symbols = _extract_from_hunks_only(
                    patched_file, file_path
                )
                for sym_info in hunk_symbols:
                    cs = self._build_changed_symbol(
                        file_path=file_path,
                        symbol=sym_info.get("span"),
                        change_type=sym_info.get("change_type", "modified"),
                        old_signature=sym_info.get("old_sig"),
                        new_signature=sym_info.get("new_sig"),
                        raw_diff=raw_diff,
                        # Override classification if we extracted it from hunks
                        override_class=sym_info.get("classification"),
                    )
                    if (cs.file_path, cs.symbol_name) not in seen:
                        seen.add((cs.file_path, cs.symbol_name))
                        changed_symbols.append(cs)

            # ── File-level classification (DEPS/ENV_CONFIG with no symbols) ─
            _maybe_add_file_level_symbol(
                file_path=file_path,
                seen=seen,
                changed_symbols=changed_symbols,
                raw_diff=raw_diff,
            )

        return ChangeReport(
            delivery_id=job.delivery_id,
            repo_full_name=job.repo_full_name,
            base_sha=job.base_sha,
            head_sha=job.head_sha,
            changed_symbols=changed_symbols,
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _build_changed_symbol(
        self,
        file_path: str,
        symbol: ExtractedSymbolSpan | None,
        change_type: str,
        old_signature: str | None,
        new_signature: str | None,
        raw_diff: str,
        override_class: ChangeClass | None = None,
    ) -> ChangedSymbol:
        """Construct a ``ChangedSymbol`` with classification."""
        # Extract the relevant diff hunk for context
        diff_hunk = _extract_hunk_for_file(raw_diff, file_path)

        if override_class is not None:
            change_class = override_class
        else:
            change_class = classify_symbol_change(
                file_path=file_path,
                symbol_name=symbol.name if symbol else "",
                symbol_kind=symbol.kind if symbol else "function",
                diff_hunk=diff_hunk,
                decorators=symbol.decorators if symbol else [],
                old_signature=old_signature,
                new_signature=new_signature,
            )

        return ChangedSymbol(
            file_path=file_path,
            symbol_name=symbol.name if symbol else "",
            symbol_kind=symbol.kind if symbol else "function",
            change_class=change_class,
            change_type=change_type,
            old_signature=old_signature,
            new_signature=new_signature,
            diff_hunk=diff_hunk,
        )


# ── Hunk-only extraction (fallback when no file_blobs) ────────────────────


def _extract_from_hunks_only(
    patched_file: unidiff.PatchedFile,
    file_path: str,
) -> list[dict[str, Any]]:
    """Extract symbol info directly from diff hunks when file_blobs is absent.

    Returns a list of dicts with keys: span, change_type, old_sig, new_sig,
    classification.
    """
    results: list[dict[str, Any]] = []

    # Include context lines alongside added/removed lines so that symbol
    # definitions (which often sit on context lines) can be reconstructed.
    added_lines: list[str] = []
    removed_lines: list[str] = []
    for hunk in patched_file:
        for line in hunk:
            if line.line_type == "+":
                added_lines.append(line.value)
            elif line.line_type == "-":
                removed_lines.append(line.value)
            else:  # context — include in both so full definitions are visible
                added_lines.append(line.value)
                removed_lines.append(line.value)

    added_text = "\n".join(added_lines)
    removed_text = "\n".join(removed_lines)

    # Attempt symbol extraction from added lines
    if added_text.strip():
        try:
            symbols = extract_symbols_from_source(added_text, file_path)
            for sym in symbols:
                cls_ = classify_symbol_change(
                    file_path=file_path,
                    symbol_name=sym.name,
                    symbol_kind=sym.kind,
                    diff_hunk=added_text,
                    decorators=sym.decorators,
                    old_signature=None,
                    new_signature=sym.signature,
                )
                results.append({
                    "span": sym,
                    "change_type": "added",
                    "old_sig": None,
                    "new_sig": sym.signature,
                    "classification": cls_,
                })
        except (SymbolExtractionError, ValueError) as exc:
            logger.warning(
                "Symbol extraction from added hunk lines failed for %s: %s",
                file_path,
                exc,
            )

    # Check for removed symbols
    if removed_text.strip():
        try:
            symbols = extract_symbols_from_source(removed_text, file_path)
            for sym in symbols:
                if any(
                    r.get("span") and r["span"].name == sym.name
                    for r in results
                ):
                    continue
                cls_ = classify_symbol_change(
                    file_path=file_path,
                    symbol_name=sym.name,
                    symbol_kind=sym.kind,
                    diff_hunk=removed_text,
                    decorators=sym.decorators,
                    old_signature=sym.signature,
                    new_signature=None,
                )
                results.append({
                    "span": sym,
                    "change_type": "removed",
                    "old_sig": sym.signature,
                    "new_sig": None,
                    "classification": cls_,
                })
        except (SymbolExtractionError, ValueError) as exc:
            logger.warning(
                "Symbol extraction from removed hunk lines failed for %s: %s",
                file_path,
                exc,
            )

    return results


def _maybe_add_file_level_symbol(
    file_path: str,
    seen: set[tuple[str, str]],
    changed_symbols: list[ChangedSymbol],
    raw_diff: str,
) -> None:
    """Create a synthetic ChangedSymbol for DEPS/ENV_CONFIG files with no symbols.

    Handles non-code files (e.g. ``pyproject.toml``, ``.env.example``) where
    no AST/tree-sitter symbols can be extracted but the file path itself
    identifies the change category.
    """
    # Only act when this file produced no symbol yet
    if any(cs.file_path == file_path for cs in changed_symbols):
        return

    diff_hunk = _extract_hunk_for_file(raw_diff, file_path)
    file_base = os.path.basename(file_path)

    change_class = classify_symbol_change(
        file_path=file_path,
        symbol_name=file_base,
        symbol_kind="",
        diff_hunk=diff_hunk,
        decorators=[],
        old_signature=None,
        new_signature=None,
    )

    # Only emit synthetic symbols for DEPS / ENV_CONFIG (path-driven categories);
    # behavior/API classes require a real symbol and are skipped here.
    if change_class not in (ChangeClass.DEPS, ChangeClass.ENV_CONFIG):
        return

    key = (file_path, file_base)
    if key in seen:
        return
    seen.add(key)

    changed_symbols.append(
        ChangedSymbol(
            file_path=file_path,
            symbol_name=file_base,
            symbol_kind="",
            change_class=change_class,
            change_type="modified",
            old_signature=None,
            new_signature=None,
            diff_hunk=diff_hunk,
        )
    )


def _extract_hunk_for_file(raw_diff: str, file_path: str) -> str:
    """Extract the diff hunk text for a specific file from the raw diff.

    Handles both ``diff --git`` style headers (git) and ``--- a/`` / ``+++ b/``
    style headers (difflib).
    """
    lines: list[str] = []
    in_target = False
    bare = file_path.replace("\\", "/")
    for line in raw_diff.splitlines():
        # Match either: "diff --git a/..." or "--- a/..." or "+++ b/..."
        if bare in line and line.startswith(("diff --git ", "--- a/", "+++ b/")):
            in_target = True
            if line.startswith(("--- ", "+++ ")):
                continue
        elif in_target:
            # Next file delimiter
            if (
                line.startswith("diff --git ")
                or (line.startswith("--- a/") and bare not in line)
            ):
                in_target = False
                continue
            if line.startswith("index "):
                continue
            lines.append(line)
    return "\n".join(lines)


# ── Singleton convenience ─────────────────────────────────────────────────

analyzer = ChangeAnalyzerService()