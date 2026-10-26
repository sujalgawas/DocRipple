"""Verifier node — 100% deterministic checks (no LLM)."""

from __future__ import annotations

import logging
import re

from src.orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)

_CODE_FENCE_PATTERN = re.compile(r"```")
_DOC_ANCHOR_PATTERN = re.compile(r"<!--\s*doc-anchor:.*?-->")


def build_verifier_node():
    """Return a pure verifier node (no external dependencies needed)."""

    async def verifier_node(state: OrchestratorState) -> dict:
        """Deterministic checks: symbol presence, code fences, doc-anchors."""
        errors: list[str] = []
        updated_docs: dict[str, str] = state.get("updated_docs", {})
        full_docs: dict[str, str] = state.get("full_docs", {})
        drift = state["drift_report"]
        changed_symbols = drift.change_report.changed_symbols
        edit_plans = state.get("edit_plans", [])

        if not updated_docs:
            return {"verification_errors": errors}

        # Build set of symbol names targeted across all plans
        targeted_names: set[str] = set()
        for plan in edit_plans:
            targeted_names.update(plan.target_symbols)

        for doc_path, content in updated_docs.items():
            # 1. Check every targeted symbol name appears in the updated doc
            for plan in edit_plans:
                if plan.doc_path != doc_path:
                    continue
                for s_name in plan.target_symbols:
                    if s_name not in content:
                        errors.append(
                            f"{doc_path}: targeted symbol `{s_name}` not found in updated content"
                        )

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