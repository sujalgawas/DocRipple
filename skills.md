---
name: docsync-multi-agent-rules
description: Ground rules, module ownership boundaries, interface contracts, and handoff protocols for parallel coding agents building the standalone FastAPI + Tree-sitter + LangGraph Self-Updating Documentation Agent.
---

# Self-Updating Documentation Agent — Multi-Agent Ground Rules

## 1. Precedence & Conflict Resolution Rules
1. **Direct task instruction wins**: An explicit instruction in the current prompt overrides every file rule.
2. **Module ownership wins on file edits**: An agent assigned to `src/<module>/` must NEVER create or edit files outside `src/<module>/` and `tests/<module>/`.
3. **Contracts are frozen**: `src/contracts/` is strictly read-only during parallel module work. If a schema change is required, stop and escalate.
4. **Safety and determinism are non-overridable**: Never commit secrets, never import LLM clients inside `src/analyzer/`, `src/drift/`, or the default Stage 0 path, and never block the FastAPI async event loop.
5. **Stage 0 runs before Stage 1**: A repository must be onboarded before webhook processing can consume a `DocStyleSkill` or `RepoMemoryMap`. Both are optional inputs at runtime so older stores still work, but new code must persist and read them.

## 2. Module Ownership Matrix

| Stage | Module Path | Test Path | LLM Allowed? | Primary Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| **0. Onboarding** | `src/onboarding/` | `tests/onboarding/` | Optional style refinement only | `DocStyleSkillGenerator` mines Markdown conventions into a compiled `SKILL.md`; `RepoMemoryMapBuilder` indexes modules, files, AST symbols, and doc sections and pre-populates `code_doc_edges`. |
| **Contracts** | `src/contracts/` | `tests/contracts/` | No | Frozen Pydantic v2 schemas (`schemas.py`) and `typing.Protocol` interfaces (`protocols.py`). |
| **1. Ingest** | `src/ingest/` | `tests/ingest/` | No | FastAPI webhook (`POST /api/v1/webhooks/github`), HMAC-SHA256 verification, `X-GitHub-Delivery` dedupe via `ContextStore`, queue push. |
| **2. Analyzer** | `src/analyzer/` | `tests/analyzer/` | **Strictly No** | `unidiff` + `tree-sitter-language-pack` symbol extraction -> `API_SURFACE`, `CLI`, `ENV_CONFIG`, `DEPS`, `BEHAVIOR`. |
| **3. Drift Engine** | `src/drift/` | `tests/drift/` | **Strictly No** | `markdown-it-py` anchor extraction (`changed_symbols ∩ doc_anchors`) + `fastembed` cosine-similarity fallback for unanchored docs. |
| **4. Orchestrator** | `src/orchestrator/` | `tests/orchestrator/` | **Yes (Open Models)** | LangGraph `StateGraph` (`Planner -> Writer -> Verifier -> Reviewer -> Publisher`) + `AsyncSqliteSaver` + GitHub PR publisher with Evidence Table. Consumes `doc_style_skill` and `memory_subgraph`. |
| **5. ContextStore** | `src/context_store/` | `tests/context_store/` | No | `SqliteContextStore` (`aiosqlite` in WAL mode) storing style skills, memory nodes/edges, `code_doc_edges`, `webhook_deliveries`, `doc_embeddings`, and `run_traces`. |

## 3. Shared Data Contracts (`src/contracts/schemas.py`)

All cross-module calls must accept and return only these models. Every model is
frozen (`ConfigDict(frozen=True)`).

### Stages 1–5

```python
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, ConfigDict, Field

class ChangeClass(StrEnum):
    API_SURFACE = "api_surface"
    CLI = "cli"
    ENV_CONFIG = "env_config"
    DEPS = "deps"
    BEHAVIOR = "behavior"

class ChangedSymbol(BaseModel):
    model_config = ConfigDict(frozen=True)
    file_path: str
    symbol_name: str
    symbol_kind: str  # "function" | "class" | "method" | "route" | "cli_flag" | "env_var"
    change_class: ChangeClass
    old_signature: str | None = None
    new_signature: str | None = None
    diff_hunk: str

class ChangeReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    delivery_id: str
    repo_full_name: str
    base_sha: str
    head_sha: str
    changed_symbols: list[ChangedSymbol]

class CodeDocEdge(BaseModel):
    model_config = ConfigDict(frozen=True)
    repo_full_name: str
    symbol_name: str
    file_path: str
    doc_path: str
    section_heading: str
    anchor_type: str  # "explicit_anchor" | "inline_code" | "graph_edge" | "embedding"

class ImpactedDocSection(BaseModel):
    model_config = ConfigDict(frozen=True)
    doc_path: str
    heading: str
    start_line: int
    end_line: int
    matched_symbols: list[str]
    match_method: str  # "exact_anchor" | "graph_edge" | "inline_symbol" | "embedding_fallback"
    confidence: float = Field(ge=0.0, le=1.0)
    current_markdown: str

class DriftReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    change_report: ChangeReport
    impacted_sections: list[ImpactedDocSection]

class PublishResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    delivery_id: str
    pr_url: str | None = None
    pr_number: int | None = None
    evidence_table_md: str = ""
    verification_status: str  # "passed" | "repaired" | "failed"
    files_updated: list[str] = Field(default_factory=list)
    error: str | None = None
```

