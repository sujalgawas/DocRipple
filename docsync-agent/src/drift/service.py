"""Deterministic documentation-drift engine implementing ``DriftEngineProtocol``."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from starlette.concurrency import run_in_threadpool

from src.contracts.schemas import (
    ChangedSymbol,
    ChangeReport,
    CodeDocEdge,
    DriftReport,
    ImpactedDocSection,
)
from src.drift.anchor_parser import parse_markdown_sections
from src.drift.embed_fallback import (
    DEFAULT_SIMILARITY_THRESHOLD,
    Embedder,
    EmbeddingMatcher,
)
from src.drift.schemas import DocSectionNode

logger = logging.getLogger(__name__)

_METHOD_PRIORITY = {
    "exact_anchor": 0,
    "graph_edge": 1,
    "inline_symbol": 2,
    "embedding_fallback": 3,
}
_METHOD_CONFIDENCE = {
    "exact_anchor": 1.0,
    "graph_edge": 0.95,
    "inline_symbol": 0.85,
}


@dataclass(frozen=True, slots=True)
class _SectionMatch:
    """A single symbol-to-section match before cross-symbol deduplication."""

    section: DocSectionNode
    match_method: str
    confidence: float


def _is_better(candidate: _SectionMatch, current: _SectionMatch) -> bool:
    """Prefer higher confidence, then the higher-priority method, then earlier section."""
    return (
        candidate.confidence,
        -_METHOD_PRIORITY[candidate.match_method],
        -candidate.section.start_line,
    ) > (
        current.confidence,
        -_METHOD_PRIORITY[current.match_method],
        -current.section.start_line,
    )


def _normalize_heading(heading: str) -> str:
    """Normalise a graph-edge heading for exact lookup."""
    return heading.strip().lstrip("#").strip()


def _parse_documents(docs: dict[str, str]) -> list[DocSectionNode]:
    """Parse every document in deterministic path order."""
    sections: list[DocSectionNode] = []
    for doc_path in sorted(docs):
        sections.extend(parse_markdown_sections(docs[doc_path], doc_path))
    return sections


def _inline_token_matches(symbol_name: str, tokens: set[str]) -> bool:
    """Match bare code spans and symbol names embedded in code examples."""
    if symbol_name in tokens:
        return True

    pattern = re.compile(rf"(?<![\w-]){re.escape(symbol_name)}(?![\w-])")
    return any(pattern.search(token) for token in tokens)


class DriftEngineService:
    """Match changed code symbols to the Markdown sections that document them."""

    def __init__(
        self,
        embedding_matcher: EmbeddingMatcher | None = None,
        *,
        embedder: Embedder | None = None,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
    ) -> None:
        if embedding_matcher is not None and embedder is not None:
            raise ValueError("pass either embedding_matcher or embedder, not both")

        self._embedding_matcher = embedding_matcher or EmbeddingMatcher(
            embedder=embedder,
            similarity_threshold=similarity_threshold,
        )

    async def compute_drift(
        self,
        change_report: ChangeReport,
        docs: dict[str, str],
        stored_edges: list[CodeDocEdge] | None = None,
    ) -> DriftReport:
        """Return the Markdown sections impacted by ``change_report``.

        Parsing and similarity math run in Starlette's thread pool so the event
        loop is never blocked.  No LLM or network dependency is used.
        """
        sections = await run_in_threadpool(_parse_documents, docs)
        edge_index = {
            (
                edge.symbol_name,
                edge.doc_path,
                _normalize_heading(edge.section_heading),
            )
            for edge in (stored_edges or [])
        }

        merged: dict[tuple[str, str], _SectionMatch] = {}
        merged_symbols: dict[tuple[str, str], set[str]] = {}

        for symbol in change_report.changed_symbols:
            symbol_matches = self._match_without_embeddings(symbol, sections, edge_index)

            if not symbol_matches:
                symbol_matches = await run_in_threadpool(
                    self._embedding_matches,
                    symbol,
                    sections,
                )

            for match in symbol_matches:
                dedupe_key = (match.section.doc_path, match.section.heading)
                merged_symbols.setdefault(dedupe_key, set()).add(symbol.symbol_name)

                current = merged.get(dedupe_key)
                if current is None or _is_better(match, current):
                    merged[dedupe_key] = match

        impacted_sections = [
            ImpactedDocSection(
                doc_path=match.section.doc_path,
                heading=match.section.heading,
                start_line=match.section.start_line,
                end_line=match.section.end_line,
                matched_symbols=sorted(merged_symbols[key]),
                match_method=match.match_method,
                confidence=match.confidence,
                current_markdown=match.section.raw_markdown,
            )
            for key, match in sorted(
                merged.items(),
                key=lambda item: (
                    item[1].section.doc_path,
                    item[1].section.start_line,
                    item[1].section.heading,
                ),
            )
        ]

        logger.info(
            "Computed drift for delivery %s: %d impacted section(s)",
            change_report.delivery_id,
            len(impacted_sections),
        )
        return DriftReport(
            change_report=change_report,
            impacted_sections=impacted_sections,
        )

    def _match_without_embeddings(
        self,
        symbol: ChangedSymbol,
        sections: list[DocSectionNode],
        edge_index: set[tuple[str, str, str]],
    ) -> list[_SectionMatch]:
        """Collect exact-anchor, graph-edge, and inline-symbol matches."""
        matches: dict[tuple[str, int, str], _SectionMatch] = {}
        graph_key = symbol.symbol_name

        for section in sections:
            if symbol.symbol_name in section.explicit_anchors:
                self._add_match(
                    matches,
                    _SectionMatch(
                        section=section,
                        match_method="exact_anchor",
                        confidence=_METHOD_CONFIDENCE["exact_anchor"],
                    ),
                )

            if (
                graph_key,
                section.doc_path,
                _normalize_heading(section.heading),
            ) in edge_index:
                self._add_match(
                    matches,
                    _SectionMatch(
                        section=section,
                        match_method="graph_edge",
                        confidence=_METHOD_CONFIDENCE["graph_edge"],
                    ),
                )

            if _inline_token_matches(symbol.symbol_name, section.inline_code_tokens):
                self._add_match(
                    matches,
                    _SectionMatch(
                        section=section,
                        match_method="inline_symbol",
                        confidence=_METHOD_CONFIDENCE["inline_symbol"],
                    ),
                )

        return list(matches.values())

    @staticmethod
    def _add_match(
        matches: dict[tuple[str, int, str], _SectionMatch],
        candidate: _SectionMatch,
    ) -> None:
        key = (
            candidate.section.doc_path,
            candidate.section.start_line,
            candidate.section.heading,
        )
        current = matches.get(key)
        if current is None or _is_better(candidate, current):
            matches[key] = candidate

    def _embedding_matches(
        self,
        symbol: ChangedSymbol,
        sections: list[DocSectionNode],
    ) -> list[_SectionMatch]:
        """Run the deterministic embedding fallback for one unanchored symbol."""
        query = f"{symbol.symbol_name} {symbol.file_path} {symbol.diff_hunk}"
        return [
            _SectionMatch(
                section=section,
                match_method="embedding_fallback",
                confidence=round(max(0.0, min(1.0, score)), 2),
            )
            for section, score in self._embedding_matcher.match_sections(query, sections)
        ]
