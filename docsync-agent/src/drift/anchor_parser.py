"""markdown-it-py section splitter and anchor extractor."""

import logging

from markdown_it import MarkdownIt
from markdown_it.token import Token

from src.drift.schemas import DocSectionNode

logger = logging.getLogger(__name__)

md_parser = MarkdownIt()


async def extract_doc_sections(markdown: str, doc_path: str) -> list[DocSectionNode]:
    """Parse markdown into heading-delimited sections with anchors."""
    tokens: list[Token] = md_parser.parse(markdown)
    sections: list[DocSectionNode] = []

    current_heading = ""
    current_level = 1
    current_anchor: str | None = None
    content_lines: list[str] = []
    start_line = 1

    for token in tokens:
        if token.type == "heading_open":
            current_level = int(token.tag[1])  # h1 → 1, h2 → 2
        elif token.type == "inline" and content_lines == []:
            # Heading text
            current_heading = token.content
            anchor = current_heading.lower().replace(" ", "-")
            current_anchor = anchor
            start_line = token.map[0] + 1 if token.map else 1
        elif token.type == "heading_close":
            if current_heading:
                sections.append(
                    DocSectionNode(
                        heading=current_heading,
                        level=current_level,
                        anchor=current_anchor,
                        content="",
                        doc_path=doc_path,
                        start_line=start_line,
                        end_line=start_line,
                    )
                )
            current_heading = ""
        else:
            if token.content and current_heading:
                content_lines.append(token.content)

    return sections


async def extract_anchors(markdown: str) -> set[str]:
    """Extract all heading-derived anchor IDs from markdown."""
    tokens = md_parser.parse(markdown)
    anchors: set[str] = set()
    for token in tokens:
        if token.type == "inline" and token.content:
            anchors.add(token.content.lower().replace(" ", "-"))
    return anchors