"""Stage 0 onboarding service — style skill + repository memory map."""

from __future__ import annotations

import logging
from typing import Any

from src.contracts.protocols import ContextStoreProtocol, OnboardingServiceProtocol
from src.contracts.schemas import CodeDocEdge, OnboardRepoResult
from src.onboarding.memory_builder import RepoMemoryMapBuilder
from src.onboarding.style_analyzer import DocStyleSkillGenerator

logger = logging.getLogger(__name__)


class OnboardingService(OnboardingServiceProtocol):
    """Run Stage 0 before a repository starts sending webhook jobs."""

    def __init__(
        self,
        context_store: ContextStoreProtocol,
        style_generator: DocStyleSkillGenerator | None = None,
        memory_builder: RepoMemoryMapBuilder | None = None,
    ) -> None:
        self._context_store = context_store
        self._style_generator = style_generator or DocStyleSkillGenerator()
        self._memory_builder = memory_builder or RepoMemoryMapBuilder()

    async def onboard_repository(
        self,
        repo_full_name: str,
        code_files: dict[str, str],
        docs: dict[str, str],
    ) -> OnboardRepoResult:
        """Generate, persist, and summarize a repository's Stage 0 state."""
        style_skill = await self._style_generator.generate(repo_full_name, docs)
        memory_result = await self._memory_builder.build_with_edges(
            repo_full_name,
            code_files,
            docs,
        )

        await self._context_store.save_style_skill(style_skill)
        await self._context_store.save_memory_map(memory_result.memory_map)

        initial_edges = memory_result.code_doc_edges
        await _persist_initial_edges(self._context_store, initial_edges)

        logger.info(
            "Onboarded %s: %d nodes, %d edges, %d initial code-doc edges",
            repo_full_name,
            len(memory_result.memory_map.nodes),
            len(memory_result.memory_map.edges),
            len(initial_edges),
        )
        return OnboardRepoResult(
            repo_full_name=repo_full_name,
            style_skill=style_skill,
            memory_node_count=len(memory_result.memory_map.nodes),
            memory_edge_count=len(memory_result.memory_map.edges),
            initial_code_doc_edges=len(initial_edges),
        )


async def _persist_initial_edges(
    context_store: ContextStoreProtocol,
    edges: list[CodeDocEdge],
) -> None:
    """Persist initial edges through either supported store method."""
    if not edges:
        return

    for method_name in ("upsert_edges", "save_edges"):
        method: Any = getattr(context_store, method_name, None)
        if callable(method):
            await method(edges)
            return

    logger.warning(
        "Context store exposes no edge-write method; %d initial edges were not persisted",
        len(edges),
    )
