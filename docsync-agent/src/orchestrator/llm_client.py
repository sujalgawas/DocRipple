"""LLM client — protocol + OpenAI-compatible implementation.

Allows swapping between real LLMs and deterministic fakes in tests.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class LLMClientProtocol(Protocol):
    """Injectable LLM backend — swap real OpenAI for a fake in tests."""

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
    ) -> BaseModel:
        """Return structured output matching ``response_schema``."""
        ...

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Return free-form text."""
        ...


class OpenAICompatibleLLMClient:
    """OpenAI-compatible async client (OpenRouter, Groq, Ollama, etc.)."""

    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = "dev-key",
        model: str = "qwen/qwen-2.5-coder-32b-instruct",
    ) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key or "dev-key")
        self._model = model

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
    ) -> BaseModel:
        """Send a prompt and parse the response as JSON matching the schema."""
        # Build schema instructions into the system prompt
        schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
        full_system = (
            f"{system_prompt}\n\n"
            f"Respond ONLY with a valid JSON object matching this schema. "
            f"Do not wrap in markdown fences.\n\n{schema_json}"
        )

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        content = response.choices[0].message.content or "{}"

        # Strip markdown fences if present
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:]) if len(lines) > 1 else content
            if content.rstrip().endswith("```"):
                content = content.rstrip()[:-3]

        parsed = json.loads(content)
        return response_schema.model_validate(parsed)

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Send a prompt and return free-form text."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        return response.choices[0].message.content or ""