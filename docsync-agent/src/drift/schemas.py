"""Drift-specific schemas."""

from pydantic import BaseModel


class DocSectionNode(BaseModel):
    """A parsed documentation section with optional anchor."""

    heading: str
    level: int  # 1 = H1, 2 = H2, ...
    anchor: str | None
    content: str
    doc_path: str
    start_line: int
    end_line: int