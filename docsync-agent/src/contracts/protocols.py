from typing import Protocol
from src.contracts.schemas import (
    ChangeReport,
    CodeDocEdge,
    DriftReport,
    WebhookJob,
)


class ContextStoreProtocol(Protocol):
    async def check_and_record_delivery(self, delivery_id: str, repo_full_name: str) -> bool:
        """Returns True if delivery_id is new and was recorded; False if duplicate."""
        ...

    async def get_edges_for_symbols(
        self, repo_full_name: str, symbol_names: list[str]
    ) -> list[CodeDocEdge]: ...


class AnalyzerProtocol(Protocol):
    async def analyze(
        self,
        job: WebhookJob,
        raw_diff: str,
        file_blobs: dict[str, tuple[str | None, str | None]] | None = None,
    ) -> ChangeReport: ...


class DriftEngineProtocol(Protocol):
    async def compute_drift(
        self,
        change_report: ChangeReport,
        docs: dict[str, str],
        stored_edges: list[CodeDocEdge] | None = None,
    ) -> DriftReport: ...