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
    # When true, the newest commit on the branch is analyzed right away instead
    # of being treated as the polling baseline.
    analyze_latest: bool = False


class RepoRestoreItem(BaseModel):
    """A repository config cached in the browser's localStorage."""

    model_config = ConfigDict(extra="ignore")

    repo_full_name: str
    watch_branch: str = "main"
    doc_paths: list[str] = Field(
        default_factory=lambda: ["README.md", "docs/**/*.md"]
    )
    drift_action: str = "open_pr"
    status: str = "listening"
    last_processed_sha: str | None = None
    language: str | None = None


class RestoreReposRequest(BaseModel):
    """Repositories to re-insert after a serverless cold start wiped SQLite."""

    model_config = ConfigDict(extra="ignore")

    repos: list[RepoRestoreItem] = Field(default_factory=list)


class PollRepoItem(BaseModel):
    """A listening repository the browser wants polled for new commits."""

    model_config = ConfigDict(extra="ignore")

    repo_full_name: str
    watch_branch: str = "main"
    last_processed_sha: str | None = None
    status: str = "listening"


class PollReposRequest(BaseModel):
    """Poll request; an empty list means poll every listened repo in SQLite."""

    model_config = ConfigDict(extra="ignore")

    repos: list[PollRepoItem] = Field(default_factory=list)


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

