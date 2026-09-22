from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FormationRule(BaseModel):
    pos: str
    form_label: str
    example_html: str


class GrammarOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    expression_html: str
    expression_clean: str
    reading: str
    meaning_ru: str
    pattern_text: str
    formation_rules: list[FormationRule]
    level: str
    tags: list[str]
    target_construction: str


class GrammarWithProgressOut(GrammarOut):
    status: str
    next_review: datetime
    interval_days: int
    recall_score: float
