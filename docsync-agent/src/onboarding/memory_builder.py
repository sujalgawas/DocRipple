"""Repository memory-map construction for Stage 0 onboarding.

The builder is deterministic and CPU-bound; all parsing runs in Starlette's
thread pool. It reuses the analyzer's AST extractor and the drift engine's
Markdown section parser so the memory graph and runtime drift graph agree.
"""

from __future__ import annotations

import ast
import json
import logging
import posixpath
import re
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi.concurrency import run_in_threadpool

from src.analyzer.ast_extractor import extract_symbols_from_source
from src.analyzer.schemas import ExtractedSymbolSpan
from src.contracts.schemas import CodeDocEdge, MemoryEdge, MemoryNode, RepoMemoryMap
from src.drift.anchor_parser import parse_markdown_sections
from src.drift.schemas import DocSectionNode

logger = logging.getLogger(__name__)

_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_PYTHON_EXT = ".py"
_JS_IMPORT_RE = re.compile(
    r"""(?:from\s*|require\s*\(\s*|import\s*\(\s*)['"]([^'"]+)['"]"""
)
_GO_IMPORT_RE = re.compile(r'(?m)^\s*(?:import\s+)?"([^"]+)"')
_RUST_USE_RE = re.compile(r"(?m)^\s*use\s+([^;]+);")

_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
_CODE_EXTENSIONS = {
    _PYTHON_EXT,
    *_JS_EXTENSIONS,
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".rb",
    ".php",
}


@dataclass(frozen=True, slots=True)
class MemoryBuildResult:
    """The memory map plus the initial symbol-to-doc edges discovered while building."""

    memory_map: RepoMemoryMap
    code_doc_edges: list[CodeDocEdge]


