"""Tree-sitter symbol extraction with Python ast fallback.

Uses `tree-sitter-language-pack.get_parser(lang)` as the primary path for
all supported languages, with stdlib `ast` fallback for ``.py`` files in
constrained environments where tree-sitter grammars are unavailable.
"""

from __future__ import annotations

import ast
import logging
import os
from typing import TYPE_CHECKING, Any

from src.analyzer.exceptions import SymbolExtractionError
from src.analyzer.schemas import ExtractedSymbolSpan

if TYPE_CHECKING:
    from tree_sitter import Node

logger = logging.getLogger(__name__)

# ── Language support ──────────────────────────────────────────────────────

_LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
}

# Node `type` names that represent function/class/method definitions per language.
_FUNC_LIKE_NODE_TYPES: dict[str, set[str]] = {
    "python": {"function_definition", "class_definition"},
    "typescript": {
        "function_declaration",
        "class_declaration",
        "method_definition",
        "arrow_function",
        "lexical_declaration",  # `const x = () => {}` or `function x() {}`
    },
    "javascript": {
        "function_declaration",
        "class_declaration",
        "method_definition",
        "arrow_function",
        "lexical_declaration",
    },
    "go": {"function_declaration", "method_declaration", "type_declaration"},
    "rust": {"function_item", "struct_item", "impl_item", "trait_item"},
}

# Decorator-like node types per language.
_DECORATOR_NODE_TYPES: dict[str, set[str]] = {
    "python": {"decorator"},
    "typescript": {"decorator", "decorator_factory", "decorator_call_expression"},
    "javascript": {"decorator", "decorator_factory", "decorator_call_expression"},
}


# ── Public API ────────────────────────────────────────────────────────────

def extract_symbols_from_source(
    source: str | bytes,
    file_path: str,
) -> list[ExtractedSymbolSpan]:
    """Extract top-level functions, classes, methods, and route decorators.

    Tries tree-sitter first. Falls back to Python ``ast`` for ``.py`` files
    when tree-sitter is unavailable or fails.
    """
    if not source:
        return []

    ext = os.path.splitext(file_path)[1].lower()
    lang = _LANG_BY_EXT.get(ext)

    # ── Tree-sitter path ──
    if lang is not None:
        try:
            return _extract_with_tree_sitter(source, lang, file_path)
        except Exception:
            logger.debug(
                "tree-sitter extraction failed for %s (%s); trying fallback",
                file_path,
                lang,
                exc_info=True,
            )

    # ── Python ast fallback ──
    if ext == ".py":
        try:
            source_str = source if isinstance(source, str) else source.decode("utf-8")
            return _extract_with_python_ast(source_str, file_path)
        except Exception:
            logger.debug("Python ast fallback also failed for %s", file_path, exc_info=True)

    return []


# ── Tree-sitter extraction ────────────────────────────────────────────────

def _extract_with_tree_sitter(
    source: str | bytes,
    lang: str,
    file_path: str,
) -> list[ExtractedSymbolSpan]:
    """Extract symbols using tree-sitter-language-pack."""
    from tree_sitter_language_pack import get_parser

    source_bytes = source if isinstance(source, bytes) else source.encode("utf-8")
    parser = get_parser(lang)
    tree = parser.parse(source_bytes)
    root = tree.root_node

    func_types = _FUNC_LIKE_NODE_TYPES.get(lang, set())
    decorator_types = _DECORATOR_NODE_TYPES.get(lang, set())

    symbols: list[ExtractedSymbolSpan] = []

    def _walk(node: Node) -> None:
        if node.type in func_types:
            symbol = _node_to_span(node, source_bytes, lang, file_path, decorator_types)
            if symbol is not None:
                symbols.append(symbol)

        for child in node.named_children:
            _walk(child)

    _walk(root)
    return symbols


def _node_to_span(
    node: Any,
    source_bytes: bytes,
    lang: str,
    file_path: str,
    decorator_types: set[str],
) -> ExtractedSymbolSpan | None:
    """Convert a tree-sitter node to an ExtractedSymbolSpan."""
    # Find the name child
    name_text = ""
    kind = _map_node_type(lang, node.type)

    for child in node.named_children:
        if child.type == "identifier" or child.type == "property_identifier":
            name_text = child.text.decode("utf-8") if child.text else ""
            break

    if not name_text:
        return None

    # Build signature: first line of the definition
    sig_lines = source_bytes[node.start_byte : node.end_byte].decode("utf-8")
    sig_first_line = sig_lines.split("\n")[0].strip()

    # Extract decorators from sibling/parent nodes
    decorators: list[str] = []
    _collect_decorators(node, decorators, decorator_types)

    # Check for route decorators → override kind
    if _has_route_decorator(decorators):
        kind = "route"

    return ExtractedSymbolSpan(
        name=name_text,
        kind=kind,
        signature=sig_first_line,
        start_line=node.start_point.row + 1,
        end_line=node.end_point.row + 1,
        decorators=decorators,
    )


