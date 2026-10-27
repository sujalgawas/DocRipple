"""Frontend-facing web API router.

Only the endpoints used by the React app are implemented here: auth status,
repository discovery/onboarding, dashboard, activity, manual triggers, and
user settings. All state is backed by SQLite and the real GitHub REST API.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from src.config import settings
from src.contracts.schemas import WebhookJob
from src.web_api.github_service import GitHubService
from src.web_api.schemas import (
    ConnectRepoRequest,
    OAuthConfigRequest,
    SettingsPatch,
    TokenAuthRequest,
    TriggerRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["web_api"])

ZERO_SHA = "0" * 40


# ── Dependencies ────────────────────────────────────────────────────────


def _get_store(request: Request):
    store = getattr(request.app.state, "context_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Context store is not configured.",
        )
    return store


def _get_github_service(request: Request) -> GitHubService:
    service: GitHubService | None = getattr(
        request.app.state, "github_service", None
    )
    if service is None:
        service = GitHubService(token=settings.GITHUB_TOKEN)
        request.app.state.github_service = service

    oauth_token = getattr(request.app.state, "github_oauth_token", "")
    service.token = oauth_token or service.token or settings.GITHUB_TOKEN

    # Keep the pipeline's fetcher on the same token (single-user local app).
    pipeline = getattr(request.app.state, "pipeline", None)
    fetcher = getattr(pipeline, "fetcher", None) if pipeline is not None else None
    if fetcher is not None and hasattr(fetcher, "token"):
        fetcher.token = service.token

    return service


def _propagate_github_token(request: Request, token: str) -> None:
    """Keep every long-lived GitHub client on the current runtime token."""
    service = _get_github_service(request)
    service.token = token
    request.app.state.github_oauth_token = token

    pipeline = getattr(request.app.state, "pipeline", None)
    fetcher = getattr(pipeline, "fetcher", None) if pipeline is not None else None
    if fetcher is not None and hasattr(fetcher, "token"):
        fetcher.token = token


def _require_github_token(service: GitHubService) -> None:
    if not service.token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "GitHub is not connected. Set GITHUB_TOKEN in docsync-agent/.env "
                "or sign in with GitHub OAuth."
            ),
        )


def _github_failure(exc: Exception) -> HTTPException:
    logger.warning("GitHub API call failed: %s", exc)
    if isinstance(exc, httpx.HTTPStatusError):
        detail = f"GitHub API returned {exc.response.status_code}"
        try:
            message = exc.response.json().get("message")
            if message:
                detail = f"{detail}: {message}"
        except ValueError:
            pass
        return HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=detail
        )
    return HTTPException(
        status_code=status.HTTP_502_BAD_GATEWAY,
        detail=f"GitHub request failed: {exc}",
    )


# ── Auth ────────────────────────────────────────────────────────────────


@router.get("/auth/me")
async def auth_me(request: Request) -> dict:
    """Return the current GitHub identity, or a disconnected state."""
    service = _get_github_service(request)
    empty = {
        "connected": False,
        "username": None,
        "avatar_url": None,
        "plan": "free",
        "authorized_repos_count": 0,
    }
    if not service.token:
        return empty

    try:
        user = await service.get_authenticated_user()
    except Exception as exc:  # noqa: BLE001 - auth status must never 500
        logger.info("GitHub auth check failed: %s", exc)
        return empty

    try:
        await _get_store(request).update_user_settings(
            github_username=user["login"]
        )
    except Exception:
        logger.debug("Could not persist GitHub username", exc_info=True)

    return {
        "connected": True,
        "username": user["login"],
        "avatar_url": user["avatar_url"],
        "plan": "free",
        "authorized_repos_count": user["repo_count"],
    }


def _update_env_file(updates: dict[str, str]) -> None:
    """Safely update key-value pairs in docsync-agent/.env and root .env."""
    from pathlib import Path

    candidates = [
        Path("docsync-agent/.env"),
        Path(".env"),
        Path(__file__).resolve().parent.parent.parent / ".env",
        Path(__file__).resolve().parent.parent.parent.parent / ".env",
    ]
    seen = set()
    for p in candidates:
        try:
            resolved = p.resolve()
            if resolved in seen or not resolved.is_file():
                continue
            seen.add(resolved)
            lines = resolved.read_text(encoding="utf-8").splitlines()
            updated_keys = set()
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("#") and "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key in updates:
                        new_lines.append(f"{key}={updates[key]}")
                        updated_keys.add(key)
                        continue
                new_lines.append(line)
            for key, val in updates.items():
                if key not in updated_keys:
                    new_lines.append(f"{key}={val}")
            resolved.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception:
            logger.debug("Could not update .env file", exc_info=True)


@router.get("/auth/config")
async def get_auth_config(request: Request) -> dict:
    """Return whether OAuth is configured and the live callback URL."""
    # Derive the callback from the incoming request so deployed environments
    # (Vercel/Render) never advertise a localhost redirect URI.
    try:
        callback_url = str(request.url_for("github_callback"))
    except Exception:  # noqa: BLE001 - config info must never 500
        callback_url = ""

    return {
        "oauth_configured": bool(settings.GITHUB_CLIENT_ID and settings.GITHUB_CLIENT_SECRET),
        "client_id": settings.GITHUB_CLIENT_ID or None,
        "callback_url": callback_url,
    }


@router.post("/auth/token")
async def auth_with_token(payload: TokenAuthRequest, request: Request) -> dict:
    """Authenticate with a GitHub Personal Access Token."""
    token = payload.token.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token cannot be empty.",
        )

    service = GitHubService(token=token)
    try:
        user = await service.get_authenticated_user()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid GitHub token or bad credentials.",
        ) from exc

    _propagate_github_token(request, token)
    settings.GITHUB_TOKEN = token

    await _get_store(request).update_user_settings(
        github_username=user["login"]
    )
    _update_env_file({"GITHUB_TOKEN": token})

    return {
        "connected": True,
        "username": user["login"],
        "avatar_url": user["avatar_url"],
        "plan": "free",
        "authorized_repos_count": user["repo_count"],
    }


@router.post("/auth/oauth-config")
async def save_oauth_config(payload: OAuthConfigRequest) -> dict:
    """Save GitHub OAuth App credentials."""
    client_id = payload.client_id.strip()
    client_secret = payload.client_secret.strip()
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both Client ID and Client Secret are required.",
        )
    settings.GITHUB_CLIENT_ID = client_id
    settings.GITHUB_CLIENT_SECRET = client_secret
    _update_env_file({
        "GITHUB_CLIENT_ID": client_id,
        "GITHUB_CLIENT_SECRET": client_secret,
    })
    return {
        "status": "ok",
        "oauth_configured": True,
        "client_id": client_id,
    }


@router.get("/auth/github/login")
async def github_login(request: Request) -> RedirectResponse:
    """Start OAuth, or fall back to the PAT-backed dashboard."""
    if not settings.GITHUB_CLIENT_ID:
        return RedirectResponse(
            url=f"{settings.FRONTEND_URL}/repositories", status_code=307
        )

    state = uuid4().hex
    request.app.state.oauth_state = state
    redirect_uri = str(request.url_for("github_callback"))
    request.app.state.oauth_redirect_uri = redirect_uri
    query = urlencode(
        {
            "client_id": settings.GITHUB_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "scope": "repo read:user",
            "state": state,
        }
    )
    return RedirectResponse(
        url=f"https://github.com/login/oauth/authorize?{query}",
        status_code=307,
    )


@router.get("/auth/github/callback")
async def github_callback(
    request: Request,
    code: str = Query(default=""),
    state: str = Query(default=""),
) -> RedirectResponse:
    """Complete OAuth and send the user directly to the Add Repository picker."""
    expected_state = getattr(request.app.state, "oauth_state", "")
    if not expected_state or state != expected_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state. Restart the login flow.",
        )
    # State is single-use; consume it before exchanging the code.
    request.app.state.oauth_state = ""
    redirect_uri = getattr(request.app.state, "oauth_redirect_uri", "")
    request.app.state.oauth_redirect_uri = ""
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing OAuth authorization code.",
        )

    service = _get_github_service(request)
    try:
        token = await service.exchange_oauth_code(code, redirect_uri or None)
        _propagate_github_token(request, token)
        settings.GITHUB_TOKEN = token
        user = await service.get_authenticated_user()
        await _get_store(request).update_user_settings(
            github_username=user["login"]
        )
        _update_env_file({"GITHUB_TOKEN": token})
    except Exception as exc:
        logger.exception("GitHub OAuth callback failed")
        raise _github_failure(exc) from exc

    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/repositories/new", status_code=307
    )


# ── Repositories & onboarding ───────────────────────────────────────────


@router.get("/github/repos")
async def github_repos(request: Request) -> list[dict]:
    """Step 1 of the Add Repository wizard."""
    service = _get_github_service(request)
    _require_github_token(service)
    try:
        return await service.list_user_repos()
    except Exception as exc:
        raise _github_failure(exc) from exc


@router.post("/repos/connect")
async def connect_repo(payload: ConnectRepoRequest, request: Request) -> dict:
    """Fetch a snapshot, run Stage 0, install the webhook, and persist."""
    service = _get_github_service(request)
    _require_github_token(service)
    store = _get_store(request)
    onboarding = getattr(request.app.state, "onboarding_service", None)
    if onboarding is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboarding service is not configured.",
        )

    repo_full_name = payload.repo_full_name.strip()
    if "/" not in repo_full_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="repo_full_name must look like 'owner/repo'.",
        )

    doc_paths = [path for path in payload.doc_paths if path.strip()]
    if not doc_paths:
        doc_paths = ["README.md", "docs/**/*.md"]

    try:
        code_files, docs = await service.fetch_repo_snapshot(
            repo_full_name, payload.watch_branch, doc_paths
        )
    except Exception as exc:
        raise _github_failure(exc) from exc

    if not code_files and not docs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No source or documentation files found in {repo_full_name} "
                f"on branch '{payload.watch_branch}'."
            ),
        )

    result = await onboarding.onboard_repository(repo_full_name, code_files, docs)

    webhook_url = settings.PUBLIC_WEBHOOK_URL
    webhook_id: int | None = None
    webhook_error: str | None = None
    if webhook_url:
        try:
            webhook_id = await service.install_repo_webhook(
                repo_full_name, webhook_url, settings.GITHUB_WEBHOOK_SECRET
            )
        except Exception as exc:  # noqa: BLE001 - connection should still succeed
            logger.warning("Webhook install failed for %s: %s", repo_full_name, exc)
            webhook_error = str(exc)

    owner, name = repo_full_name.split("/", 1)
    language: str | None = None
    last_pushed_at: str | None = None
    try:
        repo_meta = await service.get_repo(repo_full_name)
        language = repo_meta.get("language")
        last_pushed_at = repo_meta.get("pushed_at")
    except Exception:  # noqa: BLE001 - metadata is optional
        logger.debug("Could not fetch repo metadata for %s", repo_full_name)

    await store.upsert_monitored_repo(
        repo_full_name=repo_full_name,
        owner=owner,
        name=name,
        watch_branch=payload.watch_branch,
        doc_paths=doc_paths,
        drift_action=_normalize_drift_action(payload.drift_action),
        status="listening",
        language=language,
        webhook_id=webhook_id,
        last_pushed_at=last_pushed_at,
    )

    summary = result.style_skill.tone_and_voice.strip()
    if len(summary) > 280:
        summary = f"{summary[:277]}..."

    response = {
        "status": "connected",
        "repo_full_name": repo_full_name,
        "webhook_url": webhook_url or None,
        "style_skill_summary": summary,
        "memory_nodes_count": result.memory_node_count,
        "memory_edges_count": result.memory_edge_count,
    }
    if webhook_error:
        response["webhook_error"] = webhook_error
    return response


# ── Dashboard ───────────────────────────────────────────────────────────


@router.get("/dashboard")
async def dashboard(request: Request) -> dict:
    """Aggregate counters, monitored repositories, and latest activity."""
    store = _get_store(request)
    repositories = await store.list_monitored_repos()
    run_counts = await store.get_run_counts_by_repo()
    for repository in repositories:
        repository["run_count"] = run_counts.get(
            repository["repo_full_name"], 0
        )

    return {
        "stats": await store.get_activity_stats(),
        "repositories": repositories,
        "latest_runs": await store.list_activity_runs(limit=5),
    }


# ── Activity & trigger ──────────────────────────────────────────────────


@router.get("/activity")
async def activity(
    request: Request,
    repo_full_name: str | None = Query(default=None),
) -> dict:
    """Return every run, newest first."""
    runs = await _get_store(request).list_activity_runs(
        repo_full_name=repo_full_name
    )
    return {"runs": runs}


@router.get("/repos/{owner}/{repo}/history")
async def repo_history(
    owner: str,
    repo: str,
    request: Request,
) -> dict:
    """Return real execution history combining GitHub commits, PRs, and DocRipple pipeline runs."""
    repo_full_name = f"{owner}/{repo}"
    store = _get_store(request)
    service = _get_github_service(request)

    monitored = await store.get_monitored_repo(repo_full_name)
    watch_branch = (monitored or {}).get("watch_branch") or "main"

    commits: list[dict] = []
    pull_requests: list[dict] = []
    if service.token:
        try:
            commits = await service.list_repo_commits(
                repo_full_name, branch=watch_branch, per_page=15
            )
        except Exception as exc:  # noqa: BLE001 - history is best-effort
            logger.warning("Failed to fetch commits for %s: %s", repo_full_name, exc)
        try:
            pull_requests = await service.list_repo_pull_requests(
                repo_full_name, per_page=10
            )
        except Exception as exc:  # noqa: BLE001 - history is best-effort
            logger.warning("Failed to fetch PRs for %s: %s", repo_full_name, exc)

    activity_runs = await store.list_activity_runs(repo_full_name=repo_full_name)
    runs_by_sha: dict[str, dict] = {}
    for r in activity_runs:
        sha = r.get("commit_sha")
        if sha:
            runs_by_sha[sha] = r
            runs_by_sha[sha[:7]] = r

    latest_run = activity_runs[0] if activity_runs else None
    latest_run_sha = (latest_run or {}).get("commit_sha", "")
    latest_run_status = (latest_run or {}).get("status", "")

    merged_history: list[dict] = []
    seen_shas: set[str] = set()

    for c in commits:
        sha = c.get("sha", "")
        short_sha = sha[:7] if sha else ""
        run = runs_by_sha.get(sha) or runs_by_sha.get(short_sha)

        status = "synced"
        status_label = "synced"
        pr_number = None
        pr_url = None
        doc_impact = "No doc drift"

        if run:
            status = run.get("status", "synced")
            status_label = (
                "no drift" if status == "no_drift" else status.replace("_", " ")
            )
            pr_number = run.get("pr_number")
            pr_url = run.get("pr_url")
            diff_preview = run.get("diff_preview")
            if isinstance(diff_preview, dict) and diff_preview.get("file_path"):
                doc_impact = diff_preview.get("file_path")

        seen_shas.add(sha)
        seen_shas.add(short_sha)

        merged_history.append(
            {
                "id": f"gh-commit-{short_sha}",
                "type": "commit",
                "sha": short_sha,
                "full_sha": sha,
                "title": c.get("message", "").split("\n")[0],
                "message": c.get("message", ""),
                "author": c.get("author", "unknown"),
                "avatar_url": c.get("avatar_url", ""),
                "date": c.get("date", ""),
                "html_url": c.get(
                    "html_url",
                    f"https://github.com/{repo_full_name}/commit/{sha}",
                ),
                "status": status,
                "status_label": status_label,
                "doc": doc_impact,
                "pr_number": pr_number,
                "pr_url": pr_url,
                "has_pipeline_run": run is not None,
            }
        )

    for run in activity_runs:
        run_sha = run.get("commit_sha", "")
        short_sha = run_sha[:7] if run_sha else ""
        if short_sha and short_sha in seen_shas:
            continue
        status = run.get("status", "no_drift")
        status_label = "no drift" if status == "no_drift" else status.replace("_", " ")
        merged_history.append(
            {
                "id": f"run-{run.get('delivery_id')}",
                "type": "run",
                "sha": short_sha or "manual",
                "full_sha": run_sha,
                "title": run.get("commit_message") or "Manual Drift Analysis",
                "message": run.get("commit_message") or "",
                "author": run.get("author") or owner,
                "avatar_url": "",
                "date": run.get("created_at") or "",
                "html_url": (
                    f"https://github.com/{repo_full_name}/commit/{run_sha}"
                    if run_sha
                    else None
                ),
                "status": status,
                "status_label": status_label,
                "doc": "Drift simulation / run",
                "pr_number": run.get("pr_number"),
                "pr_url": run.get("pr_url"),
                "has_pipeline_run": True,
            }
        )

    latest_github_commit = commits[0] if commits else None
    latest_github_sha = (latest_github_commit or {}).get("sha", "")
    is_latest_synced = False
    is_latest_running = False

    if latest_github_sha:
        latest_run_matching = runs_by_sha.get(latest_github_sha) or runs_by_sha.get(
            latest_github_sha[:7]
        )
        if latest_run_matching:
            if latest_run_matching.get("status") == "running":
                is_latest_running = True
            elif latest_run_matching.get("status") in {
                "no_drift",
                "pr_open",
                "merged",
                "synced",
            }:
                is_latest_synced = True

    return {
        "repo_full_name": repo_full_name,
        "watch_branch": watch_branch,
        "stats": {
            "total_commits": len(commits),
            "total_runs": len(activity_runs),
            "pull_requests_count": len(pull_requests),
            "status": (monitored or {}).get("status", "listening"),
        },
        "latest_commit_sha": latest_github_sha[:7] if latest_github_sha else "",
        "latest_run_sha": latest_run_sha[:7] if latest_run_sha else "",
        "latest_run_status": latest_run_status,
        "is_latest_synced": is_latest_synced,
        "is_latest_running": is_latest_running,
        "history": merged_history,
        "pull_requests": pull_requests,
        "commits": commits,
    }


@router.post("/repos/{owner}/{repo}/trigger")
async def trigger_repo(
    owner: str,
    repo: str,
    request: Request,
    payload: TriggerRequest | None = None,
) -> dict:
    """Fetch a commit from GitHub and enqueue the full pipeline for it.

    Protects against duplicate execution if the commit is already syncing/running
    or was already synced with no drift.
    """
    store = _get_store(request)
    repo_full_name = f"{owner}/{repo}"
    monitored = await store.get_monitored_repo(repo_full_name)
    if monitored is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{repo_full_name} is not a monitored repository.",
        )

    service = _get_github_service(request)
    _require_github_token(service)

    branch = monitored.get("watch_branch") or "main"
    try:
        if payload is not None and payload.commit_sha:
            commit = await service.get_commit(
                repo_full_name, payload.commit_sha.strip()
            )
        else:
            commit = await service.get_latest_commit(repo_full_name, branch)
    except Exception as exc:
        raise _github_failure(exc) from exc

    if not commit.get("sha"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No commit found for {repo_full_name}@{branch}.",
        )

    target_sha = commit["sha"]
    short_target_sha = target_sha[:7]
    force_run = bool(payload and payload.force)

    # ── Check latest run in history to avoid duplicate sync/rerun ──
    existing_runs = await store.list_activity_runs(repo_full_name=repo_full_name)
    if not force_run and existing_runs:
        # Check if an analysis is currently running for this commit
        running_run = next(
            (
                r
                for r in existing_runs
                if r.get("status") == "running"
                and _is_same_commit(r.get("commit_sha"), target_sha)
            ),
            None,
        )
        if running_run:
            return {
                "status": "already_running",
                "message": f"Commit {short_target_sha} is currently syncing. Please wait for the current run to complete.",
                "delivery_id": running_run["delivery_id"],
                "commit_sha": target_sha,
                "branch": branch,
            }

        # Check if the latest run in history already analyzed this commit
        if payload and getattr(payload, "check_duplicate", False):
            latest_run = existing_runs[0]
            latest_sha = latest_run.get("commit_sha") or ""
            if _is_same_commit(latest_sha, target_sha) and latest_run.get(
                "status"
            ) in {"no_drift", "pr_open", "merged", "synced"}:
                return {
                    "status": "already_synced",
                    "message": f"Commit {short_target_sha} has already been synced with no further drift detected.",
                    "delivery_id": latest_run["delivery_id"],
                    "commit_sha": target_sha,
                    "branch": branch,
                }

    delivery_id = f"manual-{uuid4().hex[:12]}"
    job = WebhookJob(
        delivery_id=delivery_id,
        event_type="push",
        repo_full_name=repo_full_name,
        base_sha=commit.get("parent_sha") or ZERO_SHA,
        head_sha=target_sha,
        ref=f"refs/heads/{branch}",
        received_at=datetime.now(UTC),
        commit_message=commit.get("message", ""),
        author=commit.get("author", ""),
    )

    inline_execution = bool(getattr(request.app.state, "inline_execution", False))
    pipeline = getattr(request.app.state, "pipeline", None)

    if inline_execution and pipeline is not None:
        # Vercel freezes background work after the response, so execute the
        # pipeline inside this request (bounded by the 60s function timeout).
        await pipeline.execute_job(job)
    else:
        queue = getattr(request.app.state, "webhook_queue", None)
        if queue is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Pipeline queue is not configured.",
            )
        await queue.put(job)

    return {
        "status": "enqueued",
        "delivery_id": delivery_id,
        "repo_full_name": repo_full_name,
        "commit_sha": job.head_sha,
        "base_sha": job.base_sha,
        "commit_message": job.commit_message,
        "author": job.author,
        "branch": branch,
    }


# ── Settings ────────────────────────────────────────────────────────────


@router.get("/settings")
async def get_settings(request: Request) -> dict:
    """Read the singleton user settings row."""
    return _settings_payload(await _get_store(request).get_user_settings())


@router.patch("/settings")
async def patch_settings(payload: SettingsPatch, request: Request) -> dict:
    """Update one or more user settings flags."""
    updates = payload.model_dump(exclude_none=True)
    row = await _get_store(request).update_user_settings(
        require_reviewer_approval=_optional_int(
            updates.get("require_reviewer_approval")
        ),
        skip_internal_changes=_optional_int(updates.get("skip_internal_changes")),
        email_on_failed_runs=_optional_int(updates.get("email_on_failed_runs")),
    )
    return _settings_payload(row)


@router.post("/settings/disconnect")
async def disconnect(request: Request) -> dict:
    """Remove installed webhooks and clear the monitored repository list."""
    store = _get_store(request)
    repositories = await store.list_monitored_repos()
    service = _get_github_service(request)

    removed_webhooks = 0
    if service.token:
        for repository in repositories:
            hook_id = repository.get("webhook_id")
            if not hook_id:
                continue
            try:
                await service.delete_repo_webhook(
                    repository["repo_full_name"], int(hook_id)
                )
                removed_webhooks += 1
            except Exception:
                logger.warning(
                    "Could not remove webhook %s for %s",
                    hook_id,
                    repository["repo_full_name"],
                    exc_info=True,
                )

    removed_repos = await store.clear_monitored_repos()
    clear_username = getattr(store, "clear_github_username", None)
    if callable(clear_username):
        await clear_username()

    return {
        "status": "disconnected",
        "removed_repositories": removed_repos,
        "removed_webhooks": removed_webhooks,
    }


# ── Helpers ─────────────────────────────────────────────────────────────


def _settings_payload(row: dict) -> dict:
    return {
        "github_username": row.get("github_username"),
        "require_reviewer_approval": bool(
            row.get("require_reviewer_approval", 1)
        ),
        "skip_internal_changes": bool(row.get("skip_internal_changes", 1)),
        "email_on_failed_runs": bool(row.get("email_on_failed_runs", 0)),
    }


def _optional_int(value: bool | None) -> int | None:
    return int(value) if value is not None else None


def _normalize_drift_action(value: str) -> str:
    lowered = value.strip().lower()
    if "comment" in lowered:
        return "open_pr_comment"
    return "open_pr"


def _is_same_commit(sha1: str | None, sha2: str | None) -> bool:
    """Return True if two commit SHAs match (either exactly or as prefixes)."""
    if not sha1 or not sha2:
        return False
    s1 = sha1.strip().lower()
    s2 = sha2.strip().lower()
    return s1 == s2 or s1.startswith(s2) or s2.startswith(s1)