### Stage 0

```python
class DocStyleSkill(BaseModel):
    """Repository-specific writing/structure rules; `skill_markdown` is injectable verbatim."""
    model_config = ConfigDict(frozen=True)
    repo_full_name: str
    tone_and_voice: str
    heading_conventions: list[str]
    code_block_rules: list[str]
    formatting_patterns: list[str]
    skill_markdown: str          # Complete --- frontmatter SKILL.md block
    generated_at: datetime

class MemoryNode(BaseModel):
    model_config = ConfigDict(frozen=True)
    node_id: str                 # "module:src/ingest" | "file:src/x.py"
                                 # "symbol:src/x.py::foo" | "doc:README.md#Quickstart"
    repo_full_name: str
    node_type: str               # "module" | "file" | "symbol" | "doc_section"
    name: str
    path: str
    summary: str
    metadata_json: str = "{}"

class MemoryEdge(BaseModel):
    model_config = ConfigDict(frozen=True)
    repo_full_name: str
    source_id: str
    target_id: str
    relation: str                # "CONTAINS" | "IMPORTS" | "DEFINES" | "DOCUMENTED_IN"

class RepoMemoryMap(BaseModel):
    model_config = ConfigDict(frozen=True)
    repo_full_name: str
    nodes: list[MemoryNode]
    edges: list[MemoryEdge]
    updated_at: datetime

class OnboardRepoResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    repo_full_name: str
    style_skill: DocStyleSkill
    memory_node_count: int
    memory_edge_count: int
    initial_code_doc_edges: int
```

## 4. Shared Protocols (`src/contracts/protocols.py`)

```python
class ContextStoreProtocol(Protocol):
    async def check_and_record_delivery(self, delivery_id: str, repo_full_name: str) -> bool: ...
    async def get_edges_for_symbols(
        self, repo_full_name: str, symbol_names: list[str]
    ) -> list[CodeDocEdge]: ...

    # Stage 0
    async def save_style_skill(self, skill: DocStyleSkill) -> None: ...
    async def get_style_skill(self, repo_full_name: str) -> DocStyleSkill | None: ...
    async def save_memory_map(self, memory_map: RepoMemoryMap) -> None: ...
    async def get_memory_subgraph(
        self,
        repo_full_name: str,
        seed_symbols: list[str],
        max_hops: int = 2,
    ) -> RepoMemoryMap: ...

class OnboardingServiceProtocol(Protocol):
    async def onboard_repository(
        self,
        repo_full_name: str,
        code_files: dict[str, str],
        docs: dict[str, str],
    ) -> OnboardRepoResult: ...
```

## 5. Stage 0 Handoff Rules

1. `POST /api/v1/repos/onboard` accepts inline `code_files`/`docs`, or only
   `repo_full_name` + `branch` so the router fetches a GitHub snapshot.
2. `OnboardingService.onboard_repository()` must persist the style skill, the memory
   map, and the initial `CodeDocEdge` records in one pass.
3. `OrchestratorService` loads `get_style_skill(repo)` and
   `get_memory_subgraph(repo, changed_symbol_names, max_hops=2)` before invoking the graph.
   Missing Stage 0 state must degrade gracefully, never fail a run.
4. `Planner` receives the memory summary; `Writer` and `Reviewer` receive
   `skill_markdown`; `Publisher` updates touched `symbol` and `doc_section` memory
   nodes after a successful PR.
5. Stage 0 is deterministic by default. An injected `LLMClientProtocol` may refine
   only the compiled skill text, and must fall back to the deterministic version on error.

## 6. Running & Testing

```bash
cd docsync-agent
uv sync
uv run uvicorn src.main:app --reload
uv run pytest -q
uv run ruff check src tests
```
