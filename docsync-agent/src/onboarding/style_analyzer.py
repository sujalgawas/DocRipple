"""Deterministic DocStyleSkill generation from a repository's Markdown docs."""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import pairwise
from typing import TYPE_CHECKING

from fastapi.concurrency import run_in_threadpool
from markdown_it import MarkdownIt

from src.contracts.schemas import DocStyleSkill

if TYPE_CHECKING:
    from src.orchestrator.llm_client import LLMClientProtocol

logger = logging.getLogger(__name__)

_MD = MarkdownIt("commonmark")

_EMOJI_HEADING_RE = re.compile(
    r"^[\U0001f300-\U0001faff\u2600-\u27bf\u2b50\u2705\u274c]"
)
_NUMBERED_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*[.)]?\s+")
_CALLOUT_RE = re.compile(
    r">\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]",
    re.IGNORECASE,
)
_DOC_ANCHOR_RE = re.compile(r"<!--\s*(?:doc-anchor|@symbol)\s*:", re.IGNORECASE)
_TABLE_RE = re.compile(
    r"(?m)^\s*\|.+\|\s*$\n\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$"
)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_IMPERATIVE_VERBS = {
    "add",
    "call",
    "configure",
    "create",
    "define",
    "ensure",
    "follow",
    "install",
    "open",
    "pass",
    "provide",
    "run",
    "see",
    "set",
    "start",
    "stop",
    "update",
    "use",
}
_REFINE_SYSTEM_PROMPT = """You are a documentation style analyst. Rewrite the supplied
repository style profile as one complete SKILL.md instruction block. Preserve every
observed convention exactly. Begin with YAML frontmatter delimited by --- and include
name and description keys. Do not invent conventions that are absent from the profile."""


@dataclass(slots=True)
class _DocAnalysis:
    """Accumulated deterministic style observations."""

    doc_count: int = 0
    heading_levels: Counter[int] = field(default_factory=Counter)
    heading_transitions: Counter[tuple[int, int]] = field(default_factory=Counter)
    first_heading_levels: Counter[int] = field(default_factory=Counter)
    heading_texts: list[str] = field(default_factory=list)
    heading_sequences: list[list[int]] = field(default_factory=list)
    emoji_headings: int = 0
    numbered_headings: int = 0
    fence_count: int = 0
    untagged_fences: int = 0
    languages: Counter[str] = field(default_factory=Counter)
    curl_examples: int = 0
    cli_flags: int = 0
    python_typed: int = 0
    table_count: int = 0
    callouts: Counter[str] = field(default_factory=Counter)
    inline_code_count: int = 0
    doc_anchor_count: int = 0
    bullet_count: int = 0
    prose_sentences: int = 0
    imperative_sentences: int = 0
    second_person: int = 0
    first_plural: int = 0
    prose_words: int = 0


