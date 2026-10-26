"""Drift-specific schemas produced by the Markdown parser."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocSectionNode(BaseModel):
    """One heading-delimited section of a Markdown document.

    Line numbers are 1-indexed and ``end_line`` is inclusive.  ``raw_markdown``
    contains the heading line as well as the section body so callers can pass it
    directly to a writer without reconstructing the document.
    """

    doc_path: str
    heading: str
    level: int
    start_line: int
    end_line: int
    raw_markdown: str
    explicit_anchors: set[str] = Field(default_factory=set)
    inline_code_tokens: set[str] = Field(default_factory=set)
