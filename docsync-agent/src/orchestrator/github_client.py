"""GitHub publisher — protocol + httpx implementation."""

from __future__ import annotations

import base64
import logging
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"


class GitHubPublisherProtocol(Protocol):
    """Injectable GitHub backend — swap real HTTP for a fake in tests."""

    async def create_docs_pr(
        self,
        repo_full_name: str,
        base_sha: str,
        branch_name: str,
        updated_docs: dict[str, str],
        pr_title: str,
        pr_body: str,
    ) -> tuple[str, int]:
        """Create a PR with updated docs. Returns ``(pr_url, pr_number)``."""
        ...


class HttpGitHubPublisher:
    """Real GitHub REST API publisher via httpx."""

    def __init__(self, token: str = "dev-github-token") -> None:
        self._token = token

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def create_docs_pr(
        self,
        repo_full_name: str,
        base_sha: str,
        branch_name: str,
        updated_docs: dict[str, str],
        pr_title: str,
        pr_body: str,
    ) -> tuple[str, int]:
        """Create a branch, commit files, and open a PR."""
        async with httpx.AsyncClient(base_url=GITHUB_API_BASE) as client:
            # 1. Create branch ref
            ref_path = f"/repos/{repo_full_name}/git/refs"
            resp = await client.post(
                ref_path,
                headers=self._headers(),
                json={
                    "ref": f"refs/heads/{branch_name}",
                    "sha": base_sha,
                },
            )
            resp.raise_for_status()

            # 2. Commit each updated doc
            for doc_path, content in updated_docs.items():
                file_url = f"/repos/{repo_full_name}/contents/{doc_path}"

                # Get current SHA if file exists
                try:
                    existing = await client.get(
                        file_url,
                        headers=self._headers(),
                        params={"ref": branch_name},
                    )
                    existing.raise_for_status()
                    sha: str | None = existing.json().get("sha")
                except httpx.HTTPStatusError:
                    sha = None

                payload: dict = {
                    "message": f"docs: update {doc_path}",
                    "content": base64.b64encode(content.encode()).decode(),
                    "branch": branch_name,
                }
                if sha:
                    payload["sha"] = sha

                resp = await client.put(
                    file_url,
                    headers=self._headers(),
                    json=payload,
                )
                resp.raise_for_status()

            # 3. Create PR
            pr_resp = await client.post(
                f"/repos/{repo_full_name}/pulls",
                headers=self._headers(),
                json={
                    "title": pr_title,
                    "body": pr_body,
                    "head": branch_name,
                    "base": "main",
                },
            )
            pr_resp.raise_for_status()
            pr_data = pr_resp.json()

            pr_url: str = pr_data.get("html_url", "")
            pr_number: int = pr_data.get("number", 0)
            logger.info("Created PR %s (#%d)", pr_url, pr_number)
            return pr_url, pr_number