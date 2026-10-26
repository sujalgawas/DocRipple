"""OpenAI-compatible async LLM client (OpenRouter / Groq / Ollama)."""

import logging

from openai import AsyncOpenAI

from src.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_llm_client() -> AsyncOpenAI:
    """Return a singleton async OpenAI-compatible client."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
        )
    return _client


async def chat_completion(
    system_prompt: str,
    user_message: str,
    model: str | None = None,
) -> str:
    """Send a prompt to the LLM and return the response text."""
    client = get_llm_client()
    response = await client.chat.completions.create(
        model=model or settings.llm_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    content = response.choices[0].message.content or ""
    return content