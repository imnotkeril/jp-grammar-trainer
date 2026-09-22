from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment / .env.

    See ARCHITECTURE.md §10 for the full env var reference.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://user:pass@localhost:5432/postgres"

    llm_provider: Literal["openai", "anthropic"] = "anthropic"
    openai_api_key: str | None = None
    anthropic_api_key: str | None = None

    generation_shortage_threshold: int = 5
    generation_batch_size: int = 15

    cors_allowed_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
