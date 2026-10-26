"""LangGraph StateGraph wiring + OrchestratorService entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, AsyncIterator

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.graph import END, StateGraph

from src.orchestrator.state import OrchestratorState

if TYPE_CHECKING:
    from src.orchestrator.github_client import GitHubPublisherProtocol
    from src.orchestrator.llm_client import LLMClientProtocol
    from src.orchestrator.schemas import OrchestratorContextStoreProtocol

logger = logging.getLogger(__name__)


def _should_retry(state: OrchestratorState) -> str:
    """Conditional edge: retry writer on rejection, otherwise publish."""
    review_approved: bool = state.get("review_approved", False)
    retry_count: int = state.get("retry_count", 0)
    max_retries: int = state.get("max_retries", 2)

    if review_approved:
        return "publisher"
    if retry_count >= max_retries:
        logger.info("Max retries reached — routing to publisher")
        return "publisher"
    logger.info("Rejected — looping back to writer (attempt %d/%d)", retry_count + 1, max_retries)
    return "writer"


def build_graph(
    llm_client: LLMClientProtocol,
    github_publisher: GitHubPublisherProtocol,
    context_store: OrchestratorContextStoreProtocol,
) -> StateGraph:
    """Construct the fully wired orchestrator StateGraph (uncompiled)."""
    from src.orchestrator.nodes.planner import build_planner_node
    from src.orchestrator.nodes.writer import build_writer_node
    from src.orchestrator.nodes.verifier import build_verifier_node
    from src.orchestrator.nodes.reviewer import build_reviewer_node
    from src.orchestrator.nodes.publisher import build_publisher_node

    workflow = StateGraph(OrchestratorState)

    workflow.add_node("planner", build_planner_node(llm_client))
    workflow.add_node("writer", build_writer_node(llm_client))
    workflow.add_node("verifier", build_verifier_node())
    workflow.add_node("reviewer", build_reviewer_node(llm_client))
    workflow.add_node("publisher", build_publisher_node(github_publisher, context_store))

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "writer")
    workflow.add_edge("writer", "verifier")
    workflow.add_edge("verifier", "reviewer")

    workflow.add_conditional_edges(
        "reviewer",
        _should_retry,
        {"writer": "writer", "publisher": "publisher"},
    )

    workflow.add_edge("publisher", END)

    return workflow


@asynccontextmanager
async def _checkpointer(db_path: str) -> AsyncIterator:
    """Yield a checkpoint saver matching ``db_path``.

    ``:memory:`` → ``InMemorySaver`` (no connection lifecycle to manage).
    Otherwise → ``AsyncSqliteSaver`` held open by ``async with``.
    """
    if db_path == ":memory:":
        yield InMemorySaver()
        return

    async with AsyncSqliteSaver.from_conn_string(db_path) as saver:
        yield saver