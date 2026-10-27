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


def build_planner_node(llm_client: LLMClientProtocol | None = None):
    """Return a deterministic planner node (0 LLM calls)."""

    async def planner_node(state: OrchestratorState) -> dict:
        """Convert drift_report.impacted_sections + changed_symbols into edit plans deterministically."""
        drift: DriftReport | None = state.get("drift_report")
        if not drift or not drift.impacted_sections:
            return {"edit_plans": []}

        change_report = drift.change_report
        all_changed = change_report.changed_symbols if change_report else []
        subgraph: RepoMemoryMap | None = state.get("memory_subgraph")

        # Sort impacted sections by confidence descending and cap at top 2
        sorted_sections = sorted(
            drift.impacted_sections,
            key=lambda s: getattr(s, "confidence", 0.0),
            reverse=True,
        )[:2]

        memory_context = _format_memory_context(subgraph) if subgraph else ""

        plans: list[SectionEditPlan] = []
        for sec in sorted_sections:
            target_symbols = list(sec.matched_symbols)
            if not target_symbols and all_changed:
                target_symbols = [s.symbol_name for s in all_changed[:3]]

            # Match symbol details
            symbol_details: list[str] = []
            for s_name in target_symbols:
                matched_s = next((s for s in all_changed if s.symbol_name == s_name), None)
                if matched_s:
                    sig_info = f", new_signature: `{matched_s.new_signature}`" if matched_s.new_signature else ""
                    hunk_info = f", diff: {matched_s.diff_hunk[:150]}" if matched_s.diff_hunk else ""
                    symbol_details.append(
                        f"`{matched_s.symbol_name}` ({matched_s.symbol_kind}, {matched_s.change_type}{sig_info}{hunk_info})"
                    )
                else:
                    symbol_details.append(f"`{s_name}`")

            instructions = (
                f"Update section '{sec.heading}' to document changed symbols: "
                f"{'; '.join(symbol_details)}."
            )
            if memory_context:
                instructions += f" Architecture context: {memory_context[:300]}."

            plans.append(
                SectionEditPlan(
                    doc_path=sec.doc_path,
                    heading=sec.heading,
                    target_symbols=target_symbols,
                    instructions=instructions,
                )
            )

        logger.info("Deterministic planner generated %d edit plans (0 LLM calls)", len(plans))
        return {"edit_plans": plans}

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