def _collect_decorators(
    node: Any,
    decorators: list[str],
    decorator_types: set[str],
) -> None:
    """Walk previous siblings / parent children for decorator nodes."""
    # For Python, decorators are previous named siblings of the decorated node.
    # For TS/JS, decorators may be children of the function/class node.
    if node.parent is not None:
        for child in node.parent.named_children:
            if child.type in decorator_types:
                text = child.text.decode("utf-8") if child.text else ""
                decorators.append(text)


def _has_route_decorator(decorators: list[str]) -> bool:
    """Check if any decorator is a FastAPI/Flask/Express route."""
    route_keywords = (
        "@router.",
        "@app.",
        "@bp.",
        "@blueprint.",
        ".get(",
        ".post(",
        ".put(",
        ".delete(",
        ".patch(",
        ".route(",
    )
    return any(
        any(kw in dec for kw in route_keywords)
        for dec in decorators
    )


def _map_node_type(lang: str, node_type: str) -> str:
    """Map a tree-sitter node type to a canonical symbol kind."""
    class_like = {
        "class_definition", "class_declaration", "struct_item",
        "trait_item", "type_declaration",
    }
    method_like = {"method_definition", "method_declaration"}

    if node_type in class_like:
        return "class"
    if node_type in method_like:
        return "method"
    return "function"


# ── Python stdlib ast fallback ────────────────────────────────────────────

def _extract_with_python_ast(
    source: str,
    file_path: str,
) -> list[ExtractedSymbolSpan]:
    """Extract symbols from Python source using the stdlib ``ast`` module."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise SymbolExtractionError(f"Syntax error in {file_path}: {exc}") from exc

    symbols: list[ExtractedSymbolSpan] = []

    for node in ast.iter_child_nodes(tree):
        span = _ast_node_to_span(node, source)
        if span is not None:
            symbols.append(span)

    return symbols


def _ast_node_to_span(node: ast.AST, source: str) -> ExtractedSymbolSpan | None:
    """Convert an ast node to an ExtractedSymbolSpan."""
    decorators: list[str] = []

    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        name = node.name
        decorators = [ast.unparse(d) for d in node.decorator_list]

        # Build signature
        args_part = _build_function_args(node.args)
        returns_part = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        sig = f"{'async ' if isinstance(node, ast.AsyncFunctionDef) else ''}def {name}({args_part}){returns_part}:"

        kind = "function"
        if _has_route_decorator(decorators):
            kind = "route"
        # Check if it's inside a class (method) — for top-level only we don't need this,
        # but extract_methods handles nested
        return ExtractedSymbolSpan(
            name=name,
            kind=kind,
            signature=sig,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            decorators=decorators,
        )

    if isinstance(node, ast.ClassDef):
        name = node.name
        decorators = [ast.unparse(d) for d in node.decorator_list]
        # Collect bases for signature
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        sig = f"class {name}({bases}):" if bases else f"class {name}:"

        span = ExtractedSymbolSpan(
            name=name,
            kind="class",
            signature=sig,
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            decorators=decorators,
        )

        # Also extract methods from within the class
        for body_item in node.body:
            method_span = _ast_node_to_span(body_item, source)
            if method_span is not None and method_span.kind == "function":
                method_span.kind = "method"

        return span

    return None


def _build_function_args(args: ast.arguments) -> str:
    """Build a string representation of function arguments."""
    parts: list[str] = []

    # Positional args
    for arg in args.args:
        annotation = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        parts.append(f"{arg.arg}{annotation}")

    # *args
    if args.vararg:
        annotation = f": {ast.unparse(args.vararg.annotation)}" if args.vararg.annotation else ""
        parts.append(f"*{args.vararg.arg}{annotation}")

    # Keyword-only args
    for arg in args.kwonlyargs:
        annotation = f": {ast.unparse(arg.annotation)}" if arg.annotation else ""
        parts.append(f"{arg.arg}{annotation}")

    # **kwargs
    if args.kwarg:
        annotation = f": {ast.unparse(args.kwarg.annotation)}" if args.kwarg.annotation else ""
        parts.append(f"**{args.kwarg.arg}{annotation}")

    return ", ".join(parts)