from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, model_validator


class SessionRequest(BaseModel):
    size: Literal[5, 10, 20] = 10
    mode: Literal["due", "confusion", "weak_points"] = "due"
    level: Literal["N3", "N4", "N2"] | None = None
    # Confusion Practice scoped to the relation family containing this grammar id (any member
    # works as the anchor). Omitted = pool every confusable item, the original behavior.
    family_of: uuid.UUID | None = None

    @model_validator(mode="after")
    def _family_needs_confusion_mode(self) -> "SessionRequest":
        if self.family_of is not None and self.mode != "confusion":
            raise ValueError("family_of is only valid with mode='confusion'")
        return self


class QuestionOption(BaseModel):
    key: str
    text: str


class QuestionOut(BaseModel):
    id: uuid.UUID
    grammar_id: uuid.UUID
    sentence_with_blank_html: str
    options: list[QuestionOption]


class SessionResponse(BaseModel):
    questions: list[QuestionOut]
    known_words: list[str] = []


class AnswerRequest(BaseModel):
    question_id: uuid.UUID
    selected_option: str
    response_time_ms: int | None = None


class AnswerResponse(BaseModel):
    is_correct: bool
    correct_option: str
    explanation_ru: str | None
    sentence_full_html: str
    next_review: datetime
