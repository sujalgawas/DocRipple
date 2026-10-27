"""Reviewer node — gate before publishing."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from src.orchestrator.prompts import REVIEWER_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState

if TYPE_CHECKING:
    from src.orchestrator.llm_client import LLMClientProtocol

logger = logging.getLogger(__name__)


def build_reviewer_node(llm_client: LLMClientProtocol | None = None):
    """Return a reviewer node with injected LLM dependency."""

    async def reviewer_node(state: OrchestratorState) -> dict:
        """Review docs: auto-approve on clean verifier, reject on verifier errors (0 LLM calls)."""
        verification_errors: list[str] = state.get("verification_errors", [])
        max_retries: int = state.get("max_retries", 1)
        retry_count: int = state.get("retry_count", 0)

        # Guardrail: max retries reached — force approve
        if retry_count >= max_retries:
            logger.warning("Max retries (%d) reached — forcing approval", max_retries)
            return {"review_approved": True}

        # Fast path: verifier found errors — reject without calling LLM
        if verification_errors:
            logger.info("Verification errors found — rejecting without LLM call")
            return {
                "review_approved": False,
                "review_feedback": "Verification errors:\n" + "\n".join(f"- {e}" for e in verification_errors),
                "retry_count": retry_count + 1,
            }

        # Verifier passed clean — auto-approve with 0 LLM calls
        logger.info("Verifier passed clean with 0 errors — auto-approving review with 0 LLM calls")
        return {"review_approved": True}

    return reviewer_node