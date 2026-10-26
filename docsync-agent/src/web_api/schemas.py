"""Request schemas for the frontend-facing web API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ConnectRepoRequest(BaseModel):
    """Step 2 of the Add Repository wizard."""

    model_config = ConfigDict(extra="ignore")

    repo_full_name: str
    watch_branch: str = "main"
    doc_paths: list[str] = Field(
        default_factory=lambda: ["README.md", "docs/**/*.md"]
    )
    drift_action: str = "open_pr"


class TriggerRequest(BaseModel):
    """Optional commit selection for a manual pipeline run."""

    model_config = ConfigDict(extra="ignore")

    commit_sha: str | None = None
    force: bool = False
    check_duplicate: bool = False


class SettingsPatch(BaseModel):
    """Partial update for the singleton user settings row."""

    model_config = ConfigDict(extra="ignore")

    require_reviewer_approval: bool | None = None
    skip_internal_changes: bool | None = None
    email_on_failed_runs: bool | None = None


class TokenAuthRequest(BaseModel):
    """Personal Access Token submission."""

    model_config = ConfigDict(extra="ignore")

    token: str


class OAuthConfigRequest(BaseModel):
    """GitHub OAuth App credentials."""

    model_config = ConfigDict(extra="ignore")

    client_id: str
    client_secret: str

