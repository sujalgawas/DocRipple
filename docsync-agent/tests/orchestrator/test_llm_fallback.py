"""Tests for OpenAICompatibleLLMClient fallback and prompt optimization."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import APIStatusError
from pydantic import BaseModel

from src.contracts.schemas import (
    ChangeClass,
    ChangedSymbol,
    ChangeReport,
    DriftReport,
    ImpactedDocSection,
)
from src.orchestrator.llm_client import OpenAICompatibleLLMClient
from src.orchestrator.nodes.planner import build_planner_node


class DummySchema(BaseModel):
    name: str
    count: int


def _make_mock_response(content: str):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


@pytest.mark.asyncio
async def test_llm_primary_success_does_not_trigger_fallback():
    client = OpenAICompatibleLLMClient(
        base_url="https://api.groq.com/openai/v1",
        api_key="primary-key",
        model="groq-model",
        fallback_base_url="https://openrouter.ai/api/v1",
        fallback_api_key="fallback-key",
        fallback_model="openrouter-model",
    )

    primary_response = _make_mock_response("primary response")
    with patch.object(
        client._client.chat.completions,
        "create",
        new=AsyncMock(return_value=primary_response),
    ) as mock_primary, patch.object(
        client._fallback_client.chat.completions,
        "create",
        new=AsyncMock(),
    ) as mock_fallback:
        result = await client.generate_text("system", "user")
        assert result == "primary response"
        mock_primary.assert_awaited_once()
        mock_fallback.assert_not_awaited()


@pytest.mark.asyncio
async def test_llm_primary_413_falls_back_to_openrouter():
    client = OpenAICompatibleLLMClient(
        base_url="https://api.groq.com/openai/v1",
        api_key="primary-key",
        model="groq-model",
        fallback_base_url="https://openrouter.ai/api/v1",
        fallback_api_key="fallback-key",
        fallback_model="qwen/qwen-2.5-coder-32b-instruct",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 413
    mock_resp.headers = {}
    mock_resp.json.return_value = {
        "error": {
            "message": "Request too large on tokens per minute (TPM): Limit 8000, Requested 23400",
            "code": "rate_limit_exceeded",
        }
    }
    error_413 = APIStatusError(
        "Request too large",
        response=mock_resp,
        body=mock_resp.json.return_value,
    )

    fallback_response = _make_mock_response("openrouter response")

    with patch.object(
        client._client.chat.completions,
        "create",
        new=AsyncMock(side_effect=error_413),
    ) as mock_primary, patch.object(
        client._fallback_client.chat.completions,
        "create",
        new=AsyncMock(return_value=fallback_response),
    ) as mock_fallback:
        result = await client.generate_text("system", "user")
        assert result == "openrouter response"
        mock_primary.assert_awaited_once()
        mock_fallback.assert_awaited_once()


@pytest.mark.asyncio
async def test_llm_primary_json_failure_falls_back_to_openrouter():
    client = OpenAICompatibleLLMClient(
        base_url="https://api.groq.com/openai/v1",
        api_key="primary-key",
        model="groq-model",
        fallback_base_url="https://openrouter.ai/api/v1",
        fallback_api_key="fallback-key",
        fallback_model="qwen/qwen-2.5-coder-32b-instruct",
    )

    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_resp.headers = {}
    mock_resp.json.return_value = {"error": {"message": "Rate limit exceeded"}}
    error_429 = APIStatusError(
        "Rate limit exceeded",
        response=mock_resp,
        body=mock_resp.json.return_value,
    )

    fallback_response = _make_mock_response(
        "```json\n{\"name\": \"widget\", \"count\": 42}\n```"
    )

    with patch.object(
        client._client.chat.completions,
        "create",
        new=AsyncMock(side_effect=error_429),
    ), patch.object(
        client._fallback_client.chat.completions,
        "create",
        new=AsyncMock(return_value=fallback_response),
    ):
        result = await client.generate_json("sys", "user", DummySchema)
        assert isinstance(result, DummySchema)
        assert result.name == "widget"
        assert result.count == 42


@pytest.mark.asyncio
async def test_client_has_zero_retries_and_timeout_15():
    """Verify AsyncOpenAI has max_retries=0 and timeout=15.0 to prevent 41s SDK sleep."""
    client = OpenAICompatibleLLMClient(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key="gemini-key",
        model="gemma-3-27b-it",
    )
    assert client._client.max_retries == 0
    assert client._client.timeout == 15.0


@pytest.mark.asyncio
async def test_gemma_uses_native_google_generate_content():
    """Verify Google/Gemma uses native v1beta/models/{model}:generateContent with combined prompts."""
    import httpx

    client = OpenAICompatibleLLMClient(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="AIzaSyDummyKey",
        model="gemma-3-27b-it",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "native google response"}]}}
        ]
    }
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)) as mock_post:
        result = await client.generate_text("System instruction", "User query")
        assert result == "native google response"
        mock_post.assert_awaited_once()
        url = mock_post.call_args[0][0]
        assert "generativelanguage.googleapis.com/v1beta/models/gemma-3-27b-it:generateContent" in url
        assert "key=AIzaSyDummyKey" in url
        payload = mock_post.call_args.kwargs["json"]
        parts = payload["contents"][0]["parts"]
        assert parts[0]["text"] == "System instruction\n\n---\n\nUser query"


@pytest.mark.asyncio
async def test_gemma_native_multi_model_fallback():
    """Verify first model failure triggers zero-sleep fallback to next Google candidate."""
    import httpx

    client = OpenAICompatibleLLMClient(
        base_url="https://generativelanguage.googleapis.com/v1beta",
        api_key="AIzaSyDummyKey",
        model="gemma-3-27b-it",
    )
    fail_resp = MagicMock()
    fail_resp.status_code = 404

    ok_resp = MagicMock()
    ok_resp.status_code = 200
    ok_resp.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "gemma-3-12b-it response"}]}}
        ]
    }

    called_urls = []

    async def mock_post(url, *args, **kwargs):
        called_urls.append(url)
        if "gemma-3-27b-it" in url:
            raise httpx.HTTPStatusError("Not found", request=MagicMock(), response=fail_resp)
        return ok_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        result = await client.generate_text("System", "User")
        assert result == "gemma-3-12b-it response"
        assert len(called_urls) == 2
        assert "gemma-3-27b-it" in called_urls[0]
        assert "gemma-3-12b-it" in called_urls[1]


@pytest.mark.asyncio
async def test_planner_is_deterministic_and_caps_at_one():
    """Verify planner node makes 0 LLM calls and caps at top 1 impacted section."""
    huge_diff = "A" * 5000
    changed_symbols = [
        ChangedSymbol(
            file_path="src/big.py",
            symbol_name=f"func_{i}",
            symbol_kind="function",
            change_class=ChangeClass.BEHAVIOR,
            change_type="modified",
            diff_hunk=huge_diff,
        )
        for i in range(5)
    ]
    change_report = ChangeReport(
        delivery_id="deliv-diff-test",
        repo_full_name="org/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        changed_symbols=changed_symbols,
    )
    drift_report = DriftReport(
        change_report=change_report,
        impacted_sections=[
            ImpactedDocSection(
                doc_path="README.md",
                heading=f"Section_{i}",
                start_line=1,
                end_line=10,
                matched_symbols=[f"func_{i}"],
                match_method="exact_anchor",
                confidence=0.5 + (i * 0.1),
                current_markdown="Overview content",
            )
            for i in range(4)
        ],
    )

    class MockLLM:
        async def generate_text(self, system: str, user: str) -> str:
            raise AssertionError("LLM should not be called by deterministic planner!")

    planner = build_planner_node(MockLLM())
    state = {
        "drift_report": drift_report,
        "full_docs": {"README.md": "Overview content"},
    }
    result = await planner(state)
    # Capped at top 1 most impacted section
    assert len(result["edit_plans"]) == 1
    # Sorted by confidence descending: Section_3 (0.8)
    assert result["edit_plans"][0].heading == "Section_3"
    # Instructions contain truncated diff hunk
    assert "A" * 5000 not in result["edit_plans"][0].instructions
    assert "diff:" in result["edit_plans"][0].instructions


@pytest.mark.asyncio
async def test_writer_timeout_uses_deterministic_fallback():
    """Verify writer applies deterministic fallback when LLM times out or errors."""
    from src.orchestrator.nodes.writer import build_writer_node
    from src.orchestrator.state import SectionEditPlan

    class FailingLLM:
        async def generate_text(self, system: str, user: str) -> str:
            raise TimeoutError("LLM call timed out")

    writer = build_writer_node(FailingLLM())
    state = {
        "drift_report": DriftReport(
            change_report=ChangeReport(
                delivery_id="deliv-fallback",
                repo_full_name="org/repo",
                base_sha="a" * 40,
                head_sha="b" * 40,
                changed_symbols=[
                    ChangedSymbol(
                        file_path="src/calc.py",
                        symbol_name="compute_total",
                        symbol_kind="function",
                        change_class=ChangeClass.API_SURFACE,
                        change_type="modified",
                        new_signature="def compute_total(a: int, b: int) -> int",
                        diff_hunk="def compute_total(a: int, b: int) -> int",
                    )
                ],
            ),
            impacted_sections=[
                ImpactedDocSection(
                    doc_path="README.md",
                    heading="API Reference",
                    start_line=1,
                    end_line=5,
                    matched_symbols=["compute_total"],
                    match_method="exact_anchor",
                    confidence=0.9,
                    current_markdown="Old content",
                )
            ],
        ),
        "edit_plans": [
            SectionEditPlan(
                doc_path="README.md",
                heading="API Reference",
                target_symbols=["compute_total"],
                instructions="Document compute_total",
            )
        ],
        "full_docs": {"README.md": "# API Reference\nOld content\n"},
    }

    result = await writer(state)
    assert len(result["drafts"]) == 1
    draft = result["drafts"][0]
    assert "compute_total" in draft.updated_markdown
    assert "def compute_total(a: int, b: int) -> int" in draft.updated_markdown
    assert "README.md" in result["updated_docs"]
    assert "compute_total" in result["updated_docs"]["README.md"]