class RepoMemoryMapBuilder:
    """Build module, file, symbol, and doc-section nodes with typed edges."""

    async def build(
        self,
        repo_full_name: str,
        code_files: dict[str, str],
        docs: dict[str, str],
    ) -> RepoMemoryMap:
        """Build and return the repository memory map."""
        result = await self.build_with_edges(repo_full_name, code_files, docs)
        return result.memory_map

    async def build_with_edges(
        self,
        repo_full_name: str,
        code_files: dict[str, str],
        docs: dict[str, str],
    ) -> MemoryBuildResult:
        """Build the map and the initial ``CodeDocEdge`` records."""
        return await run_in_threadpool(
            self._build_sync,
            repo_full_name,
            code_files,
            docs,
        )

    async def build_memory_map(
        self,
        repo_full_name: str,
        code_files: dict[str, str],
        docs: dict[str, str],
    ) -> RepoMemoryMap:
        """Alias for :meth:`build`."""
        return await self.build(repo_full_name, code_files, docs)

    # ── Synchronous core ─────────────────────────────────────────────────

    def _build_sync(
        self,
        repo_full_name: str,
        code_files: dict[str, str],
        docs: dict[str, str],
    ) -> MemoryBuildResult:
        code_files = {
            _normalize_path(path): source or ""
            for path, source in code_files.items()
            if path
        }
        docs = {
            _normalize_path(path): content or ""
            for path, content in docs.items()
            if path
        }
        code_paths = set(code_files)

        nodes: dict[str, MemoryNode] = {}
        edges: dict[tuple[str, str, str], MemoryEdge] = {}

        def add_node(node: MemoryNode) -> None:
            nodes.setdefault(node.node_id, node)

        def add_edge(source_id: str, target_id: str, relation: str) -> None:
            if source_id == target_id:
                return
            edges.setdefault(
                (source_id, target_id, relation),
                MemoryEdge(
                    repo_full_name=repo_full_name,
                    source_id=source_id,
                    target_id=target_id,
                    relation=relation,
                ),
            )

        # ── Modules and files ────────────────────────────────────────────
        modules: set[str] = set()
        module_file_counts: Counter[str] = Counter()
        for path in sorted(code_paths):
            directory = posixpath.dirname(path) or "."
            module_file_counts[directory] += 1
            if directory == ".":
                modules.add(".")
            else:
                parts = directory.split("/")
                for index in range(1, len(parts) + 1):
                    modules.add("/".join(parts[:index]))

        for module in sorted(modules):
            direct_files = module_file_counts[module]
            descendant_files = sum(
                count
                for directory, count in module_file_counts.items()
                if directory == module
                or (module == "." and directory != ".")
                or directory.startswith(f"{module}/")
            )
            add_node(
                MemoryNode(
                    node_id=f"module:{module}",
                    repo_full_name=repo_full_name,
                    node_type="module",
                    name=module,
                    path=module,
                    summary=(
                        f"Package directory containing {descendant_files} "
                        f"source file(s)."
                    ),
                    metadata_json=json.dumps(
                        {
                            "direct_files": direct_files,
                            "descendant_files": descendant_files,
                        },
                        sort_keys=True,
                    ),
                )
            )

        for module in sorted(modules):
            if module == ".":
                continue
            parent = posixpath.dirname(module)
            parent_module: str | None
            if parent in modules:
                parent_module = parent
            elif not parent and "." in modules:
                parent_module = "."
            else:
                parent_module = None
            if parent_module is not None:
                add_edge(
                    f"module:{parent_module}",
                    f"module:{module}",
                    "CONTAINS",
                )

        symbol_records: list[tuple[str, ExtractedSymbolSpan]] = []

        for path in sorted(code_files):
            source = code_files[path]
            line_count = len(source.splitlines())
            module = posixpath.dirname(path) or "."
            file_summary = _file_summary(source, path, line_count)
            add_node(
                MemoryNode(
                    node_id=f"file:{path}",
                    repo_full_name=repo_full_name,
                    node_type="file",
                    name=posixpath.basename(path),
                    path=path,
                    summary=file_summary,
                    metadata_json=json.dumps(
                        {"extension": posixpath.splitext(path)[1].lower()},
                        sort_keys=True,
                    ),
                )
            )
            add_edge(f"module:{module}", f"file:{path}", "CONTAINS")

            docstrings = _python_symbol_docstrings(source, path)
            seen_symbol_names: set[str] = set()
            spans = [
                *_extract_symbols(source, path),
                *_extract_auxiliary_symbols(source, path),
            ]
            for span in spans:
                if span.name in seen_symbol_names:
                    continue
                seen_symbol_names.add(span.name)
                symbol_records.append((path, span))
                symbol_id = f"symbol:{path}::{span.name}"
                summary = span.signature
                docstring = docstrings.get(span.name)
                if docstring:
                    summary = f"{summary} - {docstring}"
                add_node(
                    MemoryNode(
                        node_id=symbol_id,
                        repo_full_name=repo_full_name,
                        node_type="symbol",
                        name=span.name,
                        path=path,
                        summary=summary,
                        metadata_json=json.dumps(
                            {
                                "kind": span.kind,
                                "start_line": span.start_line,
                                "end_line": span.end_line,
                                "decorators": span.decorators,
                            },
                            sort_keys=True,
                        ),
                    )
                )
                add_edge(f"file:{path}", symbol_id, "DEFINES")

        # ── Imports ──────────────────────────────────────────────────────
        for path in sorted(code_files):
            for imported in _extract_imports(code_files[path], path):
                target = _resolve_import(
                    importer_path=path,
                    imported=imported,
                    code_paths=code_paths,
                    modules=modules,
                )
                if target is not None:
                    add_edge(f"file:{path}", target, "IMPORTS")

        # ── Documentation sections & code-doc links ──────────────────────
        code_doc_edges: dict[tuple[str, str, str], CodeDocEdge] = {}
        used_doc_ids: set[str] = set()

        for doc_path in sorted(docs):
            for section in parse_markdown_sections(docs[doc_path], doc_path):
                doc_id = _doc_node_id(doc_path, section, used_doc_ids)
                used_doc_ids.add(doc_id)
                add_node(
                    MemoryNode(
                        node_id=doc_id,
                        repo_full_name=repo_full_name,
                        node_type="doc_section",
                        name=section.heading,
                        path=doc_path,
                        summary=_doc_section_summary(section),
                        metadata_json=json.dumps(
                            {
                                "level": section.level,
                                "start_line": section.start_line,
                                "end_line": section.end_line,
                                "explicit_anchors": sorted(section.explicit_anchors),
                                "inline_token_count": len(section.inline_code_tokens),
                            },
                            sort_keys=True,
                        ),
                    )
                )

                for file_path, span in symbol_records:
                    anchor_type = _match_anchor_type(span.name, section)
                    if anchor_type is None:
                        continue

                    add_edge(
                        f"symbol:{file_path}::{span.name}",
                        doc_id,
                        "DOCUMENTED_IN",
                    )
                    key = (span.name, doc_path, section.heading)
                    candidate = CodeDocEdge(
                        repo_full_name=repo_full_name,
                        symbol_name=span.name,
                        file_path=file_path,
                        doc_path=doc_path,
                        section_heading=section.heading,
                        anchor_type=anchor_type,
                    )
                    if (
                        key not in code_doc_edges
                        or candidate.anchor_type == "explicit_anchor"
                    ):
                        code_doc_edges[key] = candidate

        memory_map = RepoMemoryMap(
            repo_full_name=repo_full_name,
            nodes=sorted(nodes.values(), key=lambda node: node.node_id),
            edges=sorted(
                edges.values(),
                key=lambda edge: (edge.source_id, edge.target_id, edge.relation),
            ),
            updated_at=datetime.now(UTC),
        )
        initial_edges = sorted(
            code_doc_edges.values(),
            key=lambda edge: (edge.symbol_name, edge.doc_path, edge.section_heading),
        )
        return MemoryBuildResult(memory_map=memory_map, code_doc_edges=initial_edges)


