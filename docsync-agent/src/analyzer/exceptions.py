"""Analyzer-specific exceptions."""


class DiffParseError(ValueError):
    """Failed to parse the unified diff."""


class GrammarLoadError(RuntimeError):
    """Failed to load a tree-sitter grammar for the target language."""