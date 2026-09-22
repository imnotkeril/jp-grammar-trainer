from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SessionRequest(BaseModel):
    size: Literal[5, 10, 20] = 10


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
