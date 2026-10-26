"""Stage 0 onboarding API router."""

from __future__ import annotations

import logging
from urllib.parse import quote

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status

from src.config import settings
from src.contracts.schemas import DocStyleSkill, OnboardRepoResult, RepoMemoryMap
from src.onboarding.schemas import OnboardRequest
from src.onboarding.service import OnboardingService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/repos", tags=["onboarding"])

_GITHUB_API = "https://api.github.com"
_CODE_EXTENSIONS = {
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


@router.post("/onboard", response_model=OnboardRepoResult)
async def onboard_repo(
    payload: OnboardRequest,
    request: Request,
) -> OnboardRepoResult:
    """Run Stage 0 using inline files or a snapshot fetched from GitHub."""
    service = _get_onboarding_service(request)
    code_files = payload.code_files
    docs = payload.docs

    if not code_files and not docs:
        try:
            code_files, docs = await _fetch_github_snapshot(
                payload.repo_full_name,
                payload.branch,
            )
        except httpx.HTTPError as exc:
            logger.exception("GitHub snapshot fetch failed for %s", payload.repo_full_name)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to fetch repository snapshot: {exc}",
            ) from exc

    if not code_files and not docs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Provide code_files/docs, or a repo_full_name/branch whose "
                "GitHub snapshot can be fetched."
            ),
        )

    return await service.onboard_repository(payload.repo_full_name, code_files, docs)


@router.get("/{owner}/{repo}/skill", response_model=DocStyleSkill)
async def get_repo_style_skill(
    owner: str,
    repo: str,
    request: Request,
) -> DocStyleSkill:
    """Return the repository-specific DocStyleSkill."""
    store = _get_context_store(request)
    skill = await store.get_style_skill(f"{owner}/{repo}")
    if skill is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No DocStyleSkill found for {owner}/{repo}; run POST /onboard first.",
        )
    return skill


@router.get("/{owner}/{repo}/memory", response_model=RepoMemoryMap)
async def get_repo_memory(
    owner: str,
    repo: str,
    request: Request,
    symbols: str | None = Query(
        default=None,
        description="Comma-separated symbol names/paths for a bounded subgraph.",
    ),
) -> RepoMemoryMap:
    """Return the file's memory map, or a 2-hop subgraph around symbols."""
    store = _get_context_store(request)
    repo_full_name = f"{owner}/{repo}"
    seeds = [seed.strip() for seed in (symbols or "").split(",") if seed.strip()]
    return await store.get_memory_subgraph(repo_full_name, seeds, max_hops=2)


def _get_onboarding_service(request: Request) -> OnboardingService:
    service = getattr(request.app.state, "onboarding_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Onboarding service is not configured.",
        )
    return service


def _get_context_store(request: Request):
    store = getattr(request.app.state, "context_store", None)
    if store is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Context store is not configured.",
        )
    return store


async def _fetch_github_snapshot(
    repo_full_name: str,
    branch: str,
) -> tuple[dict[str, str], dict[str, str]]:
    """Fetch source and Markdown files from a GitHub branch."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "DocRipple-Onboarding",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    code_files: dict[str, str] = {}
    docs: dict[str, str] = {}

    async with httpx.AsyncClient(base_url=_GITHUB_API, timeout=30.0) as client:
        tree_response = await client.get(
            f"/repos/{repo_full_name}/git/trees/{quote(branch, safe='')}",
            headers=headers,
            params={"recursive": "1"},
        )
        tree_response.raise_for_status()

        candidates: list[str] = []
        for item in tree_response.json().get("tree", []):
            if item.get("type") != "blob":
                continue
            path = item.get("path", "")
            if not path:
                continue
            if path.lower().endswith(".md") or any(
                path.lower().endswith(ext) for ext in _CODE_EXTENSIONS
            ):
                candidates.append(path)

        for path in sorted(set(candidates)):
            content_response = await client.get(
                f"/repos/{repo_full_name}/contents/{quote(path, safe='/')}",
                headers={**headers, "Accept": "application/vnd.github.raw"},
                params={"ref": branch},
            )
            if content_response.status_code != 200:
                logger.warning(
                    "Skipping %s from %s (HTTP %d)",
                    path,
                    repo_full_name,
                    content_response.status_code,
                )
                continue
            if path.lower().endswith(".md"):
                docs[path] = content_response.text
            else:
                code_files[path] = content_response.text

    return code_files, docs
