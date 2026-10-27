"""LLM client — protocol + OpenAI-compatible implementation.

Allows swapping between real LLMs and deterministic fakes in tests,
with automatic failover to secondary providers (such as OpenRouter).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

import httpx
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

    GOOGLE_FALLBACK_MODELS = [
        "gemma-3-27b-it",
        "gemma-3-12b-it",
        "gemma-3-4b-it",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
    ]

    def __init__(
        self,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key: str = "dev-key",
        model: str = "gemma-3-27b-it",
        fallback_base_url: str | None = None,
        fallback_api_key: str | None = None,
        fallback_model: str | None = None,
    ) -> None:
        gemini_fallback = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        resolved_api_key = (api_key or "dev-key").strip()
        resolved_base_url = (base_url or "https://generativelanguage.googleapis.com/v1beta/openai/").rstrip("/")
        resolved_model = model or "gemma-3-27b-it"

        if gemini_fallback and (not resolved_api_key or resolved_api_key == "dev-key" or resolved_api_key.startswith("gsk_")):
            resolved_api_key = gemini_fallback
            if not resolved_base_url or "groq.com" in resolved_base_url:
                resolved_base_url = "https://generativelanguage.googleapis.com/v1beta"
                resolved_model = "gemma-3-27b-it"

        self._base_url = resolved_base_url
        self._api_key = resolved_api_key
        self._model = resolved_model
        self._client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            max_retries=0,
            timeout=15.0,
        )

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
        ).strip()
        fb_model = (
            fallback_model
            or os.getenv("FALLBACK_LLM_MODEL")
            or "qwen/qwen-2.5-coder-32b-instruct"
        )

        self._fallback_base_url = fb_base
        self._fallback_api_key = fb_key
        self._fallback_model = fb_model

        self._fallback_client: AsyncOpenAI | None = None
        # When Google is configured, never use OpenRouter fallback (prevents 57s hanging on dead OpenRouter)
        if not self._is_google_configured() and self._fallback_api_key and self._fallback_api_key not in ("dev-key", ""):
            # Avoid redundant fallback if primary is identical
            if not (
                self._base_url == self._fallback_base_url
                and self._api_key == self._fallback_api_key
                and self._model == self._fallback_model
            ):
                self._fallback_client = AsyncOpenAI(
                    base_url=self._fallback_base_url,
                    api_key=self._fallback_api_key,
                    max_retries=0,
                    timeout=15.0,
                    default_headers={
                        "HTTP-Referer": "https://docripple.vercel.app",
                        "X-Title": "DocRipple",
                    },
                )

    def _is_google_configured(self) -> bool:
        key = (self._api_key or "").strip()
        url = (self._base_url or "").strip().lower()
        if "groq.com" in url or "openrouter.ai" in url:
            return False
        if key.startswith("AIza") or "googleapis.com" in url:
            return True
        for env_key in ("LLM_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
            val = (os.getenv(env_key) or "").strip()
            if val.startswith("AIza"):
                return True
        return False

    def _get_google_api_key(self) -> str:
        key = (self._api_key or "").strip()
        if key.startswith("AIza"):
            return key
        for env_key in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "LLM_API_KEY"):
            val = (os.getenv(env_key) or "").strip()
            if val.startswith("AIza"):
                return val
        return key

    async def _generate_google(self, system_prompt: str, user_prompt: str) -> str:
        """Call Google's native v1beta/models/{model}:generateContent REST endpoint with fallback chain."""
        models_to_try: list[str] = []
        if self._model and self._model in self.GOOGLE_FALLBACK_MODELS:
            models_to_try.append(self._model)
        for m in self.GOOGLE_FALLBACK_MODELS:
            if m not in models_to_try:
                models_to_try.append(m)

        api_key = self._get_google_api_key()
        combined_text = f"{system_prompt}\n\n---\n\n{user_prompt}" if system_prompt else user_prompt
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": combined_text}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": 2048,
            },
        }

        last_exc: Exception | None = None
        async with httpx.AsyncClient(timeout=12.0) as http_client:
            for candidate_model in models_to_try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{candidate_model}:generateContent?key={api_key}"
                try:
                    logger.info("Calling Google native generateContent for model %s", candidate_model)
                    resp = await http_client.post(url, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                    candidates = data.get("candidates") or []
                    if not candidates:
                        raise RuntimeError(f"Google API returned no candidates: {data}")
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if not parts:
                        raise RuntimeError(f"Google API candidate had no parts: {candidates[0]}")
                    text = parts[0].get("text", "")
                    return text
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "Google native generateContent failed for model %s: %s; falling back to next model",
                        candidate_model,
                        exc,
                    )
                    continue

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No Google model candidate succeeded")

    @staticmethod
    def _is_gemma_or_google(model: str, base_url: str) -> bool:
        return "gemma" in (model or "").lower() or "generativelanguage.googleapis.com" in (base_url or "").lower()

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        status_code = getattr(exc, "status_code", None)
        if status_code is not None and (status_code == 429 or status_code >= 500):
            return True
        cls_name = exc.__class__.__name__
        if any(name in cls_name for name in ("RateLimit", "InternalServer", "BadGateway", "ServiceUnavailable", "GatewayTimeout", "APIConnection", "APITimeout")):
            return True
        msg = str(exc).lower()
        if any(term in msg for term in ("429", "too many requests", "rate limit", "resource_exhausted", "quota exceeded")):
            return True
        if any(f"status {code}" in msg or f"error {code}" in msg for code in ("500", "502", "503", "504")):
            return True
        return False

    def _format_messages_for_model(
        self,
        model: str,
        base_url: str,
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        if not self._is_gemma_or_google(model, base_url):
            return messages

        system_parts: list[str] = []
        user_parts: list[str] = []
        other_messages: list[dict[str, str]] = []

        for m in messages:
            role = m.get("role")
            content = m.get("content", "")
            if role == "system":
                system_parts.append(content)
            elif role == "user":
                user_parts.append(content)
            else:
                other_messages.append(m)

        if system_parts:
            sys_text = "\n\n".join(system_parts)
            user_text = "\n\n---\n\n".join(user_parts) if user_parts else ""
            combined = f"{sys_text}\n\n---\n\n{user_text}" if user_text else sys_text
            return [{"role": "user", "content": combined}, *other_messages]

        return messages

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
        primary_models = [self._model]
        if self._is_gemma_or_google(self._model, self._base_url):
            for m in self.GOOGLE_FALLBACK_MODELS:
                if m not in primary_models:
                    primary_models.append(m)

        last_primary_exc: Exception | None = None
        for i, candidate_model in enumerate(primary_models):
            formatted_messages = self._format_messages_for_model(
                candidate_model, self._base_url, messages
            )
            try:
                return await self._call_chat_completions(
                    self._client, candidate_model, formatted_messages, temperature
                )
            except Exception as exc:
                last_primary_exc = exc
                is_retryable = self._is_retryable_error(exc)
                has_next = i + 1 < len(primary_models)
                if is_retryable and has_next:
                    next_model = primary_models[i + 1]
                    logger.warning(
                        "Primary model %s failed with %s: %s; zero-sleep fallback to %s",
                        candidate_model,
                        exc.__class__.__name__,
                        exc,
                        next_model,
                    )
                    continue
                break

        if self._fallback_client is not None:
            logger.warning(
                "Primary LLM (%s @ %s) failed with %s: %s; falling back to %s @ %s",
                self._model,
                self._base_url,
                last_primary_exc.__class__.__name__ if last_primary_exc else "Error",
                last_primary_exc,
                self._fallback_model,
                self._fallback_base_url,
            )
            models_to_try = [self._fallback_model]
            if "openrouter.ai" in self._fallback_base_url:
                for free_model in (
                    "cohere/north-mini-code:free",
                    "nvidia/nemotron-3.5-lightning:free",
                ):
                    if free_model not in models_to_try:
                        models_to_try.append(free_model)

            last_fb_exc: Exception | None = None
            for candidate_model in models_to_try:
                formatted_fb = self._format_messages_for_model(
                    candidate_model, self._fallback_base_url, messages
                )
                try:
                    logger.info("Attempting completion with fallback model %s", candidate_model)
                    return await self._call_chat_completions(
                        self._fallback_client, candidate_model, formatted_fb, temperature
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
                raise last_fb_exc from last_primary_exc

        if last_primary_exc is not None:
            raise last_primary_exc
        raise RuntimeError("No LLM completion could be obtained")

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: type[BaseModel],
    ) -> BaseModel:
        """Send a prompt and parse the response as JSON matching the schema."""
        schema_json = json.dumps(response_schema.model_json_schema(), indent=2)
        full_system = (
            f"{system_prompt}\n\n"
            f"Respond ONLY with a valid JSON object matching this schema. "
            f"Do not wrap in markdown fences.\n\n{schema_json}"
        )

        if self._is_google_configured():
            content = await self._generate_google(full_system, user_prompt)
        else:
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
            if "```" in content:
                content = content[:content.rfind("```")]
        content = content.strip()

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
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
        if self._is_google_configured():
            return await self._generate_google(system_prompt, user_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = await self._call_completion(
            messages=messages,
            temperature=0.0,
        )
        return response.choices[0].message.content or ""