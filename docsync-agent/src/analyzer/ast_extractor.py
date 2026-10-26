"""Tree-sitter symbol and signature extraction."""

import logging

from src.analyzer.exceptions import GrammarLoadError
from src.analyzer.schemas import ASTSpan, FileChange

logger = logging.getLogger(__name__)

# Language → file extension mapping for grammar inference
_EXTENSION_GRAMMAR: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".rs": "rust",
    ".go": "go",
}


async def extract_symbols(file_change: FileChange) -> list[ASTSpan]:
    """Extract symbol definitions from a changed file using tree-sitter.

    Currently a stub — tree-sitter implementation to be wired in.
    """
    logger.debug("Extracting symbols from %s", file_change.path)
    # TODO: Initialize tree-sitter parser, load appropriate grammar,
    #       query for function/class/method definitions, capture spans.
    return []