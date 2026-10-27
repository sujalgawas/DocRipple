import os

from pydantic import field_validator
from pydantic_settings import BaseSettings


class OrchestratorConfig(BaseSettings):
    """Configuration for the LangGraph orchestrator.

    All values can be overridden via ``DOCSYNC_ORCH_<FIELD>`` env vars.
    """

    model_config = {"env_prefix": "DOCSYNC_ORCH_", "case_sensitive": False, "extra": "ignore"}

    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: str = "dev-key"
    llm_model: str = "gemma-3-27b-it"

    fallback_llm_base_url: str = "https://openrouter.ai/api/v1"
    fallback_llm_api_key: str = ""
    fallback_llm_model: str = "qwen/qwen-2.5-coder-32b-instruct"

    gemini_api_key: str = ""
    google_api_key: str = ""

    github_token: str = "dev-github-token"

    checkpoint_db_path: str = ":memory:"

    max_retries: int = 1

    @field_validator("llm_api_key", mode="before")
    @classmethod
    def _resolve_llm_api_key(cls, v: str | None) -> str:
        gemini_key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("DOCSYNC_ORCH_GEMINI_API_KEY")
            or os.getenv("DOCSYNC_ORCH_GOOGLE_API_KEY")
            or ""
        ).strip()
        val = (v or "").strip()
        if gemini_key and (not val or val == "dev-key" or val.startswith("gsk_")):
            return gemini_key
        return val or gemini_key or "dev-key"

    @field_validator("llm_base_url", mode="before")
    @classmethod
    def _resolve_llm_base_url(cls, v: str | None) -> str:
        val = (v or "").strip()
        gemini_key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or ""
        ).strip()
        llm_key = (os.getenv("LLM_API_KEY") or "").strip()
        if gemini_key and (not llm_key or llm_key.startswith("gsk_")) and "groq.com" in val:
            return "https://generativelanguage.googleapis.com/v1beta/openai/"
        return val or "https://generativelanguage.googleapis.com/v1beta/openai/"

    @field_validator("llm_model", mode="before")
    @classmethod
    def _resolve_llm_model(cls, v: str | None) -> str:
        val = (v or "").strip()
        gemini_key = (
            os.getenv("GEMINI_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
            or ""
        ).strip()
        llm_key = (os.getenv("LLM_API_KEY") or "").strip()
        if gemini_key and (not llm_key or llm_key.startswith("gsk_")) and ("groq" in val or "gpt-oss" in val):
            return "gemma-3-27b-it"
        return val or "gemma-3-27b-it"