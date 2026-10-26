"""Protocols defining module boundaries. Implementations live in their owning modules."""

from typing import Protocol, Optional

from src.contracts.schemas import (
    WebhookJob,
    ChangeReport,
    CodeDocEdge,
    DriftReport,
)


class ContextStoreProtocol(Protocol):
    """Storage contract implemented by src/context_store/service.py."""

    async def record_delivery(self, delivery_id: str) -> bool:
        """Return True if delivery_id is new (not a duplicate)."""
        ...

    async def save_edges(self, edges: list[CodeDocEdge]) -> None:
        ...

    async def get_edges_for_symbol(self, symbol_name: str) -> list[CodeDocEdge]:
        ...

    async def save_run_trace(self, job_id: str, step: str, payload: str) -> None:
        ...


class AnalyzerProtocol(Protocol):
    """Analyzer contract implemented by src/analyzer/service.py."""

    async def analyze_diff(self, job: WebhookJob) -> ChangeReport:
        ...


class DriftEngineProtocol(Protocol):
    """Drift engine contract implemented by src/drift/service.py."""

    async def compute_drift(
        self, report: ChangeReport, doc_anchors: list[CodeDocEdge]
    ) -> DriftReport:
        ...