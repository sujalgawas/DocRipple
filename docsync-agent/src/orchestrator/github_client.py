"""Async httpx client for GitHub branch creation, commits, and PRs."""

import logging

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def create_branch(
    repo_full_name: str,
    branch_name: str,
    base_sha: str,
) -> dict:
    """Create a new branch from the given base SHA."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}/git/refs",
            headers=_headers(),
            json={"ref": f"refs/heads/{branch_name}", "sha": base_sha},
        )
        resp.raise_for_status()
        return resp.json()


async def commit_file(
    repo_full_name: str,
    branch_name: str,
    path: str,
    content: str,
    message: str,
) -> dict:
    """Create or update a file in a branch."""
    async with httpx.AsyncClient() as client:
        # Get current file SHA if it exists
        try:
            existing = await client.get(
                f"{GITHUB_API_BASE}/repos/{repo_full_name}/contents/{path}",
                headers=_headers(),
                params={"ref": branch_name},
            )
            existing.raise_for_status()
            sha = existing.json().get("sha")
        except httpx.HTTPStatusError:
            sha = None

        import base64

        payload = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch_name,
        }
        if sha:
            payload["sha"] = sha

        resp = await client.put(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}/contents/{path}",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def create_pull_request(
    repo_full_name: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
) -> dict:
    """Open a pull request."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls",
            headers=_headers(),
            json={
                "title": title,
                "body": body,
                "head": head_branch,
                "base": base_branch,
            },
        )
        resp.raise_for_status()
        return resp.json()