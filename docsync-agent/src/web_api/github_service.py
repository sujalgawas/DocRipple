"""GitHub REST API operations used by the web API bridge and pipeline.

All calls are authenticated with a bearer token (OAuth session token or the
``GITHUB_TOKEN`` fallback) and use the ``application/vnd.github+json`` media
type. The service is intentionally thin: it normalizes GitHub responses into
dicts that the router and pipeline can consume directly.
"""

from __future__ import annotations

import base64
import fnmatch
import ipaddress
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from urllib.parse import quote, urlparse

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"

_MAX_SOURCE_FILES = 40
_MAX_BLOB_FILES = 20
_SOURCE_EXTENSIONS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".rb",
    ".php",
}

# Set by the pipeline around an orchestrator run so the publisher adapter can
# branch from the pushed commit (rather than the previous merge base).
_current_head_sha: ContextVar[str] = ContextVar("docripple_head_sha", default="")
_current_base_branch: ContextVar[str] = ContextVar(
    "docripple_base_branch", default="main"
)


class GitHubService:
    """Small async wrapper around the GitHub REST API."""

    def __init__(
        self,
        token: str | None = None,
        *,
        base_url: str = GITHUB_API_BASE,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.token = token if token is not None else settings.GITHUB_TOKEN
        self.base_url = base_url.rstrip("/")
        self._client = client

    # ── Plumbing ────────────────────────────────────────────────────────

    def _headers(self, accept: str = "application/vnd.github+json") -> dict[str, str]:
        headers = {
            "Accept": accept,
            "User-Agent": "DocRipple-Agent",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    @asynccontextmanager
    async def _client_ctx(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        async with httpx.AsyncClient(timeout=30.0) as client:
            yield client

    # ── Auth & repositories ─────────────────────────────────────────────

    async def get_authenticated_user(self) -> dict:
        """Return the authenticated GitHub user and a repository count."""
        async with self._client_ctx() as client:
            response = await client.get(
                self._url("/user"), headers=self._headers()
            )
            response.raise_for_status()
            data = response.json()

        return {
            "login": data.get("login", ""),
            "avatar_url": data.get("avatar_url", ""),
            "repo_count": int(data.get("public_repos", 0))
            + int(data.get("total_private_repos", 0)),
        }

    async def list_user_repos(self) -> list[dict]:
        """List the 30 most recently updated repositories for the user."""
        async with self._client_ctx() as client:
            response = await client.get(
                self._url("/user/repos"),
                headers=self._headers(),
                params={"sort": "updated", "per_page": 30},
            )
            response.raise_for_status()
            data = response.json()

        return [
            {
                "full_name": repo.get("full_name", ""),
                "name": repo.get("name", ""),
                "owner_login": (repo.get("owner") or {}).get("login", ""),
                "private": bool(repo.get("private", False)),
                "default_branch": repo.get("default_branch", "main"),
                "language": repo.get("language"),
                "updated_at": repo.get("updated_at"),
            }
            for repo in data
        ]

    async def get_repo(self, repo_full_name: str) -> dict:
        """Return basic repository metadata."""
        async with self._client_ctx() as client:
            response = await client.get(
                self._url(f"/repos/{repo_full_name}"), headers=self._headers()
            )
            response.raise_for_status()
            data = response.json()
        return {
            "full_name": data.get("full_name", repo_full_name),
            "default_branch": data.get("default_branch", "main"),
            "language": data.get("language"),
            "pushed_at": data.get("pushed_at"),
        }

    async def get_latest_commit(self, repo_full_name: str, branch: str) -> dict:
        """Return the newest commit on a branch."""
        async with self._client_ctx() as client:
            response = await client.get(
                self._url(f"/repos/{repo_full_name}/commits"),
                headers=self._headers(),
                params={"sha": branch, "per_page": 1},
            )
            response.raise_for_status()
            commits = response.json()

        if not commits:
            raise ValueError(f"No commits found on {repo_full_name}@{branch}")
        return _commit_summary(commits[0])

    async def get_commit(self, repo_full_name: str, sha: str) -> dict:
        """Return one commit and its first parent SHA."""
        async with self._client_ctx() as client:
            response = await client.get(
                self._url(f"/repos/{repo_full_name}/commits/{sha}"),
                headers=self._headers(),
            )
            response.raise_for_status()
            data = response.json()
        return _commit_summary(data)

    # ── Repository snapshots ────────────────────────────────────────────

    async def fetch_repo_snapshot(
        self,
        repo_full_name: str,
        branch: str,
        doc_globs: list[str],
    ) -> tuple[dict[str, str], dict[str, str]]:
        """Fetch source files (max 40) and Markdown docs at ``branch``."""
        async with self._client_ctx() as client:
            tree_response = await client.get(
                self._url(
                    f"/repos/{repo_full_name}/git/trees/{quote(branch, safe='')}"
                ),
                headers=self._headers(),
                params={"recursive": "1"},
            )
            tree_response.raise_for_status()
            tree = tree_response.json().get("tree", [])

            source_paths: list[str] = []
            doc_paths: list[str] = []
            for item in tree:
                if item.get("type") != "blob":
                    continue
                path = item.get("path", "")
                if not path:
                    continue
                if _is_documentation_path(path, doc_globs):
                    doc_paths.append(path)
                elif _is_source_path(path):
                    source_paths.append(path)

            source_paths = sorted(set(source_paths))[:_MAX_SOURCE_FILES]
            doc_paths = sorted(set(doc_paths))

            code_files: dict[str, str] = {}
            docs: dict[str, str] = {}
            for path in source_paths:
                content = await _fetch_raw_content(
                    client, self._url, self._headers, repo_full_name, path, branch
                )
                if content is not None:
                    code_files[path] = content

            for path in doc_paths:
                content = await _fetch_raw_content(
                    client, self._url, self._headers, repo_full_name, path, branch
                )
                if content is not None:
                    docs[path] = content

        return code_files, docs

    # ── Webhooks ────────────────────────────────────────────────────────

    async def install_repo_webhook(
        self,
        repo_full_name: str,
        webhook_url: str,
        secret: str,
    ) -> int | None:
        """Install a push/pull_request webhook when the URL is public HTTPS."""
        if not _is_public_https(webhook_url):
            logger.info(
                "Skipping webhook install for %s: %s is not a public HTTPS URL",
                repo_full_name,
                webhook_url or "<empty>",
            )
            return None

        payload = {
            "name": "web",
            "active": True,
            "events": ["push", "pull_request"],
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "secret": secret,
                "insecure_ssl": "0",
            },
        }
        async with self._client_ctx() as client:
            response = await client.post(
                self._url(f"/repos/{repo_full_name}/hooks"),
                headers=self._headers(),
                json=payload,
            )
            if response.status_code == 422:
                logger.info(
                    "Webhook already exists for %s (GitHub returned 422)",
                    repo_full_name,
                )
                return None
            response.raise_for_status()
            return int(response.json().get("id", 0)) or None

    async def delete_repo_webhook(
        self, repo_full_name: str, hook_id: int
    ) -> None:
        """Remove an installed repository webhook (best effort)."""
        async with self._client_ctx() as client:
            response = await client.delete(
                self._url(f"/repos/{repo_full_name}/hooks/{hook_id}"),
                headers=self._headers(),
            )
            if response.status_code not in (204, 404):
                response.raise_for_status()

    # ── Commit comparison ───────────────────────────────────────────────

    async def fetch_commit_comparison(
        self,
        repo_full_name: str,
        base_sha: str,
        head_sha: str,
    ) -> dict:
        """Return diff, commit metadata, and before/after blobs for a push."""
        initial_push = _is_zero_sha(base_sha)

        async with self._client_ctx() as client:
            if initial_push:
                commit_response = await client.get(
                    self._url(f"/repos/{repo_full_name}/commits/{head_sha}"),
                    headers=self._headers(),
                )
                commit_response.raise_for_status()
                compare_data = commit_response.json()
                diff_url = self._url(
                    f"/repos/{repo_full_name}/commits/{head_sha}"
                )
            else:
                compare_url = self._url(
                    f"/repos/{repo_full_name}/compare/{base_sha}...{head_sha}"
                )
                compare_response = await client.get(
                    compare_url, headers=self._headers()
                )
                compare_response.raise_for_status()
                compare_data = compare_response.json()
                diff_url = compare_url

            diff_response = await client.get(
                diff_url,
                headers=self._headers(accept="application/vnd.github.v3.diff"),
            )
            diff_response.raise_for_status()
            raw_diff = diff_response.text

            commit_message, author_login = _comparison_metadata(compare_data)
            files = compare_data.get("files") or []
            file_blobs = await _fetch_changed_blobs(
                client=client,
                url=self._url,
                headers=self._headers,
                repo_full_name=repo_full_name,
                files=files,
                base_sha=base_sha,
                head_sha=head_sha,
                initial_push=initial_push,
            )

        return {
            "raw_diff": raw_diff,
            "commit_message": commit_message,
            "author_login": author_login,
            "file_blobs": file_blobs,
            "files": [item.get("filename", "") for item in files],
        }

    # ── Pull requests ───────────────────────────────────────────────────

    async def open_documentation_pr(
        self,
        repo_full_name: str,
        base_branch: str,
        head_sha: str,
        updated_docs: dict[str, str],
        pr_title: str,
        pr_body: str,
    ) -> tuple[str, int]:
        """Create a branch, commit every doc update, and open a PR."""
        branch = f"docripple/sync-{head_sha[:7]}"

        async with self._client_ctx() as client:
            ref_response = await client.post(
                self._url(f"/repos/{repo_full_name}/git/refs"),
                headers=self._headers(),
                json={
                    "ref": f"refs/heads/{branch}",
                    "sha": head_sha,
                },
            )
            if ref_response.status_code not in (201, 422):
                ref_response.raise_for_status()

            for doc_path, content in updated_docs.items():
                file_url = self._url(
                    f"/repos/{repo_full_name}/contents/{quote(doc_path, safe='/')}"
                )
                existing = await client.get(
                    file_url,
                    headers=self._headers(),
                    params={"ref": branch},
                )
                payload: dict[str, object] = {
                    "message": f"docs: update {doc_path}",
                    "content": base64.b64encode(content.encode("utf-8")).decode(
                        "ascii"
                    ),
                    "branch": branch,
                }
                if existing.status_code == 200:
                    payload["sha"] = existing.json().get("sha")

                put_response = await client.put(
                    file_url,
                    headers=self._headers(),
                    json=payload,
                )
                put_response.raise_for_status()

            pr_response = await client.post(
                self._url(f"/repos/{repo_full_name}/pulls"),
                headers=self._headers(),
                json={
                    "title": pr_title,
                    "body": pr_body,
                    "head": branch,
                    "base": base_branch or "main",
                },
            )
            if pr_response.status_code == 422:
                existing_pr = await _find_open_pr(
                    client, self._url, self._headers, repo_full_name, branch
                )
                if existing_pr is not None:
                    return existing_pr
            pr_response.raise_for_status()
            pr_data = pr_response.json()

        pr_url = pr_data.get("html_url", "")
        pr_number = int(pr_data.get("number", 0))
        logger.info("Opened documentation PR %s (#%d)", pr_url, pr_number)
        return pr_url, pr_number

    # ── OAuth ───────────────────────────────────────────────────────────

    async def exchange_oauth_code(
        self, code: str, redirect_uri: str | None = None
    ) -> str:
        """Exchange a GitHub OAuth code for an access token."""
        payload = {
            "client_id": settings.GITHUB_CLIENT_ID,
            "client_secret": settings.GITHUB_CLIENT_SECRET,
            "code": code,
        }
        if redirect_uri:
            payload["redirect_uri"] = redirect_uri

        async with self._client_ctx() as client:
            response = await client.post(
                GITHUB_OAUTH_TOKEN_URL,
                data=payload,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

        token = data.get("access_token", "")
        if not token:
            raise ValueError(
                f"GitHub OAuth exchange failed: {data.get('error_description') or data}"
            )
        return token


class GitHubServicePublisher:
    """Adapter implementing ``GitHubPublisherProtocol`` via :class:`GitHubService`.

    The pipeline sets ``github_publish_context`` around each orchestrator run so
    the adapter knows which commit to branch from and which branch to target.
    """

    def __init__(self, service: GitHubService) -> None:
        self._service = service

    async def create_docs_pr(
        self,
        repo_full_name: str,
        base_sha: str,
        branch_name: str,
        updated_docs: dict[str, str],
        pr_title: str,
        pr_body: str,
    ) -> tuple[str, int]:
        head_sha = _current_head_sha.get() or base_sha
        base_branch = _current_base_branch.get() or "main"
        logger.info(
            "Publishing docs for %s on %s (branch %s)",
            repo_full_name,
            base_branch,
            branch_name,
        )
        return await self._service.open_documentation_pr(
            repo_full_name=repo_full_name,
            base_branch=base_branch,
            head_sha=head_sha,
            updated_docs=updated_docs,
            pr_title=pr_title,
            pr_body=pr_body,
        )


@contextmanager
def github_publish_context(*, head_sha: str, base_branch: str):
    """Expose the current job's commit/branch to the publisher adapter."""
    head_token = _current_head_sha.set(head_sha)
    branch_token = _current_base_branch.set(base_branch or "main")
    try:
        yield
    finally:
        _current_head_sha.reset(head_token)
        _current_base_branch.reset(branch_token)


# ── Helpers ─────────────────────────────────────────────────────────────


def _is_zero_sha(sha: str) -> bool:
    return not sha or set(sha) == {"0"}


def _is_source_path(path: str) -> bool:
    suffix = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return suffix in _SOURCE_EXTENSIONS


def _is_documentation_path(path: str, doc_globs: list[str]) -> bool:
    lower = path.lower()
    if lower.rsplit("/", 1)[-1] == "readme.md":
        return True
    if lower.startswith("docs/") and lower.endswith(".md"):
        return True
    return any(_matches_glob(path, pattern) for pattern in doc_globs if pattern)


def _matches_glob(path: str, pattern: str) -> bool:
    pattern = pattern.strip()
    if not pattern:
        return False
    if pattern.endswith("/"):
        return path.startswith(pattern)
    candidates = {pattern}
    if pattern.startswith("**/"):
        candidates.add(pattern[3:])
    if "/**/" in pattern:
        candidates.add(pattern.replace("/**/", "/"))
        prefix, suffix = pattern.split("/**/", 1)
        candidates.add(f"{prefix.rstrip('/')}/*{suffix}")
    return any(
        fnmatch.fnmatch(path, candidate)
        or fnmatch.fnmatch(path.lower(), candidate.lower())
        for candidate in candidates
    )


def _is_public_https(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return False

    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "127.0.0.1", "::1"} or hostname.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
    )


def _commit_summary(data: dict) -> dict:
    commit = data.get("commit") or {}
    author = data.get("author") or {}
    git_author = commit.get("author") or {}
    parents = data.get("parents") or []
    return {
        "sha": data.get("sha", ""),
        "message": commit.get("message", ""),
        "author": author.get("login") or git_author.get("name") or "",
        "date": git_author.get("date") or "",
        "parent_sha": parents[0].get("sha", "") if parents else "",
    }


def _comparison_metadata(data: dict) -> tuple[str, str]:
    commits = data.get("commits") or []
    if commits:
        return _commit_summary(commits[-1])["message"], _commit_summary(commits[-1])[
            "author"
        ]

    commit = data.get("commit") or {}
    author = data.get("author") or {}
    return (
        commit.get("message", ""),
        author.get("login") or (commit.get("author") or {}).get("name", ""),
    )


async def _fetch_raw_content(
    client: httpx.AsyncClient,
    url_builder,
    headers_builder,
    repo_full_name: str,
    path: str,
    ref: str,
) -> str | None:
    response = await client.get(
        url_builder(
            f"/repos/{repo_full_name}/contents/{quote(path, safe='/')}"
        ),
        headers=headers_builder(accept="application/vnd.github.raw"),
        params={"ref": ref},
    )
    if response.status_code == 200:
        return response.text
    logger.debug(
        "Skipping %s in %s at %s (HTTP %d)",
        path,
        repo_full_name,
        ref,
        response.status_code,
    )
    return None


async def _fetch_changed_blobs(
    *,
    client: httpx.AsyncClient,
    url,
    headers,
    repo_full_name: str,
    files: list[dict],
    base_sha: str,
    head_sha: str,
    initial_push: bool,
) -> dict[str, tuple[str | None, str | None]]:
    blobs: dict[str, tuple[str | None, str | None]] = {}
    for item in files:
        if len(blobs) >= _MAX_BLOB_FILES:
            break
        path = item.get("filename", "")
        status = item.get("status", "")
        if not path or status not in {"added", "modified", "removed", "renamed"}:
            continue

        before_path = item.get("previous_filename") or path
        before = None
        if not initial_push and status != "added" and base_sha:
            before = await _fetch_raw_content(
                client, url, headers, repo_full_name, before_path, base_sha
            )

        after = None
        if status != "removed":
            after = await _fetch_raw_content(
                client, url, headers, repo_full_name, path, head_sha
            )

        blobs[path] = (before, after)

    return blobs


async def _find_open_pr(
    client: httpx.AsyncClient,
    url,
    headers,
    repo_full_name: str,
    branch: str,
) -> tuple[str, int] | None:
    owner = repo_full_name.split("/", 1)[0]
    response = await client.get(
        url(f"/repos/{repo_full_name}/pulls"),
        headers=headers(),
        params={"state": "open", "head": f"{owner}:{branch}"},
    )
    if response.status_code != 200:
        return None
    pulls = response.json()
    if not pulls:
        return None
    pull = pulls[0]
    return pull.get("html_url", ""), int(pull.get("number", 0))
