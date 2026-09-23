from __future__ import annotations

import uuid
from typing import Literal

from beartype import beartype
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress, GrammarStatus
from app.models.grammar_relation import DIRECTIONAL_RELATION_TYPES, GrammarRelation
from app.schemas.grammar import (
    GrammarOut,
    GrammarRelationEdgeOut,
    GrammarRelationOut,
    GrammarRelationSummaryOut,
    GrammarWithProgressOut,
)

Direction = Literal["symmetric", "outgoing", "incoming"]


@beartype
def _direction_for(relation: GrammarRelation, viewed_from_id: uuid.UUID) -> Direction:
    """Direction of `relation` as seen from the perspective of `viewed_from_id`.

    Per ARCHITECTURE.md V2.1 ADR-11: symmetric types are always "symmetric" regardless of
    which physical column holds `viewed_from_id`; directional types are "outgoing" when the
    viewed item is the `grammar_id` ("from") side, "incoming" when it's the
    `related_grammar_id` ("to") side.
    """
    if relation.relation_type not in DIRECTIONAL_RELATION_TYPES:
        return "symmetric"
    return "outgoing" if relation.grammar_id == viewed_from_id else "incoming"


@beartype
def to_progress_out(grammar: Grammar, progress: GrammarProgress | None) -> GrammarWithProgressOut:
    """Assemble the {grammar fields + progress fields} shape shared by the list and detail
    endpoints. `progress` should never actually be None in practice (one row per grammar item,
    seeded 1:1 — ARCHITECTURE.md §3), but a missing row is handled defensively with NEW/now
    defaults rather than a 500, since this assembly also backs the bulk list endpoint.
    """
    from datetime import datetime, timezone

    base = GrammarOut.model_validate(grammar, from_attributes=True).model_dump()
    if progress is not None:
        return GrammarWithProgressOut(
            **base,
            status=progress.status.value,
            next_review=progress.next_review,
            interval_days=progress.interval_days,
            recall_score=progress.recall_score,
        )
    return GrammarWithProgressOut(
        **base,
        status=GrammarStatus.NEW.value,
        next_review=datetime.now(timezone.utc),
        interval_days=0,
        recall_score=0.0,
    )


@beartype
def fetch_relations_for(db: Session, grammar_id: uuid.UUID) -> list[GrammarRelationOut]:
    """All relation edges touching `grammar_id`, from either physical column, mapped into the
    direction-aware API shape (ARCHITECTURE.md V2.3 GET /grammar/{id} "relations" field / GET
    /grammar/{id}/relations).
    """
    stmt = select(GrammarRelation).where(
        or_(GrammarRelation.grammar_id == grammar_id, GrammarRelation.related_grammar_id == grammar_id)
    )
    relations = list(db.scalars(stmt))
    out: list[GrammarRelationOut] = []
    for relation in relations:
        other = relation.related_grammar if relation.grammar_id == grammar_id else relation.grammar
        out.append(
            GrammarRelationOut(
                relation_type=relation.relation_type.value,
                direction=_direction_for(relation, grammar_id),
                strength=relation.strength,
                source=relation.source.value,
                note=relation.note,
                related_grammar=GrammarRelationSummaryOut.model_validate(other, from_attributes=True),
            )
        )
    return out


@beartype
def fetch_all_edges(db: Session) -> list[GrammarRelationEdgeOut]:
    """Bulk edge list for the graph view (ARCHITECTURE.md V2.3 GET /grammar/relations).

    `direction` here is always relative to the stored `grammar_id` (the "from"/base side for
    directional types) since there's no single "viewed from" item for the bulk endpoint —
    the frontend graph renderer treats "outgoing" edges as grammar_id -> related_grammar_id.
    """
    relations = list(db.scalars(select(GrammarRelation)))
    return [
        GrammarRelationEdgeOut(
            grammar_id=relation.grammar_id,
            related_grammar_id=relation.related_grammar_id,
            relation_type=relation.relation_type.value,
            direction="symmetric" if relation.relation_type not in DIRECTIONAL_RELATION_TYPES else "outgoing",
            strength=relation.strength,
        )
        for relation in relations
    ]
