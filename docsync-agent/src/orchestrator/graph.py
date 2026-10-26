"""LangGraph StateGraph wiring with AsyncSqliteSaver persistence."""

import logging

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from src.orchestrator.state import OrchestratorState
from src.orchestrator.nodes.planner import planner_node
from src.orchestrator.nodes.writer import writer_node
from src.orchestrator.nodes.verifier import verifier_node
from src.orchestrator.nodes.reviewer import reviewer_node
from src.orchestrator.nodes.publisher import publisher_node

logger = logging.getLogger(__name__)


def _should_retry(state: OrchestratorState) -> str:
    """Conditional edge: loop back to writer if reviewer requests revision."""
    if state.error:
        return "end"
    if not state.review_approved and state.retry_count < state.max_retries:
        logger.info("Retrying writer (attempt %d/%d)", state.retry_count + 1, state.max_retries)
        return "writer"
    return "publisher"


def build_graph() -> StateGraph:
    """Construct the orchestrator state machine."""
    workflow = StateGraph(OrchestratorState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("verifier", verifier_node)
    workflow.add_node("reviewer", reviewer_node)
    workflow.add_node("publisher", publisher_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "writer")
    workflow.add_edge("writer", "verifier")
    workflow.add_edge("verifier", "reviewer")

    workflow.add_conditional_edges(
        "reviewer",
        _should_retry,
        {"writer": "writer", "publisher": "publisher", "end": END},
    )

    workflow.add_edge("publisher", END)

    return workflow


async def create_graph_with_checkpointer(db_path: str = "checkpoints.db"):
    """Return a compiled graph with AsyncSqliteSaver checkpointer."""
    conn: AsyncSqliteSaver | None = None
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        conn = AsyncSqliteSaver.from_conn_string(db_path)
        graph = build_graph().compile(checkpointer=conn)
        return graph
    except Exception as exc:
        if conn:
            await conn.close()
        raise exc