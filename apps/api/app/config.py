from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://papeles:papeles@localhost:5432/papeles"
    cors_origins: list[str] = ["http://localhost:3000"]

    # Claude: credentials come from ANTHROPIC_API_KEY (read by the SDK itself).
    anthropic_model: str = "claude-opus-5-5"
    anthropic_effort: str = "low"  # short Q&A answers don't need deep reasoning

    # Multilingual so Tagalog and Bisaya questions match English source pages.
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    embedding_dim: int = 384
    top_k: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
