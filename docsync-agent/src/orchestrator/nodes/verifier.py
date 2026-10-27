"""Verifier node — 100% deterministic checks (no LLM)."""

from __future__ import annotations

import logging
import re

from src.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)

_CODE_FENCE_PATTERN = re.compile(r"^\s*```", re.MULTILINE)
_DOC_ANCHOR_PATTERN = re.compile(r"<!--\s*doc-anchor:.*?-->")


def build_verifier_node():
    """Return a pure verifier node (no external dependencies needed)."""

    async def verifier_node(state: OrchestratorState) -> dict:
        """Deterministic checks: symbol presence, code fences, doc-anchors."""
        errors: list[str] = []
        updated_docs: dict[str, str] = state.get("updated_docs", {})
        full_docs: dict[str, str] = state.get("full_docs", {})
        drafts = state.get("drafts", [])
        edit_plans = state.get("edit_plans", [])

        if not updated_docs:
            return {"verification_errors": errors}

        # 1. Check targeted symbols appear in each updated section draft
        for draft in drafts:
            for plan in edit_plans:
                if plan.doc_path == draft.doc_path and plan.heading == draft.heading:
                    for s_name in plan.target_symbols:
                        if s_name not in draft.updated_markdown:
                            errors.append(
                                f"{draft.doc_path}#{draft.heading}: targeted symbol `{s_name}` not found in updated section"
                            )

        for doc_path, content in updated_docs.items():
            # Untouched docs must not block the run on pre-existing markdown.
            if doc_path in full_docs and full_docs[doc_path] == content:
                continue

            # 2. Check code fences are balanced
            fences = _CODE_FENCE_PATTERN.findall(content)
            if len(fences) % 2 != 0:
                errors.append(f"{doc_path}: unbalanced code fences (```)")

            # 3. Check doc-anchor comments from original doc are still present
            if doc_path in full_docs:
                original_anchors = set(_DOC_ANCHOR_PATTERN.findall(full_docs[doc_path]))
                updated_anchors = set(_DOC_ANCHOR_PATTERN.findall(content))
                missing = original_anchors - updated_anchors
                for anchor in missing:
                    errors.append(f"{doc_path}: missing doc-anchor comment: {anchor}")

        if errors:
            logger.warning("Verifier found %d errors", len(errors))
        else:
            logger.info("Verifier passed — all checks clean")

        return {"verification_errors": errors}

    return verifier_node