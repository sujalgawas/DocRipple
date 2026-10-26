"""GitHub REST service tests using an in-process MockTransport."""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from src.config import settings
from src.web_api.github_service import GitHubService


def json_response(payload: dict, status_code: int = 200) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


@pytest.mark.asyncio
async def test_user_repos_and_snapshot_fetching():
    requested_contents: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/user":
            return json_response(
                {
                    "login": "octocat",
                    "avatar_url": "https://avatars.example/octocat.png",
                    "public_repos": 3,
                    "total_private_repos": 2,
                }
            )
        if path == "/user/repos":
            assert request.url.params["sort"] == "updated"
            assert request.url.params["per_page"] == "30"
            return json_response(
                [
                    {
                        "full_name": "octo/docs",
                        "name": "docs",
                        "owner": {"login": "octo"},
                        "private": False,
                        "default_branch": "main",
                        "language": "Python",
                        "updated_at": "2026-01-01T00:00:00Z",
                    }
                ]
            )
        if path == "/repos/octo/docs/git/trees/main":
            return json_response(
                {
                    "tree": [
                        {"type": "blob", "path": "src/app.py"},
                        {"type": "blob", "path": "src/util.ts"},
                        {"type": "blob", "path": "README.md"},
                        {"type": "blob", "path": "docs/guide/start.md"},
                        {"type": "blob", "path": "docs/guide/setup.mdx"},
                        {"type": "blob", "path": "docs/assets/logo.png"},
                        {"type": "blob", "path": "Makefile"},
                        {"type": "tree", "path": "src"},
                    ]
                }
            )
        if "/contents/" in path:
            file_path = path.split("/contents/", 1)[1]
            requested_contents.append((file_path, request.url.params["ref"]))
            return httpx.Response(200, text=f"content of {file_path}")
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GitHubService(token="test-token", client=client)

        user = await service.get_authenticated_user()
        assert user == {
            "login": "octocat",
            "avatar_url": "https://avatars.example/octocat.png",
            "repo_count": 5,
        }

        repos = await service.list_user_repos()
        assert repos[0]["full_name"] == "octo/docs"
        assert repos[0]["owner_login"] == "octo"

        code_files, docs = await service.fetch_repo_snapshot(
            "octo/docs", "main", ["README.md", "docs/**/*.md"]
        )

    assert set(code_files) == {"src/app.py", "src/util.ts"}
    assert set(docs) == {"README.md", "docs/guide/start.md"}
    assert ("src/app.py", "main") in requested_contents
    assert ("docs/guide/start.md", "main") in requested_contents


