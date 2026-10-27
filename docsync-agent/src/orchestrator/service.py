"""OrchestratorService — top-level runner for the LangGraph pipeline."""

from __future__ import annotations

import logging

from pydantic import BaseModel

from src.context_store.sqlite_store import _resolve_writable_db_path
from src.contracts.schemas import DocStyleSkill, DriftReport, RepoMemoryMap
from src.orchestrator.config import OrchestratorConfig
from src.orchestrator.github_client import HttpGitHubPublisher
from src.orchestrator.graph import _checkpointer, build_graph
from src.orchestrator.llm_client import OpenAICompatibleLLMClient
from src.orchestrator.schemas import (
    OrchestratorContextStoreProtocol,
    PublishResult,
)

logger = logging.getLogger(__name__)


class _CountingLLMClient:
    """Delegate to an LLM client while counting every completion request."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.calls = 0

    def reset(self) -> None:
        self.calls = 0

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
    ) -> BaseModel:
        self.calls += 1
        return await self._inner.generate_json(  # type: ignore[attr-defined]
            system_prompt, user_prompt, response_schema
        )

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        self.calls += 1
        return await self._inner.generate_text(  # type: ignore[attr-defined]
            system_prompt, user_prompt
        )


class OrchestratorService:
    """Top-level orchestrator implementing ``OrchestratorProtocol``.

    Wires the LangGraph StateGraph, compiles it with a checkpointer,
    and provides a clean ``run()`` entry point.
    """

    def __init__(
        self,
        llm_client: object | None = None,
        github_publisher: object | None = None,
        context_store: OrchestratorContextStoreProtocol | None = None,
        config: OrchestratorConfig | None = None,
    ) -> None:
        self._config = config or OrchestratorConfig()
        if self._config.checkpoint_db_path:
            self._config.checkpoint_db_path = _resolve_writable_db_path(
                self._config.checkpoint_db_path
            )

        inner_llm = llm_client or OpenAICompatibleLLMClient(
            base_url=self._config.llm_base_url,
            api_key=self._config.llm_api_key,
            model=self._config.llm_model,
            fallback_base_url=self._config.fallback_llm_base_url,
            fallback_api_key=self._config.fallback_llm_api_key,
            fallback_model=self._config.fallback_llm_model,
        )
        self._llm_client = _CountingLLMClient(inner_llm)
        self.last_llm_calls = 0

        self._github_publisher = github_publisher or HttpGitHubPublisher(
            token=self._config.github_token,
        )

        # ContextStore is required — must be injected in production
        if context_store is None:
            raise ValueError("context_store is required for OrchestratorService")
        self._context_store = context_store

    async def run(
        self,
        drift_report: DriftReport,
        full_docs: dict[str, str],
    ) -> PublishResult:
        """Execute the full planner→writer→verifier→reviewer→publisher pipeline."""

        delivery_id = drift_report.change_report.delivery_id

        graph = build_graph(
            llm_client=self._llm_client,  # type: ignore[arg-type]
            github_publisher=self._github_publisher,  # type: ignore[arg-type]
            context_store=self._context_store,
        )

        config = {"configurable": {"thread_id": delivery_id}}
        repo_full_name = drift_report.change_report.repo_full_name
        seed_symbols = [
            symbol.symbol_name for symbol in drift_report.change_report.changed_symbols
        ]
        doc_style_skill = await self._load_style_skill(repo_full_name)
        memory_subgraph = await self._load_memory_subgraph(repo_full_name, seed_symbols)

        initial: dict = {
            "drift_report": drift_report,
            "full_docs": full_docs,
            "doc_style_skill": doc_style_skill,
            "memory_subgraph": memory_subgraph,
            "edit_plans": [],
            "drafts": [],
            "updated_docs": {},
            "verification_errors": [],
            "review_approved": False,
            "review_feedback": "",
            "retry_count": 0,
            "max_retries": self._config.max_retries,
            "publish_result": None,
        }

        self._llm_client.reset()
        try:
            async with _checkpointer(self._config.checkpoint_db_path) as saver:
                compiled = graph.compile(checkpointer=saver)
                final = await compiled.ainvoke(initial, config)
        finally:
            self.last_llm_calls = self._llm_client.calls

        result: PublishResult | None = final.get("publish_result")
        if result is not None:
            return result

        return PublishResult(
            delivery_id=delivery_id,
            verification_status="failed",
            error="Pipeline did not produce a publish result",
        )

    async def _load_style_skill(self, repo_full_name: str) -> DocStyleSkill | None:
        """Load Stage 0's style skill when the store supports onboarding."""
        loader = getattr(self._context_store, "get_style_skill", None)
        if not callable(loader):
            return None
        try:
            return await loader(repo_full_name)
        except Exception:
            logger.warning(
                "Failed to load DocStyleSkill for %s",
                repo_full_name,
                exc_info=True,
            )
            return None

    async def _load_memory_subgraph(
        self, repo_full_name: str, seed_symbols: list[str]
    ) -> RepoMemoryMap | None:
        """Load the 2-hop memory subgraph around changed symbols."""
        loader = getattr(self._context_store, "get_memory_subgraph", None)
        if not callable(loader):
            return None
        try:
            return await loader(repo_full_name, seed_symbols, max_hops=2)
        except TypeError:
            try:
                return await loader(repo_full_name, seed_symbols)
            except Exception:
                logger.warning(
                    "Failed to load RepoMemoryMap subgraph for %s",
                    repo_full_name,
                    exc_info=True,
                )
                return None
        except Exception:
            logger.warning(
                "Failed to load RepoMemoryMap subgraph for %s",
                repo_full_name,
                exc_info=True,
            )
            return None