def _normalize_path(path: str) -> str:
    """Normalize repository paths to POSIX form without a leading ``./``."""
    normalized = path.replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.lstrip("/")


def _extract_symbols(source: str, path: str) -> list[ExtractedSymbolSpan]:
    """Run the analyzer extractor defensively so one bad file cannot fail onboarding."""
    if posixpath.splitext(path)[1].lower() not in _CODE_EXTENSIONS:
        return []
    try:
        return extract_symbols_from_source(source, path)
    except Exception:
        logger.warning("Symbol extraction failed while onboarding %s", path, exc_info=True)
        return []


def _extract_auxiliary_symbols(
    source: str,
    path: str,
) -> list[ExtractedSymbolSpan]:
    """Extract CLI flags, environment variables, and config constants.

    ``ast_extractor`` covers callable/class/route symbols. Stage 0 additionally
    indexes the surfaces documentation commonly references but an AST walker
    alone does not model: ``--cli-flags``, environment variables, and uppercase
    configuration constants.
    """
    symbols: dict[str, ExtractedSymbolSpan] = {}
    extension = posixpath.splitext(path)[1].lower()

    def add(name: str, kind: str, signature: str, line: int) -> None:
        symbols.setdefault(
            name,
            ExtractedSymbolSpan(
                name=name,
                kind=kind,
                signature=signature,
                start_line=line,
                end_line=line,
                decorators=[],
            ),
        )

    for match in re.finditer(
        r"(?<![\w-])(--[A-Za-z0-9][A-Za-z0-9-]*)",
        source,
    ):
        add(
            match.group(1),
            "cli_flag",
            match.group(1),
            source.count("\n", 0, match.start()) + 1,
        )

    if extension == _PYTHON_EXT:
        for name, kind, signature, line in _python_auxiliary_symbols(source):
            add(name, kind, signature, line)
    else:
        for match in re.finditer(
            r"(?:process\.env|import\.meta\.env)\.([A-Z][A-Z0-9_]+)",
            source,
        ):
            add(
                match.group(1),
                "env_var",
                f"{match.group(0)}",
                source.count("\n", 0, match.start()) + 1,
            )

    for match in re.finditer(
        r"(?m)^\s*(?:export\s+)?(?:const\s+)?([A-Z][A-Z0-9_]{2,})\s*=",
        source,
    ):
        add(
            match.group(1),
            "config_var",
            match.group(0).strip(),
            source.count("\n", 0, match.start()) + 1,
        )

    return sorted(symbols.values(), key=lambda symbol: (symbol.start_line, symbol.name))


