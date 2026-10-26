"""Planner node — maps DriftReport to a targeted edit plan."""

import json
import logging

from src.orchestrator.llm_client import chat_completion
from src.orchestrator.prompts import PLANNER_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)


async def planner_node(state: OrchestratorState) -> OrchestratorState:
    """Generate an edit plan from the drift report using an LLM."""
    if not state.drift_report:
        state.error = "No drift report available for planning"
        return state

    stale_summary = "\n".join(
        f"- {s.doc_path}#{s.doc_section}: symbol `{s.symbol_name}`"
        for s in state.drift_report.stale_sections
    )

    user_message = f"""Drift Report (job: {state.drift_report.job_id})
Stale sections:
{stale_summary}

Changed symbols:
{json.dumps([s.model_dump() for s in (state.change_report.symbols if state.change_report else [])], indent=2)}

Return a JSON array of edit plan items, each with: doc_path, section, action (rewrite|append|remove), instructions."""

    try:
        response = await chat_completion(PLANNER_SYSTEM_PROMPT, user_message)
        # Extract JSON array from response
        start = response.find("[")
        end = response.rfind("]") + 1
        if start >= 0 and end > start:
            state.edit_plan = json.loads(response[start:end])
        logger.info("Planner generated %d edit items", len(state.edit_plan))
    except Exception as exc:
        logger.error("Planner failed: %s", exc)
        state.error = str(exc)

    return state