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


def build_reviewer_node(llm_client: LLMClientProtocol):
    """Return a reviewer node with injected LLM dependency."""

    async def reviewer_node(state: OrchestratorState) -> dict:
        """Review docs: reject on verifier errors, then LLM critique."""
        verification_errors: list[str] = state.get("verification_errors", [])
        max_retries: int = state.get("max_retries", 2)
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

        # LLM review
        drift = state["drift_report"]
        changed_symbols = drift.change_report.changed_symbols
        updated_docs: dict[str, str] = state.get("updated_docs", {})
        edit_plans = state.get("edit_plans", [])
        style_skill = state.get("doc_style_skill")

        system_prompt = REVIEWER_SYSTEM_PROMPT
        if style_skill is not None:
            system_prompt = (
                f"{REVIEWER_SYSTEM_PROMPT}\n\n"
                "## Repository DocStyleSkill (adherence is required)\n"
                f"{style_skill.skill_markdown}\n\n"
                "In addition to diff accuracy, reject drafts that violate these "
                "tone, heading, code-fence, table, callout, or anchor conventions."
            )

        docs_summary = "\n\n".join(
            f"### {path}\n{content[:2000]}"
            for path, content in updated_docs.items()
        )

        changed_json = json.dumps(
            [
                {
                    "symbol_name": s.symbol_name,
                    "new_signature": s.new_signature,
                    "diff_hunk": s.diff_hunk[:500],
                }
                for s in changed_symbols
            ],
            indent=2,
        )

        plans_json = json.dumps(
            [p.model_dump() for p in edit_plans],
            indent=2,
        )

        user_prompt = f"""Edit Plans:
{plans_json}

Changed Symbols:
{changed_json}

Updated Documentation:
{docs_summary}

Repository DocStyleSkill:
{style_skill.skill_markdown if style_skill is not None else 'No repository style skill available.'}

Respond with APPROVED if everything checks out, or list specific issues prefixed with "- "."""

        try:
            response = await llm_client.generate_text(system_prompt, user_prompt)
            if "APPROVED" in response.upper():
                logger.info("Reviewer approved")
                return {"review_approved": True}
            else:
                logger.info("Reviewer requested revision (attempt %d)", retry_count + 1)
                return {
                    "review_approved": False,
                    "review_feedback": response,
                    "retry_count": retry_count + 1,
                }
        except Exception:
            logger.exception("Reviewer LLM call failed — failing open")
            return {"review_approved": True}

    return reviewer_node