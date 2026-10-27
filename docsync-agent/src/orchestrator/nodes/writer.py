"""Writer node — rewrites impacted Markdown sections using LLM."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.orchestrator.prompts import WRITER_SYSTEM_PROMPT
from src.orchestrator.schemas import EvidenceRow
from src.orchestrator.state import OrchestratorState, SectionDraft, SectionEditPlan

if TYPE_CHECKING:
    from src.orchestrator.llm_client import LLMClientProtocol

logger = logging.getLogger(__name__)


def build_writer_node(llm_client: LLMClientProtocol):
    """Return a writer node with injected dependencies."""

    async def writer_node(state: OrchestratorState) -> dict:
        """Rewrite each impacted section according to the edit plan."""
        edit_plans: list[SectionEditPlan] = state.get("edit_plans", [])
        full_docs: dict[str, str] = state.get("full_docs", {})
        review_feedback: str = state.get("review_feedback", "")
        verification_errors: list[str] = state.get("verification_errors", [])
        retry_count: int = state.get("retry_count", 0)
        # Only documents whose sections are actually rewritten are tracked here.
        # Seeding this with every doc in the repo makes the verifier flag
        # pre-existing issues in untouched docs and makes the publisher commit
        # docs that did not change.
        updated_docs: dict[str, str] = {}
        style_skill = state.get("doc_style_skill")

        drift = state["drift_report"]
        changed_symbols = drift.change_report.changed_symbols

        system_prompt = WRITER_SYSTEM_PROMPT
        if style_skill is not None:
            system_prompt = (
                f"{WRITER_SYSTEM_PROMPT}\n\n"
                "## Repository DocStyleSkill (MUST FOLLOW)\n"
                f"{style_skill.skill_markdown}\n\n"
                "Follow every convention above exactly. The skill overrides generic "
                "style defaults but never overrides factual consistency with the code diff."
            )

        # Build feedback context for retries
        retry_context = ""
        if retry_count > 0:
            if review_feedback:
                retry_context += f"\n## Reviewer Feedback\n{review_feedback}\n"
            if verification_errors:
                retry_context += (
                    "\n## Verification Errors\n"
                    + "\n".join(f"- {e}" for e in verification_errors)
                    + "\n"
                )

        new_drafts: list[SectionDraft] = []
        capped_plans = edit_plans[:2]

        for plan in capped_plans:
            doc_path = plan.doc_path
            heading = plan.heading

            # Get the current doc content (from updated_docs if already modified, else from full_docs)
            current_content = updated_docs.get(doc_path, full_docs.get(doc_path, ""))

            # Find the section's current markdown
            section_md = _extract_section(current_content, heading)

            # Gather symbol details for this plan
            symbols_detail = []
            for s_name in plan.target_symbols:
                for cs in changed_symbols:
                    if cs.symbol_name == s_name:
                        symbols_detail.append(
                            f"- `{cs.symbol_name}` ({cs.symbol_kind}): "
                            f"new_signature=`{cs.new_signature}`, "
                            f"diff_hunk=`{cs.diff_hunk[:200]}`"
                        )
                        break

            required_symbols_msg = (
                f"You MUST explicitly include each of these changed symbol names: "
                f"{', '.join(f'`{s}`' for s in plan.target_symbols)} "
                f"in your rewritten text or code snippets."
                if plan.target_symbols
                else ""
            )

            user_prompt = f"""Document: {doc_path}
Section Heading: {heading}
Instructions: {plan.instructions}

Current Section Content:
{section_md}

Changed Symbols:
{chr(10).join(symbols_detail) if symbols_detail else 'None'}
{retry_context}

CRITICAL VERIFICATION RULES (MUST FOLLOW ON ATTEMPT 1):
1. {required_symbols_msg}
2. Ensure all code fences (```) are properly balanced and closed.
3. Preserve all <!-- doc-anchor: ... --> comments exactly.

Output ONLY the rewritten section content as valid Markdown. Do not include the heading line itself."""

            try:
                new_section = await llm_client.generate_text(system_prompt, user_prompt)

                # Splice the new section back into the doc
                spliced = _splice_section(current_content, heading, new_section)
                updated_docs[doc_path] = spliced

                evidence = [
                    EvidenceRow(
                        doc_file=doc_path,
                        section=heading,
                        changed_symbol=s_name,
                        change_class=cs.change_class if (cs := _find_symbol(changed_symbols, s_name)) else "",
                        match_method=sec.match_method if (sec := _find_section(drift.impacted_sections, doc_path, heading)) else "graph_edge",
                        verification="pending",
                    )
                    for s_name in plan.target_symbols
                ]

                new_drafts.append(
                    SectionDraft(
                        doc_path=doc_path,
                        heading=heading,
                        updated_markdown=new_section,
                        evidence=evidence,
                    )
                )
                logger.info("Writer updated %s#%s", doc_path, heading)

            except Exception:
                logger.exception("Writer failed for %s#%s", doc_path, heading)
                # Keep original content on failure
                new_drafts.append(
                    SectionDraft(
                        doc_path=doc_path,
                        heading=heading,
                        updated_markdown=section_md,
                        evidence=[],
                    )
                )

        return {"drafts": new_drafts, "updated_docs": updated_docs}

    return writer_node


def _extract_section(content: str, heading: str) -> str:
    """Extract a heading-delimited section from markdown content."""
    lines = content.split("\n")
    start_idx = None
    heading_level = 0
    in_code_block = False

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped.lstrip("#").strip()
            if title == heading.strip():
                start_idx = i
                heading_level = level
            elif start_idx is not None and level <= heading_level:
                # Next heading at same or higher level ends this section
                return "\n".join(lines[start_idx:i])
    if start_idx is not None:
        return "\n".join(lines[start_idx:])
    return content


def _splice_section(content: str, heading: str, new_section: str) -> str:
    """Replace a heading-delimited section in markdown content with new content."""
    lines = content.split("\n")
    start_idx = None
    end_idx = len(lines)
    heading_level = 0
    in_code_block = False

    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            continue

        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            title = stripped.lstrip("#").strip()
            if title == heading.strip():
                start_idx = i
                heading_level = level
            elif start_idx is not None and level <= heading_level:
                end_idx = i
                break

    if start_idx is None:
        # Heading not found — append
        return content.rstrip() + "\n\n" + new_section

    # Keep the heading line itself, replace content after it
    result = lines[: start_idx + 1]
    result.append("")
    result.extend(new_section.split("\n"))
    result.append("")
    result.extend(lines[end_idx:])
    return "\n".join(result)


def _find_symbol(symbols, name: str):
    from src.contracts.schemas import ChangedSymbol

    for s in symbols:
        if isinstance(s, ChangedSymbol) and s.symbol_name == name:
            return s
    return None


def _find_section(sections, doc_path: str, heading: str):
    from src.contracts.schemas import ImpactedDocSection

    for s in sections:
        if isinstance(s, ImpactedDocSection) and s.doc_path == doc_path and s.heading == heading:
            return s
    return None