@pytest.mark.asyncio
async def test_oauth_exchange_sends_redirect_uri(monkeypatch):
    captured: dict[str, str] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content.decode()
        return json_response({"access_token": "gho_test_token"})

    monkeypatch.setattr(settings, "GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setattr(settings, "GITHUB_CLIENT_SECRET", "client-secret")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GitHubService(token="", client=client)
        token = await service.exchange_oauth_code(
            "code-123",
            "http://localhost:8000/api/v1/auth/github/callback",
        )

    assert token == "gho_test_token"
    form = parse_qs(captured["body"])
    assert form["client_id"] == ["client-id"]
    assert form["client_secret"] == ["client-secret"]
    assert form["code"] == ["code-123"]
    assert form["redirect_uri"] == [
        "http://localhost:8000/api/v1/auth/github/callback"
    ]


@pytest.mark.asyncio
async def test_webhook_install_only_for_public_https():
    calls: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return json_response({"id": 99}, status_code=201)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GitHubService(token="token", client=client)

        hook_id = await service.install_repo_webhook(
            "octo/docs", "https://example.com/api/v1/webhooks/github", "secret"
        )
        assert hook_id == 99
        assert len(calls) == 1
        payload = json.loads(calls[0].content)
        assert payload["events"] == ["push", "pull_request"]
        assert payload["config"]["secret"] == "secret"

        assert (
            await service.install_repo_webhook(
                "octo/docs", "http://example.com/hook", "secret"
            )
            is None
        )
        assert (
            await service.install_repo_webhook(
                "octo/docs", "https://localhost/hook", "secret"
            )
            is None
        )
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_commit_comparison_returns_diff_metadata_and_blobs():
    raw_diff = "diff --git a/src/app.py b/src/app.py\n+print('new')\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/compare/" in path:
            accept = request.headers.get("accept", "")
            if "diff" in accept:
                return httpx.Response(200, text=raw_diff)
            return json_response(
                {
                    "commits": [
                        {
                            "sha": "headsha",
                            "commit": {
                                "message": "feat: change app",
                                "author": {"name": "Octo Cat"},
                            },
                            "author": {"login": "octocat"},
                        }
                    ],
                    "files": [
                        {
                            "filename": "src/app.py",
                            "status": "modified",
                        }
                    ],
                }
            )
        if "/contents/src/app.py" in path:
            ref = request.url.params["ref"]
            return httpx.Response(200, text=f"content at {ref}")
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GitHubService(token="token", client=client)
        comparison = await service.fetch_commit_comparison(
            "octo/docs", "basesha", "headsha"
        )

    assert comparison["raw_diff"] == raw_diff
    assert comparison["commit_message"] == "feat: change app"
    assert comparison["author_login"] == "octocat"
    assert comparison["file_blobs"]["src/app.py"] == (
        "content at basesha",
        "content at headsha",
    )


@pytest.mark.asyncio
async def test_initial_push_uses_commit_endpoint():
    raw_diff = "diff --git a/README.md b/README.md\n+hello\n"

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/octo/docs/commits/headsha":
            if "diff" in request.headers.get("accept", ""):
                return httpx.Response(200, text=raw_diff)
            return json_response(
                {
                    "sha": "headsha",
                    "commit": {
                        "message": "initial commit",
                        "author": {"name": "Octo Cat"},
                    },
                    "author": {"login": "octocat"},
                    "files": [{"filename": "README.md", "status": "added"}],
                }
            )
        if path == "/repos/octo/docs/contents/README.md":
            return httpx.Response(200, text="# Hello")
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GitHubService(token="token", client=client)
        comparison = await service.fetch_commit_comparison(
            "octo/docs", "0" * 40, "headsha"
        )

    assert comparison["raw_diff"] == raw_diff
    assert comparison["commit_message"] == "initial commit"
    assert comparison["file_blobs"]["README.md"] == (None, "# Hello")


@pytest.mark.asyncio
async def test_open_documentation_pr_creates_branch_and_commits():
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/repos/octo/docs/git/refs":
            # Simulate an already existing branch.
            return json_response({"message": "Reference already exists"}, 422)
        if path == "/repos/octo/docs/contents/README.md" and request.method == "GET":
            return httpx.Response(404, json={"message": "not found"})
        if path == "/repos/octo/docs/contents/README.md" and request.method == "PUT":
            return json_response({"content": {"sha": "newblob"}}, 200)
        if path == "/repos/octo/docs/pulls":
            return json_response(
                {
                    "html_url": "https://github.com/octo/docs/pull/7",
                    "number": 7,
                },
                status_code=201,
            )
        return httpx.Response(404, json={"message": "not found"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GitHubService(token="token", client=client)
        pr_url, pr_number = await service.open_documentation_pr(
            repo_full_name="octo/docs",
            base_branch="develop",
            head_sha="abcdef123456",
            updated_docs={"README.md": "# Updated\n"},
            pr_title="docs: sync",
            pr_body="evidence",
        )

    assert (pr_url, pr_number) == ("https://github.com/octo/docs/pull/7", 7)

    ref_payload = json.loads(requests[0].content)
    assert ref_payload["ref"] == "refs/heads/docripple/sync-abcdef1"
    assert ref_payload["sha"] == "abcdef123456"

    put_payload = json.loads(
        next(
            request.content
            for request in requests
            if request.method == "PUT"
            and request.url.path.endswith("/contents/README.md")
        )
    )
    assert base64.b64decode(put_payload["content"]).decode() == "# Updated\n"
    assert put_payload["branch"] == "docripple/sync-abcdef1"

    pr_payload = json.loads(
        next(
            request.content
            for request in requests
            if request.url.path == "/repos/octo/docs/pulls"
        )
    )
    assert pr_payload["head"] == "docripple/sync-abcdef1"
    assert pr_payload["base"] == "develop"
