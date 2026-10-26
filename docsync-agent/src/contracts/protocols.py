from typing import Protocol

from src.contracts.schemas import (
    ChangeReport,
    CodeDocEdge,
    DocStyleSkill,
    DriftReport,
    OnboardRepoResult,
    PublishResult,
    RepoMemoryMap,
    WebhookJob,
)


class ContextStoreProtocol(Protocol):
    async def check_and_record_delivery(self, delivery_id: str, repo_full_name: str) -> bool:
        """Returns True if delivery_id is new and was recorded; False if duplicate."""
        ...

    async def get_edges_for_symbols(
        self, repo_full_name: str, symbol_names: list[str]
    ) -> list[CodeDocEdge]: ...

    async def save_style_skill(self, skill: DocStyleSkill) -> None:
        """Persist (or replace) the repository's DocStyleSkill."""
        ...

    async def get_style_skill(self, repo_full_name: str) -> DocStyleSkill | None:
        """Load the repository's DocStyleSkill, if Stage 0 has run."""
        ...

    async def save_memory_map(self, memory_map: RepoMemoryMap) -> None:
        """Persist (or replace) the repository's memory nodes and edges."""
        ...

    async def get_memory_subgraph(
        self,
        repo_full_name: str,
        seed_symbols: list[str],
        max_hops: int = 2,
    ) -> RepoMemoryMap:
        """Return the bounded memory subgraph around ``seed_symbols``.

        Traversal follows both incoming and outgoing edges. An empty
        ``seed_symbols`` list returns the repository's complete memory map.
        """
        ...


class OnboardingServiceProtocol(Protocol):
    async def onboard_repository(
        self,
        repo_full_name: str,
        code_files: dict[str, str],
        docs: dict[str, str],
    ) -> OnboardRepoResult: ...


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


class OrchestratorProtocol(Protocol):
    """Entry point for running the full LangGraph pipeline."""

    async def run(
        self,
        drift_report: DriftReport,
        full_docs: dict[str, str],
    ) -> PublishResult: ...