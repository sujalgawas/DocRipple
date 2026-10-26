"""Frontend-facing web API bridge and GitHub service."""

from src.web_api.github_service import GitHubService, GitHubServicePublisher
from src.web_api.router import router as web_api_router

__all__ = ["GitHubService", "GitHubServicePublisher", "web_api_router"]
