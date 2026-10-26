"""Orchestrator state definition for the LangGraph state machine."""

from typing import Optional, Annotated
from dataclasses import dataclass, field

from src.contracts.schemas import ChangeReport, DriftReport, PublishResult


@dataclass
class OrchestratorState:
    """State carried through the LangGraph pipeline."""

    # Input
    change_report: Optional[ChangeReport] = None
    drift_report: Optional[DriftReport] = None

    # Planner output
    edit_plan: list[dict] = field(default_factory=list)  # [{doc_path, section, action, instructions}]

    # Writer output
    updated_docs: dict[str, str] = field(default_factory=dict)  # doc_path -> new_content

    # Verifier output
    verification_errors: list[str] = field(default_factory=list)

    # Reviewer output
    review_approved: bool = False
    review_feedback: str = ""
    retry_count: int = 0

    # Publisher output
    publish_result: Optional[PublishResult] = None

    # Control
    max_retries: int = 2
    error: Optional[str] = None