def _python_auxiliary_symbols(
    source: str,
) -> list[tuple[str, str, str, int]]:
    """Return ``(name, kind, signature, line)`` for Python env/config symbols."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    found: dict[str, tuple[str, str, str, int]] = {}

    def add(name: str, kind: str, signature: str, line: int) -> None:
        found.setdefault(name, (name, kind, signature, line))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_name = _python_expr_name(node.func)
            if (
                call_name.endswith(("getenv", "environ.get"))
                and node.args
                and isinstance(node.args[0], ast.Constant)
            ):
                value = node.args[0].value
                if isinstance(value, str) and value:
                    add(
                        value,
                        "env_var",
                        f"{call_name}({value!r})",
                        getattr(node, "lineno", 1),
                    )
        elif isinstance(node, ast.Subscript):
            base_name = _python_expr_name(node.value)
            if base_name in {"os.environ", "environ"}:
                key = node.slice
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    add(
                        key.value,
                        "env_var",
                        f"{base_name}[{key.value!r}]",
                        getattr(node, "lineno", 1),
                    )
        elif isinstance(node, ast.Attribute):
            base_name = _python_expr_name(node.value)
            if base_name in {"os.environ", "environ", "process.env"} and re.fullmatch(
                r"[A-Z][A-Z0-9_]+", node.attr
            ):
                add(
                    node.attr,
                    "env_var",
                    f"{base_name}.{node.attr}",
                    getattr(node, "lineno", 1),
                )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and re.fullmatch(
                    r"[A-Z][A-Z0-9_]{2,}", target.id
                ):
                    value = ast.unparse(node.value)[:100]
                    add(
                        target.id,
                        "config_var",
                        f"{target.id} = {value}",
                        getattr(node, "lineno", 1),
                    )

    return list(found.values())


def _python_expr_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _python_expr_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _file_summary(source: str, path: str, line_count: int) -> str:
    if posixpath.splitext(path)[1].lower() == _PYTHON_EXT:
        try:
            docstring = ast.get_docstring(ast.parse(source))
        except (SyntaxError, ValueError):
            docstring = None
        if docstring:
            return _first_line(docstring)
    language = posixpath.splitext(path)[1].lstrip(".").upper() or "Source"
    return f"{language} source file with {line_count} line(s)."


def _python_symbol_docstrings(source: str, path: str) -> dict[str, str]:
    if posixpath.splitext(path)[1].lower() != _PYTHON_EXT:
        return {}
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}

    docstrings: dict[str, str] = {}
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            docstring = ast.get_docstring(node)
            if docstring:
                docstrings[node.name] = _first_line(docstring)
    return docstrings


def _extract_imports(source: str, path: str) -> list[str]:
    extension = posixpath.splitext(path)[1].lower()
    if extension == _PYTHON_EXT:
        return _extract_python_imports(source)
    if extension in _JS_EXTENSIONS:
        return _JS_IMPORT_RE.findall(source)
    if extension == ".go":
        return _GO_IMPORT_RE.findall(source)
    if extension == ".rs":
        return [
            match.split(" as ", 1)[0].strip()
            for match in _RUST_USE_RE.findall(source)
        ]
    return []


def _extract_python_imports(source: str) -> list[str]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return []

    imports: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            module = node.module or ""
            imports.append(f"{prefix}{module}")
    return [value for value in imports if value]


def _resolve_import(
    *,
    importer_path: str,
    imported: str,
    code_paths: set[str],
    modules: set[str],
) -> str | None:
    """Resolve an import target to an internal file or module node id."""
    target = imported.strip().strip("'\"")
    if not target:
        return None

    if target.startswith("."):
        base = posixpath.dirname(importer_path)
        relative = posixpath.normpath(posixpath.join(base, target))
        return _match_file_or_module(relative, code_paths, modules)

    normalized = target.replace("::", ".").replace("/", ".")
    module_path = normalized.replace(".", "/")
    match = _match_file_or_module(module_path, code_paths, modules)
    if match is not None:
        return match

    # JavaScript/TypeScript absolute source imports are often written as
    # ``src/components/Button`` rather than dotted Python modules.
    return _match_file_or_module(target, code_paths, modules)


def _match_file_or_module(
    path: str,
    code_paths: set[str],
    modules: set[str],
) -> str | None:
    path = path.strip("/")
    if not path:
        return None

    candidates = [
        path,
        f"{path}.py",
        *(f"{path}{extension}" for extension in _JS_EXTENSIONS),
        *(f"{path}/index{extension}" for extension in _JS_EXTENSIONS),
        f"{path}/__init__.py",
    ]
    for candidate in candidates:
        if candidate in code_paths:
            return f"file:{candidate}"

    if path in modules:
        return f"module:{path}"
    return None


def _doc_node_id(
    doc_path: str,
    section: DocSectionNode,
    used_ids: set[str],
) -> str:
    base = f"doc:{doc_path}#{section.heading}"
    if base not in used_ids:
        return base
    return f"{base}@{section.start_line}"


def _doc_section_summary(section: DocSectionNode) -> str:
    for raw_line in section.raw_markdown.splitlines()[1:]:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("<!--", "```", "~~~", "|")):
            continue
        cleaned = re.sub(r"^[>#*+\-\d.\s]+", "", line)
        cleaned = cleaned.replace("**", "").replace("__", "").strip()
        if cleaned:
            return _first_line(cleaned)
    return f"Documentation section '{section.heading}'."


def _first_line(text: str) -> str:
    return next((line.strip() for line in text.splitlines() if line.strip()), "")


def _token_matches(symbol_name: str, tokens: set[str]) -> bool:
    if symbol_name in tokens:
        return True
    pattern = re.compile(rf"(?<![\w-]){re.escape(symbol_name)}(?![\w-])")
    return any(pattern.search(token) for token in tokens)


def _match_anchor_type(
    symbol_name: str,
    section: DocSectionNode,
) -> str | None:
    if symbol_name in section.explicit_anchors:
        return "explicit_anchor"
    if _token_matches(symbol_name, section.inline_code_tokens):
        return "inline_code"
    if symbol_name in _IDENTIFIER_RE.findall(section.heading):
        return "inline_code"
    return None
