"""Orchestrator-local schemas and protocols."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


# ── Evidence & Publish ────────────────────────────────────────────────────


class EvidenceRow(BaseModel):
    """A single row in the evidence table — maps a symbol to its doc update."""

    doc_file: str
    section: str
    changed_symbol: str
    change_class: str
    match_method: str
    verification: str  # "passed" | "repaired" | "failed"


class PublishResult(BaseModel):
    """Result of the PR publishing step."""

    delivery_id: str
    pr_url: str | None = None
    pr_number: int | None = None
    evidence_table_md: str = ""
    verification_status: str = "passed"  # "passed" | "repaired" | "failed"
    files_updated: list[str] = Field(default_factory=list)
    error: str | None = None


# ── Protocols ─────────────────────────────────────────────────────────────


class OrchestratorProtocol(Protocol):
    """Entry point for running the full LangGraph pipeline."""

    async def run(
        self,
        drift_report: "src.contracts.schemas.DriftReport",  # noqa: F821
        full_docs: dict[str, str],
    ) -> PublishResult: ...


class OrchestratorContextStoreProtocol(Protocol):
    """Extended store interface needed by the orchestrator.

    Must be provided by the context_store module.
    """

    async def save_edges(self, edges: list["src.contracts.schemas.CodeDocEdge"]) -> None: ...  # noqa: F821

    async def save_publish_result(self, result: PublishResult) -> None: ...

    # Inherited from ContextStoreProtocol (no-op shim so tests can implement minimal subset)
    async def check_and_record_delivery(self, delivery_id: str, repo_full_name: str) -> bool: ...

    async def get_edges_for_symbols(
        self, repo_full_name: str, symbol_names: list[str]
    ) -> list["src.contracts.schemas.CodeDocEdge"]: ...  # noqa: F821