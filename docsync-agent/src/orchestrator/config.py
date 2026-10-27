"""Orchestrator-specific configuration via pydantic-settings."""

from pydantic_settings import BaseSettings


class OrchestratorConfig(BaseSettings):
    """Configuration for the LangGraph orchestrator.

    All values can be overridden via ``DOCSYNC_ORCH_<FIELD>`` env vars.
    """

    model_config = {"env_prefix": "DOCSYNC_ORCH_", "case_sensitive": False}

    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = "dev-key"
    llm_model: str = "qwen/qwen-2.5-coder-32b-instruct"

    fallback_llm_base_url: str = "https://openrouter.ai/api/v1"
    fallback_llm_api_key: str = ""
    fallback_llm_model: str = "qwen/qwen-2.5-coder-32b-instruct"

    github_token: str = "dev-github-token"

    checkpoint_db_path: str = ":memory:"

    max_retries: int = 2