"""Drift engine service — compute documentation drift from a ChangeReport."""

import logging

from src.contracts.schemas import ChangeReport, CodeDocEdge, DriftReport, EvidenceRow
from src.drift.anchor_parser import extract_doc_sections, extract_anchors
from src.drift.embed_fallback import find_best_match

logger = logging.getLogger(__name__)


async def compute_drift(
    report: ChangeReport,
    doc_edges: list[CodeDocEdge],
    doc_contents: dict[str, str] | None = None,
) -> DriftReport:
    """Determine which doc sections are stale given changed symbols.

    Algorithm:
    1. Extract all doc anchors from each documentation page.
    2. Intersect changed symbols with doc anchors for direct matches.
    3. For symbols without an anchor match, use embed fallback.

    Deterministic except for the embedding similarity path.
    """
    drift = DriftReport(job_id=report.job_id)

    if doc_contents is None:
        doc_contents = {}

    # Build anchor set per doc path
    doc_anchors: dict[str, set[str]] = {}
    for doc_path, content in doc_contents.items():
        doc_anchors[doc_path] = await extract_anchors(content)

    # Pre-group edges for fast lookup
    edges_by_symbol: dict[str, list[CodeDocEdge]] = {}
    for edge in doc_edges:
        edges_by_symbol.setdefault(edge.symbol_name, []).append(edge)

    for symbol in report.symbols:
        symbol_name_lower = symbol.name.lower()
        edges = edges_by_symbol.get(symbol_name_lower, [])

        if edges:
            # Direct anchor match — these sections are stale
            drift.stale_sections.extend(edges)
            for edge in edges:
                drift.evidence.append(
                    EvidenceRow(
                        symbol=symbol.name,
                        doc_path=edge.doc_path,
                        section_before=edge.doc_section,
                        section_after="",  # filled by orchestrator writer
                        status="updated",
                    )
                )
        elif doc_contents:
            # Embedding fallback for unanchored symbols
            all_sections: list[tuple[str, str]] = []
            for doc_path, content in doc_contents.items():
                sections = await extract_doc_sections(content, doc_path)
                for s in sections:
                    all_sections.append((s.heading, doc_path))

            candidates = [heading for heading, _ in all_sections]
            best, score = await find_best_match(symbol.name, candidates)
            if best and score >= 0.5:
                for heading, doc_path in all_sections:
                    if heading == best:
                        drift.stale_sections.append(
                            CodeDocEdge(
                                symbol_name=symbol.name,
                                doc_path=doc_path,
                                doc_section=heading,
                            )
                        )
                        drift.evidence.append(
                            EvidenceRow(
                                symbol=symbol.name,
                                doc_path=doc_path,
                                section_before=heading,
                                section_after="",
                                status="updated",
                            )
                        )
                        break
        else:
            drift.evidence.append(
                EvidenceRow(
                    symbol=symbol.name,
                    doc_path="",
                    section_before="",
                    section_after="",
                    status="missing",
                )
            )

    logger.info("Drift for job %s: %d stale sections", report.job_id, len(drift.stale_sections))
    return drift