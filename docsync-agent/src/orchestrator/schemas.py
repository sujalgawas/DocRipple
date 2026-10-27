"""Orchestrator-local schemas and protocols."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from src.contracts.schemas import (
    CodeDocEdge,
    DocStyleSkill,
    MemoryNode,
    PublishResult,
    RepoMemoryMap,
)

# ── Evidence & Publish ────────────────────────────────────────────────────


class EvidenceRow(BaseModel):
    """A single row in the evidence table — maps a symbol to its doc update."""

    doc_file: str
    section: str
    changed_symbol: str
    change_class: str
    match_method: str
    verification: str  # "passed" | "repaired" | "failed"


# ── Protocols ─────────────────────────────────────────────────────────────


class OrchestratorContextStoreProtocol(Protocol):
    """Extended store interface needed by the orchestrator.

    Must be provided by the context_store module.
    """

    async def save_edges(self, edges: list[CodeDocEdge]) -> None: ...

    async def save_publish_result(self, result: PublishResult) -> None: ...

    # Inherited from ContextStoreProtocol (no-op shim so tests can implement minimal subset)
    async def check_and_record_delivery(self, delivery_id: str, repo_full_name: str) -> bool: ...

    async def get_edges_for_symbols(
        self, repo_full_name: str, symbol_names: list[str]
    ) -> list[CodeDocEdge]: ...

    # Stage 0 context (optional for older stores; the service degrades gracefully)
    async def get_style_skill(self, repo_full_name: str) -> DocStyleSkill | None: ...

    async def get_memory_subgraph(
        self,
        repo_full_name: str,
        seed_symbols: list[str],
        max_hops: int = 2,
    ) -> RepoMemoryMap: ...

    async def upsert_memory_nodes(self, nodes: list[MemoryNode]) -> None: ...