class DocStyleSkillGenerator:
    """Mine Markdown conventions and compile a reusable ``SKILL.md`` prompt.

    The deterministic path is always available. When an ``LLMClientProtocol``
    is injected, it may rewrite the compiled block while preserving the
    observed conventions; failures fall back to the deterministic block.
    """

    def __init__(self, llm_client: LLMClientProtocol | None = None) -> None:
        self._llm_client = llm_client

    async def generate(
        self,
        repo_full_name: str,
        docs: dict[str, str],
    ) -> DocStyleSkill:
        """Generate a repository style skill in a thread-pool worker."""
        skill = await run_in_threadpool(
            self._build_deterministic,
            repo_full_name,
            docs,
        )
        if self._llm_client is None:
            return skill
        return await self._refine_with_llm(repo_full_name, skill)

    async def generate_skill(
        self,
        repo_full_name: str,
        docs: dict[str, str],
    ) -> DocStyleSkill:
        """Alias for :meth:`generate`."""
        return await self.generate(repo_full_name, docs)

    # ── Deterministic analysis ───────────────────────────────────────────

    def _build_deterministic(
        self,
        repo_full_name: str,
        docs: dict[str, str],
    ) -> DocStyleSkill:
        analysis = self._analyze_docs(docs)
        tone = _tone_and_voice(analysis)
        headings = _heading_conventions(analysis)
        code_rules = _code_block_rules(analysis)
        formatting = _formatting_patterns(analysis)
        skill_markdown = _render_skill_markdown(
            repo_full_name=repo_full_name,
            tone=tone,
            headings=headings,
            code_rules=code_rules,
            formatting=formatting,
        )
        return DocStyleSkill(
            repo_full_name=repo_full_name,
            tone_and_voice=tone,
            heading_conventions=headings,
            code_block_rules=code_rules,
            formatting_patterns=formatting,
            skill_markdown=skill_markdown,
            generated_at=datetime.now(UTC),
        )

    def _analyze_docs(self, docs: dict[str, str]) -> _DocAnalysis:
        analysis = _DocAnalysis(doc_count=len(docs))

        for doc_path in sorted(docs):
            markdown = docs[doc_path] or ""
            if not markdown.strip():
                continue

            tokens = _MD.parse(markdown)
            levels: list[int] = []
            prose_parts: list[str] = []

            for index, token in enumerate(tokens):
                if token.type == "heading_open":
                    level = int(token.tag[1:]) if token.tag[1:].isdigit() else 1
                    heading = ""
                    if index + 1 < len(tokens) and tokens[index + 1].type == "inline":
                        heading = _plain_inline_text(tokens[index + 1])
                        prose_parts.append(heading)
                    levels.append(level)
                    analysis.heading_levels[level] += 1
                    analysis.heading_texts.append(heading)
                    if _EMOJI_HEADING_RE.match(heading):
                        analysis.emoji_headings += 1
                    if _NUMBERED_HEADING_RE.match(heading):
                        analysis.numbered_headings += 1
                elif token.type == "inline":
                    for child in token.children or []:
                        if child.type == "code_inline":
                            analysis.inline_code_count += 1
                        elif child.type == "text":
                            prose_parts.append(child.content)
                elif token.type == "fence":
                    analysis.fence_count += 1
                    info = (token.info or "").strip()
                    language = info.split()[0].lower() if info else ""
                    if language:
                        analysis.languages[language] += 1
                    else:
                        analysis.untagged_fences += 1
                    if re.search(r"(?m)^\s*curl\b", token.content):
                        analysis.curl_examples += 1
                    analysis.cli_flags += len(
                        re.findall(r"(?<![\w-])--?[A-Za-z0-9][A-Za-z0-9-]*", token.content)
                    )
                    if language in {"python", "py"} and re.search(
                        r"\b(?:def|class)\b.*(?:->|:\s*[A-Za-z_])",
                        token.content,
                    ):
                        analysis.python_typed += 1

            if levels:
                analysis.first_heading_levels[levels[0]] += 1
                analysis.heading_sequences.append(levels)
                for current, following in pairwise(levels):
                    analysis.heading_transitions[(current, following)] += 1

            prose = "\n".join(prose_parts)
            analysis.second_person += len(
                re.findall(r"\b(?:you|your|yours)\b", prose, re.IGNORECASE)
            )
            analysis.first_plural += len(
                re.findall(r"\b(?:we|our|ours)\b", prose, re.IGNORECASE)
            )
            analysis.prose_words += len(re.findall(r"[A-Za-z][A-Za-z'-]*", prose))
            sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+|\n+", prose)
                if sentence.strip()
            ]
            analysis.prose_sentences += len(sentences)
            analysis.imperative_sentences += sum(
                1
                for sentence in sentences
                if sentence.split(maxsplit=1)[0].lower().strip("`*_") in _IMPERATIVE_VERBS
            )

            stripped = _FENCE_RE.sub("", markdown)
            analysis.table_count += len(_TABLE_RE.findall(stripped))
            analysis.callouts.update(
                match.upper() for match in _CALLOUT_RE.findall(stripped)
            )
            analysis.doc_anchor_count += len(_DOC_ANCHOR_RE.findall(stripped))
            analysis.bullet_count += len(
                re.findall(r"(?m)^\s{0,3}[-*+]\s+\S", stripped)
            )

        return analysis

    async def _refine_with_llm(
        self,
        repo_full_name: str,
        skill: DocStyleSkill,
    ) -> DocStyleSkill:
        assert self._llm_client is not None
        user_prompt = (
            f"Repository: {repo_full_name}\n\n"
            f"Tone: {skill.tone_and_voice}\n\n"
            f"Heading rules:\n"
            + "\n".join(f"- {rule}" for rule in skill.heading_conventions)
            + "\n\nCode rules:\n"
            + "\n".join(f"- {rule}" for rule in skill.code_block_rules)
            + "\n\nFormatting rules:\n"
            + "\n".join(f"- {rule}" for rule in skill.formatting_patterns)
            + "\n\nDeterministic draft:\n"
            + skill.skill_markdown
        )
        try:
            refined = await self._llm_client.generate_text(
                _REFINE_SYSTEM_PROMPT,
                user_prompt,
            )
            refined = refined.strip()
            if refined.startswith("---") and "name:" in refined:
                return skill.model_copy(update={"skill_markdown": refined})
        except Exception:
            logger.warning(
                "LLM style refinement failed for %s; using deterministic skill",
                repo_full_name,
                exc_info=True,
            )
        return skill


