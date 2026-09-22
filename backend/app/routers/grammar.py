from __future__ import annotations

import uuid

from beartype import beartype
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.grammar import Grammar
from app.schemas.grammar import GrammarOut

router = APIRouter(prefix="/grammar", tags=["grammar"])


@router.get("", response_model=list[GrammarOut])
@beartype
def list_grammar(db: Session = Depends(get_db)) -> list[Grammar]:
    """GET /grammar — list all seeded N3 grammar items. See ARCHITECTURE.md §8."""
    return list(db.scalars(select(Grammar).order_by(Grammar.source_note_id)))


@router.get("/{grammar_id}", response_model=GrammarOut)
@beartype
def get_grammar(grammar_id: uuid.UUID, db: Session = Depends(get_db)) -> Grammar:
    """GET /grammar/{id} — single item detail. See ARCHITECTURE.md §8."""
    grammar = db.get(Grammar, grammar_id)
    if grammar is None:
        raise HTTPException(status_code=404, detail="Grammar item not found")
    return grammar
