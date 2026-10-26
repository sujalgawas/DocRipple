"""Line-accurate Markdown section parsing and anchor extraction.

The parser is intentionally deterministic.  It uses ``markdown-it-py`` only to
identify ATX headings, inline code spans, and fenced/indented code blocks; all
line numbers are derived from the token source maps so callers get exact
1-indexed, inclusive ranges.
"""

from __future__ import annotations

import re

from markdown_it import MarkdownIt
from markdown_it.token import Token

from src.drift.schemas import DocSectionNode

_MD = MarkdownIt("commonmark")

_DOC_ANCHOR_RE = re.compile(
    r"<!--\s*doc-anchor\s*:\s*(?P<value>.*?)\s*-->",
    re.IGNORECASE | re.DOTALL,
)
_SYMBOL_ANCHOR_RE = re.compile(
    r"<!--\s*@symbol\s*:\s*(?P<value>.*?)\s*-->",
    re.IGNORECASE | re.DOTALL,
)
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CLI_FLAG_RE = re.compile(r"(?<![\w-])--?[A-Za-z0-9][A-Za-z0-9-]*")
_ATX_HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})[ \t]+(?P<text>.*?)(?:[ \t]+#+[ \t]*)?$")


def _plain_inline_text(token: Token) -> str:
    """Return visible text for an inline token, dropping emphasis/link markup."""
    if not token.children:
        return token.content.strip()

    parts: list[str] = []
    for child in token.children:
        if child.type in {"text", "code_inline"}:
            parts.append(child.content)
        elif child.type in {"softbreak", "hardbreak"}:
            parts.append(" ")
        elif child.type == "image" and child.content:
            # The alt text is stored on the image token itself.
            parts.append(child.content)
    return "".join(parts).strip()


def _iter_headings(markdown: str, lines: list[str]) -> list[tuple[int, int, str]]:
    """Yield ``(zero_based_start, level, heading_text)`` for ATX headings."""
    tokens = _MD.parse(markdown)
    headings: list[tuple[int, int, str]] = []

    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.map is None:
            continue

        level_text = token.tag[1:] if token.tag.startswith("h") else ""
        level = int(level_text) if level_text.isdigit() else 1

        heading = ""
        if index + 1 < len(tokens) and tokens[index + 1].type == "inline":
            heading = _plain_inline_text(tokens[index + 1])

        if not heading:
            source = lines[token.map[0]]
            match = _ATX_HEADING_RE.match(source.lstrip())
            if match:
                heading = match.group("text").strip()

        if heading:
            headings.append((token.map[0], level, heading))

    return headings


def _collect_anchor_values(fragment: str, anchors: set[str]) -> None:
    """Collect anchors from one HTML token's content."""
    for pattern in (_DOC_ANCHOR_RE, _SYMBOL_ANCHOR_RE):
        for match in pattern.finditer(fragment):
            raw_value = match.group("value")
            for candidate in re.split(r"[,\s]+", raw_value):
                anchor = candidate.strip().strip("`")
                if anchor:
                    anchors.add(anchor)


def extract_explicit_anchors(markdown: str) -> set[str]:
    """Extract HTML-comment anchors from a Markdown fragment.

    Supported forms::

        <!-- doc-anchor: create_user, other_symbol -->
        <!-- @symbol: func_name -->

    Anchors are case-sensitive and returned exactly as written (aside from
    surrounding whitespace/backticks).  HTML comments inside fenced code blocks
    are treated as example text and ignored.
    """
    anchors: set[str] = set()
    for token in _MD.parse(markdown):
        if token.type == "html_block":
            _collect_anchor_values(token.content, anchors)
        elif token.type == "inline":
            for child in token.children or []:
                if child.type == "html_inline":
                    _collect_anchor_values(child.content, anchors)
    return anchors


def extract_inline_code_tokens(markdown: str) -> set[str]:
    """Extract inline code spans and identifiers from fenced code blocks.

    Inline code is kept verbatim because CLI flags such as ``--dry-run`` and
    environment variables such as ``MAX_RETRIES`` cannot be reconstructed from
    a generic identifier tokenizer.  Fenced/indented code blocks contribute
    their language identifier plus identifiers and CLI flags found in the body.
    """
    tokens: set[str] = set()
    for token in _MD.parse(markdown):
        if token.type == "inline":
            for child in token.children or []:
                if child.type == "code_inline":
                    content = child.content.strip()
                    if content:
                        tokens.add(content)
        elif token.type in {"fence", "code_block"}:
            info = (token.info or "").strip()
            if info:
                language = info.split()[0].strip("{}.")
                if language:
                    tokens.add(language)
            tokens.update(_IDENTIFIER_RE.findall(token.content))
            tokens.update(_CLI_FLAG_RE.findall(token.content))
    return tokens


def parse_markdown_sections(markdown: str, doc_path: str) -> list[DocSectionNode]:
    """Split ``markdown`` into flat, heading-delimited sections.

    A section starts on its heading line and ends on the line immediately before
    the next ATX heading (regardless of level), or at end-of-file for the last
    section.  Content before the first heading is ignored.
    """
    if not markdown:
        return []

    lines = markdown.splitlines()
    if not lines:
        return []

    headings = _iter_headings(markdown, lines)
    sections: list[DocSectionNode] = []

    for position, (start_index, level, heading) in enumerate(headings):
        if position + 1 < len(headings):
            end_index = headings[position + 1][0] - 1
        else:
            end_index = len(lines) - 1

        end_index = max(end_index, start_index)

        raw_markdown = "\n".join(lines[start_index : end_index + 1])
        sections.append(
            DocSectionNode(
                doc_path=doc_path,
                heading=heading,
                level=level,
                start_line=start_index + 1,
                end_line=end_index + 1,
                raw_markdown=raw_markdown,
                explicit_anchors=extract_explicit_anchors(raw_markdown),
                inline_code_tokens=extract_inline_code_tokens(raw_markdown),
            )
        )

    return sections


# Friendly alias for callers that prefer the shorter name.
def parse_markdown(markdown: str, doc_path: str) -> list[DocSectionNode]:
    """Alias for :func:`parse_markdown_sections`."""
    return parse_markdown_sections(markdown, doc_path)


async def extract_doc_sections(markdown: str, doc_path: str) -> list[DocSectionNode]:
    """Async compatibility wrapper around :func:`parse_markdown_sections`."""
    return parse_markdown_sections(markdown, doc_path)


async def extract_anchors(markdown: str) -> set[str]:
    """Return every explicit HTML-comment anchor in ``markdown``."""
    return extract_explicit_anchors(markdown)
