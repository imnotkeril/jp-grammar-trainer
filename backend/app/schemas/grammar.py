from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

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


class GrammarRelationSummaryOut(BaseModel):
    """The "other side" of a relation edge — just enough to link/render it, per
    ARCHITECTURE.md V2.3 ("related_grammar": {...})."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    expression_clean: str
    reading: str
    meaning_ru: str
    target_construction: str


class GrammarRelationOut(BaseModel):
    """One relation edge as seen from the perspective of a given grammar item.

    `direction` is "symmetric" for the 5 non-directional relation types, or
    "outgoing"/"incoming" for prerequisite/advanced_version depending on whether the
    viewed item is the `grammar_id` ("from") or `related_grammar_id` ("to") side of the
    stored row — see ARCHITECTURE.md V2.1 ADR-11.
    """

    relation_type: str
    direction: Literal["symmetric", "outgoing", "incoming"]
    strength: float
    source: str
    note: str | None
    related_grammar: GrammarRelationSummaryOut


class GrammarDetailOut(GrammarWithProgressOut):
    relations: list[GrammarRelationOut]


class GrammarListOut(BaseModel):
    """{items, total} wrapper for GET /grammar — the one breaking change vs MVP's bare
    list[GrammarOut] (ARCHITECTURE.md V2.3)."""

    items: list[GrammarWithProgressOut]
    total: int


class GrammarRelationEdgeOut(BaseModel):
    """One row of the bulk edge list for the graph view (ARCHITECTURE.md V2.3,
    GET /grammar/relations) — no embedded grammar payload, just ids + type, since the
    frontend already has node labels from GET /grammar."""

    grammar_id: uuid.UUID
    related_grammar_id: uuid.UUID
    relation_type: str
    direction: Literal["symmetric", "outgoing", "incoming"]
    strength: float
