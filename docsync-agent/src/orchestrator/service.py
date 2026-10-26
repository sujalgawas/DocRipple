"""OrchestratorService — top-level runner for the LangGraph pipeline."""

from __future__ import annotations

import logging

from src.contracts.schemas import DriftReport
from src.orchestrator.config import OrchestratorConfig
from src.orchestrator.github_client import HttpGitHubPublisher
from src.orchestrator.graph import _checkpointer, build_graph
from src.orchestrator.llm_client import OpenAICompatibleLLMClient
from src.orchestrator.schemas import (
    OrchestratorContextStoreProtocol,
    PublishResult,
)

logger = logging.getLogger(__name__)


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

        self._llm_client = llm_client or OpenAICompatibleLLMClient(
            base_url=self._config.llm_base_url,
            api_key=self._config.llm_api_key,
            model=self._config.llm_model,
        )

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

        initial: dict = {
            "drift_report": drift_report,
            "full_docs": full_docs,
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

        async with _checkpointer(self._config.checkpoint_db_path) as saver:
            compiled = graph.compile(checkpointer=saver)
            final = await compiled.ainvoke(initial, config)

        result: PublishResult | None = final.get("publish_result")
        if result is not None:
            return result

        return PublishResult(
            delivery_id=delivery_id,
            verification_status="failed",
            error="Pipeline did not produce a publish result",
        )