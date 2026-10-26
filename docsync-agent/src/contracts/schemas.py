from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ChangeClass(StrEnum):
    API_SURFACE = "api_surface"
    CLI = "cli"
    ENV_CONFIG = "env_config"
    DEPS = "deps"
    BEHAVIOR = "behavior"


class WebhookJob(BaseModel):
    model_config = ConfigDict(frozen=True)
    delivery_id: str
    event_type: str  # "push" | "pull_request"
    repo_full_name: str
    base_sha: str
    head_sha: str
    ref: str
    pr_number: int | None = None
    received_at: datetime


class ChangedSymbol(BaseModel):
    model_config = ConfigDict(frozen=True)
    file_path: str
    symbol_name: str
    symbol_kind: str  # "function" | "class" | "method" | "route" | "cli_flag" | "env_var" | "dependency"
    change_class: ChangeClass
    change_type: str  # "added" | "modified" | "removed"
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
    anchor_type: str  # "explicit_anchor" | "inline_code" | "embedding"


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
    verification_status: str = "passed"  # "passed" | "repaired" | "failed"
    files_updated: list[str] = Field(default_factory=list)
    error: str | None = None


# ── Stage 0: Repository onboarding & memory ───────────────────────────────


class DocStyleSkill(BaseModel):
    """Repository-specific writing and structure rules mined from existing docs.

    ``skill_markdown`` is a complete ``SKILL.md`` block that can be injected
    verbatim into Planner/Writer/Reviewer system prompts.
    """

    model_config = ConfigDict(frozen=True)

    repo_full_name: str
    tone_and_voice: str
    heading_conventions: list[str]
    code_block_rules: list[str]
    formatting_patterns: list[str]
    skill_markdown: str
    generated_at: datetime


class MemoryNode(BaseModel):
    """A node in the repository memory graph."""

    model_config = ConfigDict(frozen=True)

    node_id: str  # e.g. "symbol:src/ingest/router.py::github_webhook"
    repo_full_name: str
    node_type: str  # "module" | "file" | "symbol" | "doc_section"
    name: str
    path: str
    summary: str
    metadata_json: str = "{}"


class MemoryEdge(BaseModel):
    """A directed, typed relationship between two memory nodes."""

    model_config = ConfigDict(frozen=True)

    repo_full_name: str
    source_id: str
    target_id: str
    relation: str  # "CONTAINS" | "IMPORTS" | "DEFINES" | "DOCUMENTED_IN"


class RepoMemoryMap(BaseModel):
    """The complete -- or traversed -- node/edge memory map for a repository."""

    model_config = ConfigDict(frozen=True)

    repo_full_name: str
    nodes: list[MemoryNode]
    edges: list[MemoryEdge]
    updated_at: datetime


class OnboardRepoResult(BaseModel):
    """Summary returned after Stage 0 completes for a repository."""

    model_config = ConfigDict(frozen=True)

    repo_full_name: str
    style_skill: DocStyleSkill
    memory_node_count: int
    memory_edge_count: int
    initial_code_doc_edges: int