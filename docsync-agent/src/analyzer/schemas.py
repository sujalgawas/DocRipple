"""Internal AST span models used by the analyzer."""

from pydantic import BaseModel


class ASTSpan(BaseModel):
    """A tree-sitter capture — symbol name, kind, and location."""

    name: str
    kind: str  # function_definition, class_definition, etc.
    start_line: int
    end_line: int
    source: str  # raw source bytes of the captured node


class FileChange(BaseModel):
    """Parsed representation of one file in a unified diff."""

    path: str
    added_lines: list[str] = []
    removed_lines: list[str] = []
    hunks: list[str] = []