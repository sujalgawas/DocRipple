---
name: docsync-multi-agent-rules
description: Ground rules, module ownership boundaries, interface contracts, and handoff protocols for parallel coding agents building the standalone FastAPI + Tree-sitter + LangGraph Self-Updating Documentation Agent.
---

# Self-Updating Documentation Agent — Multi-Agent Ground Rules

## 1. Precedence & Conflict Resolution Rules
1. **Direct task instruction wins**: An explicit instruction in the current prompt overrides every file rule.
2. **Module ownership wins on file edits**: An agent assigned to `src/<module>/` must NEVER create or edit files outside `src/<module>/` and `tests/<module>/`.
3. **Contracts are frozen**: `src/contracts/` is strictly read-only during parallel module work. If a schema change is required, stop and escalate.
4. **Safety and determinism are non-overridable**: Never commit secrets, never import LLM clients inside `src/analyzer/` or `src/drift/`, and never block the FastAPI async event loop.

## 2. Module Ownership Matrix

| Stage | Module Path | Test Path | LLM Allowed? | Primary Responsibility |
| :--- | :--- | :--- | :--- | :--- |
| **0. Contracts** | `src/contracts/` | `tests/contracts/` | No | Frozen Pydantic v2 schemas (`schemas.py`) and `typing.Protocol` interfaces (`protocols.py`). |
| **1. Ingest** | `src/ingest/` | `tests/ingest/` | No | FastAPI webhook (`POST /api/v1/webhooks/github`), HMAC-SHA256 verification, `X-GitHub-Delivery` dedupe via `ContextStore`, queue push. |
| **2. Analyzer** | `src/analyzer/` | `tests/analyzer/` | **Strictly No** | `unidiff` + `tree-sitter-language-pack` symbol extraction -> `API_SURFACE`, `CLI`, `ENV_CONFIG`, `DEPS`, `BEHAVIOR`. |
| **3. Drift Engine** | `src/drift/` | `tests/drift/` | **Strictly No** | `markdown-it-py` anchor extraction (`changed_symbols ∩ doc_anchors`) + `fastembed` cosine-similarity fallback for unanchored docs. |
| **4. Orchestrator** | `src/orchestrator/` | `tests/orchestrator/` | **Yes (Open Models)** | LangGraph `StateGraph` (`Planner -> Writer -> Verifier -> Reviewer -> Publisher`) + `AsyncSqliteSaver` + GitHub PR publisher with Evidence Table. |
| **5. ContextStore** | `src/context_store/` | `tests/context_store/` | No | `SqliteContextStore` (`aiosqlite` in WAL mode) storing `code_doc_edges`, `webhook_deliveries`, `doc_embeddings`, and `run_traces`. |

## 3. Shared Data Contracts (`src/contracts/schemas.py`)

All cross-module calls must accept and return only these models:

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
    anchor_type: str  # "explicit_comment" | "inline_code" | "embedding"

class ImpactedDocSection(BaseModel):
    model_config = ConfigDict(frozen=True)
    doc_path: str
    heading: str
    start_line: int
    end_line: int
    matched_symbols: list[str]
    match_method: str  # "exact_anchor" | "graph_edge" | "embedding_fallback"
    confidence: float = Field(ge=0.0, le=1.0)
    current_markdown: str

class DriftReport(BaseModel):
    model_config = ConfigDict(frozen=True)
    change_report: ChangeReport
    impacted_sections: list[ImpactedDocSection]

class EvidenceRow(BaseModel):
    model_config = ConfigDict(frozen=True)
    doc_path: str
    section_heading: str
    trigger_symbol: str
    change_class: ChangeClass
    match_method: str
    verification_status: str  # "verified" | "repaired"

class PublishResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    pr_url: str
    pr_number: int
    branch_name: str
    evidence_table_md: str
    completed_at: datetime