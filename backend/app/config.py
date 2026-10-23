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

    # Roadmap item 2: opt-in LLM re-classification of the existing heuristic relation edges
    # (`generate_relations.py --reclassify`). Off by default so adding an API key for question
    # generation never silently starts spending tokens on relation work.
    llm_relation_reclassify: bool = False

    generation_shortage_threshold: int = 5
    generation_batch_size: int = 15

    # V3 slice (ARCHITECTURE.md "V3 Slice: Adaptive Practice & Vocabulary") — ADR-17/ADR-16.
    weak_point_mix_ratio: float = 0.2
    known_streak_threshold: int = 5
    # Personal path on the owner's machine, not portable — only used by the one-off
    # `app/scripts/seed_vocabulary.py`, never read at request time. See ARCHITECTURE.md V3.2.
    # Optional: directory with the original Anki vocabulary CSVs. Empty -> use the committed
    # data/seed/vocabulary_n3.json snapshot (what a fresh clone should do).
    vocabulary_csv_source_dir: str = ""

    cors_allowed_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


settings = Settings()
