"""Request/response schemas for Stage 0 repository onboarding."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OnboardRequest(BaseModel):
    """Payload for ``POST /api/v1/repos/onboard``.

    Callers may provide the repository snapshot inline, or provide only
    ``repo_full_name`` and ``branch`` so the router fetches it from GitHub.
    """

    model_config = ConfigDict(extra="ignore")

    repo_full_name: str
    branch: str = "main"
    code_files: dict[str, str] = Field(default_factory=dict)
    docs: dict[str, str] = Field(default_factory=dict)
