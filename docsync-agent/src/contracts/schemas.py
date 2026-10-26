"""Shared data models used across module boundaries."""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid4().hex


class ChangeClass(str, Enum):
    API_SURFACE = "api_surface"
    CLI = "cli"
    ENV_CONFIG = "env_config"
    DEPS = "deps"
    BEHAVIOR = "behavior"


# ── Webhook ──────────────────────────────────────────────

class WebhookJob(BaseModel):
    """Verified job enqueued by the ingest layer."""
    job_id: str = Field(default_factory=_new_id)
    delivery_id: str
    repo_full_name: str
    default_branch: str
    head_commit: str
    diff: str
    received_at: datetime = Field(default_factory=datetime.utcnow)


# ── Analyzer output ──────────────────────────────────────

class ChangedSymbol(BaseModel):
    name: str
    kind: str  # function, class, method, route, cli_flag, env_var
    signature: str
    file_path: str
    diff_hunk: str


class ChangeReport(BaseModel):
    job_id: str
    symbols: list[ChangedSymbol] = []
    change_classes: list[ChangeClass] = []
    files_changed: list[str] = []


# ── Drift / ContextStore models ──────────────────────────

class CodeDocEdge(BaseModel):
    symbol_name: str
    doc_path: str
    doc_section: str
    anchor: Optional[str] = None


class EvidenceRow(BaseModel):
    symbol: str
    doc_path: str
    section_before: str
    section_after: str
    status: str  # updated | unchanged | missing


class DriftReport(BaseModel):
    job_id: str
    stale_sections: list[CodeDocEdge] = []
    evidence: list[EvidenceRow] = []


# ── Orchestrator output ──────────────────────────────────

class PublishResult(BaseModel):
    job_id: str
    pr_url: Optional[str] = None
    pr_number: Optional[int] = None
    files_updated: list[str] = []
    error: Optional[str] = None