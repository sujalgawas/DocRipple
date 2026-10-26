"""Writer node — rewrites impacted Markdown sections using LLM."""

import logging

from src.orchestrator.llm_client import chat_completion
from src.orchestrator.prompts import WRITER_SYSTEM_PROMPT
from src.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)


async def writer_node(state: OrchestratorState) -> OrchestratorState:
    """Rewrite documentation sections according to the edit plan."""
    for item in state.edit_plan:
        doc_path = item.get("doc_path", "")
        instructions = item.get("instructions", "")
        section = item.get("section", "")

        # Get current content (would be loaded from repo in production)
        current_content = state.updated_docs.get(doc_path, f"# {section}\n\nTODO: load from repo")

        user_message = f"""Document: {doc_path}
Section: {section}
Instructions: {instructions}

Current content:
{current_content}

Output the full updated document as valid Markdown."""

        try:
            new_content = await chat_completion(WRITER_SYSTEM_PROMPT, user_message)
            state.updated_docs[doc_path] = new_content
            logger.info("Writer updated %s", doc_path)
        except Exception as exc:
            logger.error("Writer failed for %s: %s", doc_path, exc)
            state.error = str(exc)

    return state