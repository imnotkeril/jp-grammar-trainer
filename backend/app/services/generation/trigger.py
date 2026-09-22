from __future__ import annotations

import uuid

from beartype import beartype
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.grammar import Grammar
from app.models.question import Question, QuestionSource, ValidationStatus
from app.services.generation.factory import get_provider
from app.services.generation.prompts import PROMPT_VERSION
from app.services.generation.provider import build_prompt
from app.services.generation.validate import dedup_hash, validate_generated_sentence


@beartype
def count_unused_valid_questions(db: Session, grammar_id: uuid.UUID) -> int:
    """"Unused" = never served, per ARCHITECTURE.md §7.1 (MVP interpretation)."""
    stmt = select(func.count()).select_from(Question).where(
        Question.grammar_id == grammar_id,
        Question.validation_status == ValidationStatus.VALID,
        Question.used_count == 0,
    )
    return db.execute(stmt).scalar_one()


@beartype
def needs_generation(db: Session, grammar_id: uuid.UUID) -> bool:
    return count_unused_valid_questions(db, grammar_id) < settings.generation_shortage_threshold


@beartype
async def generate_batch_for_grammar(db: Session, grammar_id: uuid.UUID) -> int:
    """Generate + validate + persist a batch of new questions for one grammar item.

    Intended to run as a FastAPI BackgroundTasks callback after POST /review/session
    responds — see ARCHITECTURE.md §7.1. Returns the number of valid questions inserted.
    """
    grammar = db.get(Grammar, grammar_id)
    if grammar is None:
        raise ValueError(f"Grammar {grammar_id} not found")

    existing_sentences = [
        q.sentence_full_html for q in db.scalars(select(Question).where(Question.grammar_id == grammar_id))
    ]
    formation_rules = [rule.get("example_html", "") for rule in grammar.formation_rules]

    prompt = build_prompt(
        pattern_text=grammar.pattern_text,
        target_construction=grammar.target_construction,
        formation_rules=formation_rules,
        existing_example_clean=grammar.expression_clean,
        existing_sentences=existing_sentences,
        batch_size=settings.generation_batch_size,
    )

    provider = get_provider()
    raw_sentences = await provider.generate_sentences(prompt)

    inserted = 0
    for raw in raw_sentences:
        is_valid = validate_generated_sentence(raw, grammar.target_construction)
        question = Question(
            grammar_id=grammar_id,
            sentence_with_blank_html=raw.sentence_with_blank_html,
            sentence_full_html=raw.sentence_full_html,
            options=[],  # populated by distractors.py at serve time (§7.5), left empty here
            correct_option="A",
            explanation_ru=raw.explanation_ru,
            source=QuestionSource.AI_GENERATED,
            generation_model=provider.model_name,
            generation_prompt_version=PROMPT_VERSION,
            validation_status=ValidationStatus.VALID if is_valid else ValidationStatus.REJECTED,
            dedup_hash=dedup_hash(raw.sentence_full_html),
        )
        db.add(question)
        try:
            db.flush()  # surfaces the unique (grammar_id, dedup_hash) violation immediately
            if is_valid:
                inserted += 1
        except Exception:  # noqa: BLE001 — duplicate sentence, skip per §7.4 step 3
            db.rollback()

    db.commit()
    return inserted
