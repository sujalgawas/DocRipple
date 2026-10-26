"""Analyzer-specific exceptions."""


class DiffParseError(Exception):
    """Failed to parse the unified diff."""


class SymbolExtractionError(Exception):
    """Failed to extract symbols from source code (tree-sitter grammar or AST error)."""