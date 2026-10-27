"""LLM client — protocol + OpenAI-compatible implementation.

Allows swapping between real LLMs and deterministic fakes in tests,
with automatic failover to secondary providers (such as OpenRouter).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

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
    """OpenAI-compatible async client with automatic fallback."""

    def __init__(
        self,
        base_url: str = "https://openrouter.ai/api/v1",
        api_key: str = "dev-key",
        model: str = "qwen/qwen-2.5-coder-32b-instruct",
        fallback_base_url: str | None = None,
        fallback_api_key: str | None = None,
        fallback_model: str | None = None,
    ) -> None:
        self._base_url = (base_url or "https://openrouter.ai/api/v1").rstrip("/")
        self._api_key = api_key or "dev-key"
        self._model = model or "qwen/qwen-2.5-coder-32b-instruct"
        self._client = AsyncOpenAI(base_url=self._base_url, api_key=self._api_key)

        # Fallback provider configuration (e.g., OpenRouter)
        fb_base = (
            fallback_base_url
            or os.getenv("FALLBACK_LLM_BASE_URL")
            or "https://openrouter.ai/api/v1"
        ).rstrip("/")
        fb_key = (
            fallback_api_key
            or os.getenv("FALLBACK_LLM_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or ""
        )
        fb_model = (
            fallback_model
            or os.getenv("FALLBACK_LLM_MODEL")
            or "qwen/qwen-2.5-coder-32b-instruct"
        )

        self._fallback_base_url = fb_base
        self._fallback_api_key = fb_key
        self._fallback_model = fb_model

        self._fallback_client: AsyncOpenAI | None = None
        if self._fallback_api_key and self._fallback_api_key not in ("dev-key", ""):
            # Avoid redundant fallback if primary is identical
            if not (
                self._base_url == self._fallback_base_url
                and self._api_key == self._fallback_api_key
                and self._model == self._fallback_model
            ):
                self._fallback_client = AsyncOpenAI(
                    base_url=self._fallback_base_url,
                    api_key=self._fallback_api_key,
                    default_headers={
                        "HTTP-Referer": "https://docripple.vercel.app",
                        "X-Title": "DocRipple",
                    },
                )

    async def _call_chat_completions(
        self,
        client: AsyncOpenAI,
        model: str,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> Any:
        return await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
        )

    async def _call_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
    ) -> Any:
        try:
            return await self._call_chat_completions(
                self._client, self._model, messages, temperature
            )
        except Exception as exc:
            if self._fallback_client is not None:
                logger.warning(
                    "Primary LLM (%s @ %s) failed with %s: %s; falling back to %s @ %s",
                    self._model,
                    self._base_url,
                    exc.__class__.__name__,
                    exc,
                    self._fallback_model,
                    self._fallback_base_url,
                )
                models_to_try = [self._fallback_model]
                # If using OpenRouter, add free models as backup in case of 403 key limit or 404
                if "openrouter.ai" in self._fallback_base_url:
                    for free_model in (
                        "cohere/north-mini-code:free",
                        "nvidia/nemotron-3.5-lightning:free",
                    ):
                        if free_model not in models_to_try:
                            models_to_try.append(free_model)

                last_fb_exc: Exception | None = None
                for candidate_model in models_to_try:
                    try:
                        logger.info("Attempting completion with fallback model %s", candidate_model)
                        return await self._call_chat_completions(
                            self._fallback_client, candidate_model, messages, temperature
                        )
                    except Exception as fb_exc:
                        last_fb_exc = fb_exc
                        logger.warning(
                            "Fallback LLM candidate (%s @ %s) failed with %s: %s",
                            candidate_model,
                            self._fallback_base_url,
                            fb_exc.__class__.__name__,
                            fb_exc,
                        )
                if last_fb_exc:
                    raise last_fb_exc from exc
            raise

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

        messages = [
            {"role": "system", "content": full_system},
            {"role": "user", "content": user_prompt},
        ]

        response = await self._call_completion(
            messages=messages,
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
        content = content.strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            # Fallback extraction for json inside extraneous text
            start = content.find("{")
            end = content.rfind("}")
            if start != -1 and end != -1 and end > start:
                parsed = json.loads(content[start : end + 1])
            else:
                raise

        return response_schema.model_validate(parsed)

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
    ) -> str:
        """Send a prompt and return free-form text."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = await self._call_completion(
            messages=messages,
            temperature=0.0,
        )
        return response.choices[0].message.content or ""