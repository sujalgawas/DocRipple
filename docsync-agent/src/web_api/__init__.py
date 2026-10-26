"""Frontend-facing web API bridge and GitHub service."""

from src.web_api.github_service import GitHubService, GitHubServicePublisher

__all__ = ["GitHubService", "GitHubServicePublisher"]
