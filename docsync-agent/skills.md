---
name: docsync-agent-ground-rules
description: Module ownership, Stage 0 onboarding contracts, and testing rules for the DocRipple FastAPI + Tree-sitter + LangGraph documentation agent.
---

# DocSync Agent — Ground Rules

- Keep each agent module self-contained: one module owns its `src/<module>/` and `tests/<module>/` exclusively.
- Contracts (`src/contracts/`) are **frozen** before parallel runs — read-only for all module agents.
- The Analyzer and Drift engines are **deterministic** — no LLM calls allowed in `src/analyzer/` or `src/drift/`.
- Stage 0 onboarding is deterministic by default — no LLM required to build the style skill or memory map.
- The Orchestrator is the only module that calls an LLM or interacts with GitHub; Stage 0 only fetches a snapshot when asked to onboard from GitHub.
- All async I/O uses `aiosqlite` (WAL mode) through the `ContextStoreProtocol`.
- Maximum retries in the orchestrator state machine: 2.
- Environment variables managed via `pydantic-settings` `BaseSettings` in each module's `config.py`.

## 1. Module Ownership Matrix

| Stage | Module Path | Test Path | LLM Allowed? | Primary Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| **0. Onboarding** | `src/onboarding/` | `tests/onboarding/` | Optional style refinement only | Mine Markdown conventions into a `DocStyleSkill`; build the `RepoMemoryMap`; persist both and pre-populate `code_doc_edges`. |
| **Contracts** | `src/contracts/` | `tests/contracts/` | No | Frozen Pydantic v2 schemas and `typing.Protocol` interfaces. |
| **1. Ingest** | `src/ingest/` | `tests/ingest/` | No | HMAC verification, delivery dedupe, and queue handoff. |
| **2. Analyzer** | `src/analyzer/` | `tests/analyzer/` | **Strictly No** | Diff parsing and AST symbol extraction/classification. |
| **3. Drift Engine** | `src/drift/` | `tests/drift/` | **Strictly No** | Anchor matching, graph-edge lookup, and embedding fallback. |
| **4. Orchestrator** | `src/orchestrator/` | `tests/orchestrator/` | **Yes** | LangGraph `Planner → Writer → Verifier → Reviewer → Publisher` loop consuming the Stage 0 skill and memory subgraph. |
| **5. ContextStore** | `src/context_store/` | `tests/context_store/` | No | SQLite WAL persistence for style skills, memory nodes/edges, code-doc edges, deliveries, embeddings, and run traces. |
| **Pipeline** | `src/pipeline.py` | `tests/integration/` | No | Background worker chaining Stages 1–5 and fetching GitHub diffs/docs. |
| **App** | `src/main.py` | `tests/integration/` | No | Lifespan wiring for the store, Stage 0 service, worker, and routers. |

## 2. Stage 0 Shared Contracts (`src/contracts/schemas.py`)

```python
class DocStyleSkill(BaseModel):
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
    node_id: str                 # module:* | file:* | symbol:* | doc:*
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

## 3. Protocols (`src/contracts/protocols.py`)

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
        self, repo_full_name: str, seed_symbols: list[str], max_hops: int = 2
    ) -> RepoMemoryMap: ...

class OnboardingServiceProtocol(Protocol):
    async def onboard_repository(
        self, repo_full_name: str, code_files: dict[str, str], docs: dict[str, str]
    ) -> OnboardRepoResult: ...
```

## 4. Stage 0 Integration Rules

- `OnboardingService` persists `DocStyleSkill`, `RepoMemoryMap`, and initial `CodeDocEdge` records.
- `OrchestratorService` loads both Stage 0 artifacts before running the graph; missing state degrades gracefully.
- `Planner` consumes the 2-hop memory summary; `Writer` and `Reviewer` consume `skill_markdown`.
- `Publisher` refreshes touched `symbol` and `doc_section` memory nodes after a successful PR.
- Memory traversal follows both incoming and outgoing edges for `max_hops=2`; an empty seed list returns the full map.

## 5. Running

```bash
uv sync
uv run uvicorn src.main:app --reload
```

## 6. Testing

```bash
uv run pytest -q          # 39 tests
uv run ruff check src tests
```
