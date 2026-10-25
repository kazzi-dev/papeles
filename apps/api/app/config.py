from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Provider = Literal["claude", "groq", "gemini", "openrouter"]

# OpenAI-compatible endpoints and a sensible default model for each. Free tiers and model
# names change often; override with LLM_BASE_URL / LLM_MODEL when they do.
PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "openai/gpt-oss-120b"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "gemini-flash-latest"),
    "openrouter": ("https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct:free"),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://papeles:papeles@localhost:5432/papeles"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Which model writes the answers. Without a key the API still runs and returns sources.
    llm_provider: Provider = "claude"
    llm_api_key: str = ""
    llm_model: str = ""  # empty = the provider's default
    llm_base_url: str = ""  # empty = the provider's default

    # Claude. ANTHROPIC_API_KEY also works in place of LLM_API_KEY when the provider is claude.
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "low"  # short Q&A answers don't need deep reasoning

    # Multilingual so Tagalog and Bisaya questions match English source pages.
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 384
    top_k: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
