"""Orchestrator state — TypedDict for LangGraph StateGraph + plan/draft models."""

from __future__ import annotations

from typing import TypedDict

from pydantic import BaseModel

from src.contracts.schemas import DocStyleSkill, DriftReport, RepoMemoryMap
from src.orchestrator.schemas import EvidenceRow, PublishResult


class SectionEditPlan(BaseModel):
    """A targeted edit plan for one doc section produced by the Planner node."""

    doc_path: str
    heading: str
    target_symbols: list[str]
    instructions: str


class SectionDraft(BaseModel):
    """A rewritten section draft produced by the Writer node."""

    doc_path: str
    heading: str
    updated_markdown: str
    evidence: list[EvidenceRow]


class OrchestratorState(TypedDict, total=False):
    """State carried through the LangGraph pipeline.

    Fields are intentionally ``total=False`` so partial updates from nibble
    nodes work correctly.
    """

    # ── Input ──────────────────────────────────────────────────────────
    drift_report: DriftReport
    full_docs: dict[str, str]  # doc_path -> full_markdown
    doc_style_skill: DocStyleSkill | None
    memory_subgraph: RepoMemoryMap | None

    # ── Planner output ─────────────────────────────────────────────────
    edit_plans: list[SectionEditPlan]

    # ── Writer output ──────────────────────────────────────────────────
    drafts: list[SectionDraft]
    updated_docs: dict[str, str]

    # ── Verifier output ────────────────────────────────────────────────
    verification_errors: list[str]

    # ── Reviewer output ────────────────────────────────────────────────
    review_approved: bool
    review_feedback: str

    # ── Retry control ──────────────────────────────────────────────────
    retry_count: int
    max_retries: int

    # ── Publisher output ───────────────────────────────────────────────
    publish_result: PublishResult | None