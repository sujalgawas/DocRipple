"""Internal symbol span models used by the analyzer."""

from pydantic import BaseModel


class ExtractedSymbolSpan(BaseModel):
    """A symbol extracted from source code — name, kind, location, and decorators."""

    name: str
    kind: str  # "function" | "class" | "method" | "route"
    signature: str
    start_line: int
    end_line: int
    decorators: list[str] = []