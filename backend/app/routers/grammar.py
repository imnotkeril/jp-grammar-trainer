from __future__ import annotations

import uuid

from beartype import beartype
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress
from app.schemas.grammar import (
    GrammarDetailOut,
    GrammarListOut,
    GrammarRelationEdgeOut,
    GrammarRelationOut,
)
from app.services.grammar_relations import fetch_all_edges, fetch_relations_for, to_progress_out

router = APIRouter(prefix="/grammar", tags=["grammar"])


@router.get("", response_model=GrammarListOut)
@beartype
def list_grammar(
    db: Session = Depends(get_db),
    q: str | None = Query(default=None, description="case-insensitive substring match"),
    status: str | None = Query(default=None, description="grammar_progress.status filter"),
    tag: str | None = Query(default=None, description="tag containment filter (no-op until tags are populated)"),
    limit: int = Query(default=205, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> GrammarListOut:
    """GET /grammar — browsable, filterable list of seeded N3 grammar items.

    See ARCHITECTURE.md V2.3. Default limit/offset return everything (matches MVP behavior);
    the {items, total} wrapper is the one breaking change vs MVP's bare list[GrammarOut].
    """
    stmt = select(Grammar).join(GrammarProgress, GrammarProgress.grammar_id == Grammar.id, isouter=True)
    count_stmt = select(func.count()).select_from(Grammar).join(
        GrammarProgress, GrammarProgress.grammar_id == Grammar.id, isouter=True
    )

    if q:
        pattern = f"%{q}%"
        search_clause = or_(
            Grammar.expression_clean.ilike(pattern),
            Grammar.reading.ilike(pattern),
            Grammar.meaning_ru.ilike(pattern),
            Grammar.pattern_text.ilike(pattern),
        )
        stmt = stmt.where(search_clause)
        count_stmt = count_stmt.where(search_clause)

    if status:
        stmt = stmt.where(GrammarProgress.status == status)
        count_stmt = count_stmt.where(GrammarProgress.status == status)

    if tag:
        # No-op per ARCHITECTURE.md V2.6 open items: all tags are empty on this deck (ADR-4).
        # Kept as a real filter (not silently ignored) so it's forward-compatible once tags
        # get populated — `tags @> ARRAY[tag]` matches nothing today by construction.
        stmt = stmt.where(Grammar.tags.contains([tag]))
        count_stmt = count_stmt.where(Grammar.tags.contains([tag]))

    total = db.scalar(count_stmt) or 0
    rows = db.scalars(stmt.order_by(Grammar.source_note_id).limit(limit).offset(offset)).all()

    items = [to_progress_out(grammar, grammar.progress) for grammar in rows]
    return GrammarListOut(items=items, total=int(total))


@router.get("/relations", response_model=list[GrammarRelationEdgeOut])
@beartype
def list_all_relations(db: Session = Depends(get_db)) -> list[GrammarRelationEdgeOut]:
    """GET /grammar/relations — bulk edge list for the graph view. See ARCHITECTURE.md V2.3.

    NOTE: this route is registered before /{grammar_id} so "relations" isn't swallowed as a
    uuid path param.
    """
    return fetch_all_edges(db)


@router.get("/{grammar_id}", response_model=GrammarDetailOut)
@beartype
def get_grammar(grammar_id: uuid.UUID, db: Session = Depends(get_db)) -> GrammarDetailOut:
    """GET /grammar/{id} — single item detail, with progress + relations embedded.
    See ARCHITECTURE.md V2.3.
    """
    grammar = db.get(Grammar, grammar_id)
    if grammar is None:
        raise HTTPException(status_code=404, detail="Grammar item not found")
    progress_out = to_progress_out(grammar, grammar.progress)
    relations = fetch_relations_for(db, grammar_id)
    return GrammarDetailOut(**progress_out.model_dump(), relations=relations)


@router.get("/{grammar_id}/relations", response_model=list[GrammarRelationOut])
@beartype
def get_grammar_relations(grammar_id: uuid.UUID, db: Session = Depends(get_db)) -> list[GrammarRelationOut]:
    """GET /grammar/{id}/relations — standalone relations-only fetch. See ARCHITECTURE.md V2.3."""
    grammar = db.get(Grammar, grammar_id)
    if grammar is None:
        raise HTTPException(status_code=404, detail="Grammar item not found")
    return fetch_relations_for(db, grammar_id)
