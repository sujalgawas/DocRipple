"""Planner node — maps DriftReport to list[SectionEditPlan]."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.contracts.schemas import DriftReport
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
                    "diff_hunk": s.diff_hunk,
                }
                for s in change_report.changed_symbols
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
                    "current_markdown": sec.current_markdown[:3000],
                }
                for sec in drift.impacted_sections
            ],
            indent=2,
        )

        user_prompt = f"""Changed Symbols:
{symbols_json}

Impacted Documentation Sections:
{sections_json}

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