from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field


class ProductionSessionRequest(BaseModel):
    size: Literal[5, 10, 20] = 5
    level: Literal["N3", "N4", "N2"] | None = None


class ProductionPrompt(BaseModel):
    """One "write a sentence with this pattern" prompt. The Russian `meaning_ru` is the
    translation of the model sentence, so the exercise doubles as translate-into-Japanese."""

    grammar_id: uuid.UUID
    level: str
    pattern_hint: str
    meaning_hint: str
    meaning_ru: str
    formation_hints: list[str]


class ProductionSessionResponse(BaseModel):
    prompts: list[ProductionPrompt]


class ProductionCheckRequest(BaseModel):
    grammar_id: uuid.UUID
    answer: str = Field(max_length=500)


class ProductionCheckResponse(BaseModel):
    # "exact" = the target form appears verbatim; "stem" = only its conjugation-insensitive
    # stem does (e.g. いただいて for いただきました); "none" = neither; "empty" = no Japanese
    # text typed. Advisory only — the learner still self-rates against the model sentence.
    match: Literal["exact", "stem", "none", "empty"]
    too_short: bool
    target_construction: str
    model_sentence_html: str
    model_sentence_clean: str
