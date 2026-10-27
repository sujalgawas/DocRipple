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
async def test_planner_prompt_truncates_large_diff_hunks():
    """Verify planner truncates diffuse diff hunks to under 600 chars."""
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
                heading="Overview",
                start_line=1,
                end_line=10,
                matched_symbols=["func_0"],
                match_method="exact_anchor",
                confidence=1.0,
                current_markdown="Overview content",
            )
        ],
    )

    captured_prompts = []

    class MockLLM:
        async def generate_text(self, system: str, user: str) -> str:
            captured_prompts.append((system, user))
            return json.dumps(
                [
                    {
                        "doc_path": "README.md",
                        "heading": "Overview",
                        "target_symbols": ["func_0"],
                        "instructions": "Update overview",
                    }
                ]
            )

    planner = build_planner_node(MockLLM())
    state = {
        "drift_report": drift_report,
        "full_docs": {"README.md": "Overview content"},
    }
    result = await planner(state)
    assert len(result["edit_plans"]) == 1
    assert len(captured_prompts) == 1

    _, user_prompt = captured_prompts[0]
    # The prompt should NOT contain the 5000 character diff hunk
    assert "A" * 5000 not in user_prompt
    assert "A" * 600 in user_prompt
    assert "A" * 601 not in user_prompt
