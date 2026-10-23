from __future__ import annotations

from beartype import beartype
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.grammar import Grammar
from app.schemas.production import (
    ProductionCheckRequest,
    ProductionCheckResponse,
    ProductionPrompt,
    ProductionSessionRequest,
    ProductionSessionResponse,
)
from app.services.production import (
    check_sentence,
    get_grammar_or_none,
    plain_text,
    select_production_grammar,
    split_pattern_text,
)

router = APIRouter(prefix="/production", tags=["production"])


@beartype
def _prompt_for(grammar: Grammar) -> ProductionPrompt:
    pattern_hint, meaning_hint = split_pattern_text(grammar.pattern_text)
    return ProductionPrompt(
        grammar_id=grammar.id,
        level=grammar.level,
        pattern_hint=plain_text(pattern_hint),
        meaning_hint=plain_text(meaning_hint),
        meaning_ru=grammar.meaning_ru,
        formation_hints=[plain_text(rule["form_label"]) for rule in grammar.formation_rules if rule.get("form_label")],
    )


@router.post("/session", response_model=ProductionSessionResponse)
@beartype
def start_production_session(
    request: ProductionSessionRequest, db: Session = Depends(get_db)
) -> ProductionSessionResponse:
    """POST /production/session — offline sentence-production prompts (no LLM, no writes)."""
    items = select_production_grammar(db, request.size, request.level)
    return ProductionSessionResponse(prompts=[_prompt_for(g) for g in items])


@router.post("/check", response_model=ProductionCheckResponse)
@beartype
def check_production(request: ProductionCheckRequest, db: Session = Depends(get_db)) -> ProductionCheckResponse:
    """POST /production/check — advisory string check + the model sentence to self-compare."""
    grammar = get_grammar_or_none(db, request.grammar_id)
    if grammar is None:
        raise HTTPException(status_code=404, detail="Grammar item not found")
    result = check_sentence(request.answer, grammar.target_construction)
    return ProductionCheckResponse(
        match=result.match,
        too_short=result.too_short,
        target_construction=grammar.target_construction,
        model_sentence_html=grammar.expression_html,
        model_sentence_clean=grammar.expression_clean,
    )
