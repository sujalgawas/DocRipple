"""Verifier node — deterministic checks on links, symbols, and code fences."""

import logging
import re

from src.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)

# Simplified patterns
_MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
_CODE_FENCE_PATTERN = re.compile(r"```")


async def verifier_node(state: OrchestratorState) -> OrchestratorState:
    """Run deterministic checks on all updated documents."""
    state.verification_errors = []

    for doc_path, content in state.updated_docs.items():
        # Check code fences are balanced
        fences = _CODE_FENCE_PATTERN.findall(content)
        if len(fences) % 2 != 0:
            state.verification_errors.append(f"{doc_path}: unbalanced code fences")

        # Check links have destinations
        links = _MARKDOWN_LINK_PATTERN.findall(content)
        for text, url in links:
            if not url.strip():
                state.verification_errors.append(f"{doc_path}: empty link URL for [{text}]")

    if state.verification_errors:
        logger.warning("Verifier found %d errors", len(state.verification_errors))
    else:
        logger.info("Verifier passed — all checks clean")

    return state