def _plain_inline_text(token) -> str:
    """Return visible inline text without emphasis/link markup."""
    if not token.children:
        return token.content.strip()
    parts: list[str] = []
    for child in token.children:
        if child.type in {"text", "code_inline"}:
            parts.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append(" ")
        elif child.type == "image" and child.content:
            parts.append(child.content)
    return "".join(parts).strip()


def _tone_and_voice(analysis: _DocAnalysis) -> str:
    if analysis.prose_sentences == 0:
        return (
            "Concise reference-style technical voice: declarative present tense, "
            "sparse narration, and definition-first examples."
        )

    imperative_ratio = analysis.imperative_sentences / analysis.prose_sentences
    average_sentence = round(analysis.prose_words / max(analysis.prose_sentences, 1))

    if analysis.imperative_sentences >= 2 and (
        analysis.second_person > 0 or imperative_ratio >= 0.2
    ):
        tone = (
            "Direct, tutorial-first technical voice: short imperative steps, "
            "active present tense, and second-person guidance."
        )
    elif analysis.second_person > 1:
        tone = (
            "Conversational technical voice: active present tense with "
            "second-person guidance."
        )
    elif analysis.first_plural > 1:
        tone = (
            "Collaborative reference-style voice: declarative present tense "
            "with occasional first-person plural framing."
        )
    else:
        tone = (
            "Concise reference-style technical voice: declarative present tense, "
            "terse definitions, and minimal narration."
        )

    return f"{tone} Average sentence length is about {average_sentence} words."


def _heading_conventions(analysis: _DocAnalysis) -> list[str]:
    if not analysis.heading_levels:
        return [
            "No ATX headings were observed; introduce one `#` title followed by `##` sections.",
            "Keep heading text short, unique, and descriptive.",
        ]

    level_counts = ", ".join(
        f"`{'#' * level}` ({count})"
        for level, count in sorted(analysis.heading_levels.items())
    )
    start_level = analysis.first_heading_levels.most_common(1)[0][0]
    rules = [
        f"Use ATX headings; observed levels are {level_counts}.",
        f"Start documents at H{start_level}.",
    ]

    transitions = [
        (transition, count)
        for transition, count in analysis.heading_transitions.most_common(3)
    ]
    if transitions:
        rendered = ", ".join(
            f"`{'#' * source}` -> `{'#' * target}` ({count})"
            for (source, target), count in transitions
        )
        rules.append(f"Preserve the dominant heading hierarchy: {rendered}.")

    if analysis.emoji_headings:
        rules.append(
            "Keep emoji prefixes in headings where the repository already uses them."
        )
    if analysis.numbered_headings:
        rules.append("Preserve numbered heading prefixes such as `1.` or `1.2`.")

    common_headings = [
        heading
        for heading, _ in Counter(
            heading for heading in analysis.heading_texts if heading
        ).most_common(6)
    ]
    if common_headings:
        rules.append(
            "Reuse the established section vocabulary: "
            + ", ".join(f"`{heading}`" for heading in common_headings)
            + "."
        )
    return rules


