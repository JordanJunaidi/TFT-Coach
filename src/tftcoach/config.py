"""Application settings loaded from environment variables and `.env`."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # SecretStr masks the value in repr/str so keys can't leak through logs or tracebacks.
    riot_api_key: SecretStr
    riot_region: str = "americas"
    database_url: str = "postgresql://localhost/tftcoach"

    # Any OpenAI-compatible Chat Completions + Embeddings endpoint (Gemini by default).
    llm_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    llm_api_key: SecretStr | None = None
    llm_model: str = "gemini-3.1-flash-lite"
    embedding_model: str = "gemini-embedding-2"
    embedding_dims: int = 768

    # Player the agent and chat UI answer about by default.
    tft_riot_id: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields are populated from the environment
