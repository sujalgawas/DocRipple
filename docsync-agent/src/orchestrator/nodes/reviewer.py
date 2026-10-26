"""Reviewer node — LLM critique of edits against the diff."""

import json
import logging

from src.orchestrator.llm_client import chat_completion
from src.orchestrator.prompts import REVIEWER_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)


async def reviewer_node(state: OrchestratorState) -> OrchestratorState:
    """Review updated docs against the diff; approve or request revision."""
    if state.retry_count >= state.max_retries:
        logger.warning("Max retries (%d) reached — forcing approval", state.max_retries)
        state.review_approved = True
        return state

    docs_summary = "\n\n".join(
        f"### {path}\n{content[:2000]}"  # truncate for token budget
        for path, content in state.updated_docs.items()
    )

    changed_symbols = json.dumps(
        [s.model_dump() for s in (state.change_report.symbols if state.change_report else [])],
        indent=2,
    )

    user_message = f"""Edit Plan:
{json.dumps(state.edit_plan, indent=2)}

Changed Symbols:
{changed_symbols}

Updated Documentation:
{docs_summary}

Verification Errors:
{json.dumps(state.verification_errors)}

Respond with APPROVED or list specific issues to fix."""

    try:
        response = await chat_completion(REVIEWER_SYSTEM_PROMPT, user_message)
        if "APPROVED" in response.upper():
            state.review_approved = True
            logger.info("Reviewer approved")
        else:
            state.review_approved = False
            state.review_feedback = response
            state.retry_count += 1
            logger.info("Reviewer requested revision (attempt %d)", state.retry_count)
    except Exception as exc:
        logger.error("Reviewer failed: %s", exc)
        state.error = str(exc)
        state.review_approved = True  # Fail open

    return state