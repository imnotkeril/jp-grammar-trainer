from __future__ import annotations

import logging
import random
import uuid

from beartype import beartype
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.grammar import Grammar
from app.models.grammar_relation import GrammarRelation
from app.models.question import Question, QuestionSource, ValidationStatus
from app.services.distractors import pick_distractors
from app.services.generation.factory import get_provider
from app.services.generation.prompts import PROMPT_VERSION
from app.services.generation.provider import GenerationPrompt, RawGeneratedSentence, build_prompt
from app.services.generation.validate import dedup_hash, validate_generated_sentence
from app.services.review import CONFUSION_RELATION_TYPES

logger = logging.getLogger(__name__)

_OPTION_KEYS = ("A", "B", "C", "D")


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
def _fetch_distractor_candidates(db: Session, exclude_grammar_id: uuid.UUID) -> list[tuple[uuid.UUID, str]]:
    """Other grammar items' target_construction, usable as distractor text (§7.5).

    Excludes rows with an empty target_construction (ADR-6b: 3/205 seed rows have none) —
    pick_distractors already excludes the correct grammar item and literal-duplicate text.
    """
    stmt = select(Grammar.id, Grammar.target_construction).where(
        Grammar.id != exclude_grammar_id,
        Grammar.target_construction != "",
    )
    return [(gid, text) for gid, text in db.execute(stmt).all()]


@beartype
def _fetch_confused_texts(db: Session, grammar_id: uuid.UUID) -> list[tuple[str, str, float]]:
    """Every grammar item connected to `grammar_id` via a commonly_confused/similar_form
    edge, as (target_construction, meaning_ru, strength) — used both to bias distractor
    selection and (top 2 by strength) to nudge the generation prompt. See ARCHITECTURE.md
    V3.5. One indexed query each direction, same pattern as _fetch_distractor_candidates.
    """
    stmt_from = (
        select(Grammar.target_construction, Grammar.meaning_ru, GrammarRelation.strength)
        .join(GrammarRelation, GrammarRelation.related_grammar_id == Grammar.id)
        .where(
            GrammarRelation.grammar_id == grammar_id,
            GrammarRelation.relation_type.in_(CONFUSION_RELATION_TYPES),
        )
    )
    stmt_to = (
        select(Grammar.target_construction, Grammar.meaning_ru, GrammarRelation.strength)
        .join(GrammarRelation, GrammarRelation.grammar_id == Grammar.id)
        .where(
            GrammarRelation.related_grammar_id == grammar_id,
            GrammarRelation.relation_type.in_(CONFUSION_RELATION_TYPES),
        )
    )
    rows = [*db.execute(stmt_from).all(), *db.execute(stmt_to).all()]
    return [(text, meaning, strength) for text, meaning, strength in rows if text]


@beartype
def _build_options(
    grammar_id: uuid.UUID,
    correct_answer_text: str,
    candidates: list[tuple[uuid.UUID, str]],
    rng: random.Random,
    preferred: list[str] | None = None,
) -> tuple[list[dict[str, str]], str, bool] | None:
    """Build shuffled A-D options for a generated sentence, per ARCHITECTURE.md §7.5.

    Returns None when there aren't enough distractor candidates to build a real 4-choice
    question (too few grammar items seeded) — caller should treat that as invalid. The third
    element of the returned tuple (`has_confusion_distractor`) is True iff at least one of the
    3 served distractors came from the `preferred` pool (a real commonly_confused/similar_form
    grammar_relation edge) rather than the uniform-random fallback pool — see question.py's
    `has_confusion_distractor` field and services/review.py's discrimination_score scoring.
    """
    try:
        distractor_texts = pick_distractors(
            grammar_id, correct_answer_text, candidates, count=3, rng=rng, preferred=preferred
        )
    except ValueError:
        return None

    preferred_set = {t.strip() for t in (preferred or [])}
    has_confusion_distractor = any(t in preferred_set for t in distractor_texts)

    texts = [correct_answer_text, *distractor_texts]
    rng.shuffle(texts)
    options = [{"key": key, "text": text} for key, text in zip(_OPTION_KEYS, texts, strict=True)]
    correct_option = next(opt["key"] for opt in options if opt["text"] == correct_answer_text)
    return options, correct_option, has_confusion_distractor


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

    confused = _fetch_confused_texts(db, grammar_id)
    confused_top2 = [
        {"target_construction": text, "meaning_ru": meaning}
        for text, meaning, _strength in sorted(confused, key=lambda c: c[2], reverse=True)[:2]
    ]

    prompt: GenerationPrompt = build_prompt(
        pattern_text=grammar.pattern_text,
        target_construction=grammar.target_construction,
        formation_rules=formation_rules,
        existing_example_clean=grammar.expression_clean,
        existing_sentences=existing_sentences,
        batch_size=settings.generation_batch_size,
        confusable_with=confused_top2,
    )

    provider = get_provider()
    raw_sentences: list[RawGeneratedSentence] = await provider.generate_sentences(prompt)

    candidates = _fetch_distractor_candidates(db, grammar_id)
    preferred = [text for text, _meaning, _strength in confused]
    rng = random.Random()

    inserted = 0
    for raw in raw_sentences:
        is_valid = validate_generated_sentence(raw, grammar.target_construction)
        options: list[dict[str, str]] = []
        correct_option = "A"
        has_confusion_distractor = False
        if is_valid:
            built = _build_options(grammar_id, raw.correct_answer_text, candidates, rng, preferred=preferred)
            if built is None:
                # Not enough distractor candidates to serve a real 4-choice question —
                # reject rather than serve a broken question with < 4 options.
                is_valid = False
            else:
                options, correct_option, has_confusion_distractor = built

        question = Question(
            grammar_id=grammar_id,
            sentence_with_blank_html=raw.sentence_with_blank_html,
            sentence_full_html=raw.sentence_full_html,
            options=options,
            correct_option=correct_option,
            explanation_ru=raw.explanation_ru,
            source=QuestionSource.AI_GENERATED,
            generation_model=provider.model_name,
            generation_prompt_version=PROMPT_VERSION,
            validation_status=ValidationStatus.VALID if is_valid else ValidationStatus.REJECTED,
            dedup_hash=dedup_hash(raw.sentence_full_html),
            has_confusion_distractor=has_confusion_distractor,
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


@beartype
async def generate_batch_for_grammar_background(grammar_id: uuid.UUID) -> None:
    """BackgroundTasks-safe entrypoint: opens its own DB session.

    The request-scoped session (`app.db.get_db`) is closed as soon as the response is sent,
    so a task scheduled via `BackgroundTasks.add_task` must not reuse it — see ARCHITECTURE.md
    ADR-2. Failures are logged and swallowed: per ADR-2, the next review-session start that
    still finds a shortage simply retries the trigger, no dedicated retry/backoff infra on MVP.
    """
    with SessionLocal() as db:
        try:
            inserted = await generate_batch_for_grammar(db, grammar_id)
            logger.info("Generated %d question(s) for grammar %s", inserted, grammar_id)
        except Exception:  # noqa: BLE001 — background task must never raise into the caller
            logger.exception("Shortage-triggered generation failed for grammar %s", grammar_id)