def _code_block_rules(analysis: _DocAnalysis) -> list[str]:
    if analysis.fence_count == 0:
        return [
            "Use fenced code blocks with an explicit language tag for commands and examples.",
            "Wrap identifiers, filenames, flags, and environment variables in inline backticks.",
        ]

    languages = ", ".join(f"`{lang}`" for lang in sorted(analysis.languages))
    rules = [f"Tag every fenced block with a language; observed tags are {languages}."]
    if analysis.untagged_fences:
        rules.append("Do not leave fenced blocks untagged.")

    shell_languages = {"bash", "sh", "shell", "console", "zsh"}
    if shell_languages.intersection(analysis.languages):
        rules.append("Use `bash` fences for terminal commands and expected output.")
    if analysis.curl_examples:
        rules.append("Keep HTTP examples copy-pasteable as complete `curl` commands.")
    if analysis.cli_flags:
        rules.append("Show CLI flags literally inside command fences (for example, `--flag`).")
    if {"python", "py"}.intersection(analysis.languages):
        typed = (
            " Include typed signatures and runnable call sites."
            if analysis.python_typed
            else " Keep Python snippets runnable and import-complete."
        )
        rules.append("Use `python` fences for Python API examples." + typed)
    if "json" in analysis.languages:
        rules.append("Use `json` fences for request and response payloads.")
    return rules


def _formatting_patterns(analysis: _DocAnalysis) -> list[str]:
    patterns: list[str] = []
    if analysis.table_count:
        patterns.append(
            "Use GitHub-flavored pipe tables with a header row and `---` separator row."
        )
    if analysis.callouts:
        labels = ", ".join(f"`> [!{label}]`" for label in sorted(analysis.callouts))
        patterns.append(f"Use alert-style callouts such as {labels} for caveats.")
    if analysis.inline_code_count:
        patterns.append(
            "Wrap symbols, parameters, filenames, flags, and env vars in inline backticks."
        )
    if analysis.doc_anchor_count:
        patterns.append(
            "Preserve `<!-- doc-anchor: symbol -->` HTML comments immediately above "
            "documented sections; they are primary drift anchors."
        )
    if analysis.bullet_count:
        patterns.append("Use short bullet lists for options, requirements, and steps.")
    if not patterns:
        patterns.append(
            "Prefer clean CommonMark: short paragraphs, bullet lists, and inline code."
        )
    return patterns


def _render_skill_markdown(
    *,
    repo_full_name: str,
    tone: str,
    headings: list[str],
    code_rules: list[str],
    formatting: list[str],
) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", repo_full_name.lower()).strip("-")
    slug = slug or "repository"
    description = (
        f"Repository-specific documentation writing and structure rules for "
        f"{repo_full_name}, mined from its existing Markdown."
    )
    heading_lines = "\n".join(f"- {rule}" for rule in headings)
    code_lines = "\n".join(f"- {rule}" for rule in code_rules)
    formatting_lines = "\n".join(f"- {rule}" for rule in formatting)

    return f"""---
name: {slug}-doc-style
description: {description}
---

# {repo_full_name} Documentation Style Skill

## Tone and voice
{tone}

## Heading conventions
{heading_lines}

## Code block conventions
{code_lines}

## Formatting and anchors
{formatting_lines}

## Non-negotiable output checklist
- Match the existing heading depth and section vocabulary.
- Preserve the repository's tone, code-fence languages, tables, callouts, and anchors.
- Update only the impacted section; never rewrite unrelated prose.
- Keep every `<!-- doc-anchor: ... -->` comment and balanced code fence intact.
"""
