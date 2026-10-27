"""Planner node — maps DriftReport to list[SectionEditPlan]."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.contracts.schemas import DriftReport, RepoMemoryMap
from src.orchestrator.prompts import PLANNER_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState, SectionEditPlan

if TYPE_CHECKING:
    from src.orchestrator.llm_client import LLMClientProtocol

logger = logging.getLogger(__name__)


def build_planner_node(llm_client: LLMClientProtocol):
    """Return a planner node with injected dependencies."""

    async def planner_node(state: OrchestratorState) -> dict:
        """Convert drift_report.impacted_sections + changed_symbols into edit plans."""
        drift: DriftReport = state["drift_report"]
        change_report = drift.change_report

        if not drift.impacted_sections:
            return {"edit_plans": []}

        symbols_json = json.dumps(
            [
                {
                    "file_path": s.file_path,
                    "symbol_name": s.symbol_name,
                    "symbol_kind": s.symbol_kind,
                    "change_class": s.change_class,
                    "change_type": s.change_type,
                    "new_signature": s.new_signature,
                    "diff_hunk": (s.diff_hunk or "")[:600],
                }
                for s in change_report.changed_symbols[:30]
            ],
            indent=2,
        )

        sections_json = json.dumps(
            [
                {
                    "doc_path": sec.doc_path,
                    "heading": sec.heading,
                    "matched_symbols": sec.matched_symbols,
                    "match_method": sec.match_method,
                    "confidence": sec.confidence,
                    "current_markdown": sec.current_markdown[:2000],
                }
                for sec in drift.impacted_sections[:15]
            ],
            indent=2,
        )

        memory_context = _format_memory_context(state.get("memory_subgraph"))

        user_prompt = f"""Changed Symbols:
{symbols_json}

Impacted Documentation Sections:
{sections_json}

Repository Memory Subgraph:
{memory_context}

Produce a JSON array of edit plan objects. Each object must have exactly:
- "doc_path": string
- "heading": string
- "target_symbols": array of strings (symbol names from the Changed Symbols list)
- "instructions": string (what to change, referencing new_signature and diff_hunk)"""

        try:
            text = await llm_client.generate_text(PLANNER_SYSTEM_PROMPT, user_prompt)
            raw = _extract_json_array(text)
            if raw is not None:
                parsed = json.loads(raw)
                plans = [SectionEditPlan.model_validate(item) for item in parsed]
                logger.info("Planner generated %d edit plan items", len(plans))
                return {"edit_plans": plans}
        except Exception:
            logger.exception("Planner error — generating fallback plan")

        # Fallback: one plan per impacted section
        return {
            "edit_plans": [
                SectionEditPlan(
                    doc_path=sec.doc_path,
                    heading=sec.heading,
                    target_symbols=sec.matched_symbols,
                    instructions=(
                        f"Update section to reflect changed symbols: "
                        f"{', '.join(sec.matched_symbols) if sec.matched_symbols else 'n/a'}"
                    ),
                )
                for sec in drift.impacted_sections
            ]
        }

    return planner_node


def _format_memory_context(subgraph: RepoMemoryMap | None) -> str:
    """Render the 2-hop memory subgraph as architecturally useful prompt context."""
    if subgraph is None:
        return "No repository memory map is available for this run."

    modules = [node for node in subgraph.nodes if node.node_type == "module"]
    files = [node for node in subgraph.nodes if node.node_type == "file"]
    symbols = [node for node in subgraph.nodes if node.node_type == "symbol"]
    docs = [node for node in subgraph.nodes if node.node_type == "doc_section"]

    parent_modules = ", ".join(f"`{node.name}`" for node in modules[:12]) or "none"
    related_symbols = "; ".join(
        f"`{node.name}` in `{node.path}` - {node.summary}" for node in symbols[:16]
    ) or "none"
    connected_docs = "; ".join(
        f"`{node.path}#{node.name}` - {node.summary}" for node in docs[:16]
    ) or "none"
    relations = ", ".join(
        f"{relation}={count}"
        for relation, count in sorted(
            {
                relation: sum(1 for edge in subgraph.edges if edge.relation == relation)
                for relation in {edge.relation for edge in subgraph.edges}
            }.items()
        )
    ) or "none"

    return f"""Repository: {subgraph.repo_full_name}
Nodes: {len(subgraph.nodes)} · Edges: {len(subgraph.edges)} ({relations})
Parent modules / packages: {parent_modules}
Related files: {', '.join(f'`{node.path}`' for node in files[:16]) or 'none'}
Related symbols: {related_symbols}
Connected documentation sections: {connected_docs}
Use this graph to preserve parent-module behavior, sibling APIs, and the exact
documentation sections that already reference the changed symbols."""


def _extract_json_array(text: str) -> str | None:
    """Extract the first JSON array from LLM output (may include fences)."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if len(lines) > 1 else text
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        return text[start:end]
    return None