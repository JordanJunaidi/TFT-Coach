"""Application settings loaded from environment variables and `.env`."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # SecretStr masks the value in repr/str so the key can't leak through logs or tracebacks.
    riot_api_key: SecretStr
    riot_region: str = "americas"
    database_url: str = "postgresql://localhost/tftcoach"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # fields are populated from the environment
