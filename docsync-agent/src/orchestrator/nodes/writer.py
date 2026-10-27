"""Writer node — rewrites impacted Markdown sections using LLM."""

from __future__ import annotations

import asyncio
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
        # Cap to top 1 highest-confidence section so writer makes only 1 LLM call total
        capped_plans = edit_plans[:1]

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
                new_section = await asyncio.wait_for(
                    llm_client.generate_text(system_prompt, user_prompt),
                    timeout=20.0,
                )

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

            except Exception as exc:
                logger.warning(
                    "Writer LLM failed or timed out for %s#%s (%s: %s); applying deterministic fallback",
                    doc_path,
                    heading,
                    exc.__class__.__name__,
                    exc,
                )
                fallback_section = _build_deterministic_fallback_section(
                    section_md, plan.target_symbols, changed_symbols
                )
                spliced = _splice_section(current_content, heading, fallback_section)
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
                        updated_markdown=fallback_section,
                        evidence=evidence,
                    )
                )

        return {"drafts": new_drafts, "updated_docs": updated_docs}

    return writer_node


def _build_deterministic_fallback_section(
    original_section_md: str,
    target_symbols: list[str],
    changed_symbols: list,
) -> str:
    """Build a clean deterministic Markdown block when LLM times out or fails."""
    lines = original_section_md.split("\n")
    if lines and lines[0].lstrip().startswith("#"):
        base_content = "\n".join(lines[1:]).strip()
    else:
        base_content = original_section_md.strip()

    updates: list[str] = []
    for s_name in target_symbols:
        cs = _find_symbol(changed_symbols, s_name)
        if cs:
            sig = f"\n```python\n{cs.new_signature}\n```" if cs.new_signature else f"`{s_name}`"
            diff = f"\n> *Change ({cs.change_type})*: {cs.diff_hunk[:150]}" if cs.diff_hunk else ""
            updates.append(f"### `{cs.symbol_name}` ({cs.symbol_kind})\n{sig}{diff}\n")
        else:
            updates.append(f"- `{s_name}`: Updated according to code changes.\n")

    update_block = "\n".join(updates).strip()
    if base_content:
        return f"{base_content}\n\n#### Recent Code Updates\n\n{update_block}"
    return f"#### Recent Code Updates\n\n{update_block}"


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