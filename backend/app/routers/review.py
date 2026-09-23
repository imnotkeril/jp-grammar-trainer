from __future__ import annotations

from datetime import datetime, timezone

from beartype import beartype
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress
from app.models.question import Question
from app.models.question_attempt import QuestionAttempt
from app.schemas.review import (
    AnswerRequest,
    AnswerResponse,
    QuestionOption,
    QuestionOut,
    SessionRequest,
    SessionResponse,
)
from app.services.generation.trigger import generate_batch_for_grammar_background, needs_generation
from app.services.review import (
    apply_answer,
    build_explanation_ru,
    classify_error_type,
    select_confusion_progress,
    select_due_progress_mixed,
    select_weak_progress,
    serve_question_for_grammar,
)
from app.services.vocabulary import known_surface_forms, record_exposures

router = APIRouter(prefix="/review", tags=["review"])


@router.post("/session", response_model=SessionResponse)
@beartype
async def start_session(
    request: SessionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> SessionResponse:
    """POST /review/session — see ARCHITECTURE.md §8/§9 task 2.4.

    Selects up to `size` grammar items — via the ordinary due queue (mode="due", with a
    weak-point mix-in per ADR-17), Confusion Practice (mode="confusion"), or Weak Points
    (mode="weak_points") — serves one valid question per item, and — for every selected item
    below the unused-question shortage threshold — schedules a background batch generation
    so the *next* session has fresh material (ARCHITECTURE.md §7.1, ADR-2: fire-and-forget
    BackgroundTasks, no job queue). See ARCHITECTURE.md V3.3 for the mode dispatch.
    """
    now = datetime.now(timezone.utc)
    if request.mode == "confusion":
        selected_progress = select_confusion_progress(db, request.size, level=request.level)
    elif request.mode == "weak_points":
        selected_progress = select_weak_progress(db, request.size, level=request.level)
    else:
        selected_progress = select_due_progress_mixed(db, request.size, now, level=request.level)

    questions_out: list[QuestionOut] = []
    for progress in selected_progress:
        if needs_generation(db, progress.grammar_id):
            background_tasks.add_task(generate_batch_for_grammar_background, progress.grammar_id)

        question = serve_question_for_grammar(db, progress.grammar_id)
        if question is None:
            # No valid question exists yet for this due item (generation hasn't landed) —
            # skip it this round rather than serve a broken question; it stays due and will
            # be picked up again once the background batch above (or a prior one) lands.
            continue

        questions_out.append(
            QuestionOut(
                id=question.id,
                grammar_id=question.grammar_id,
                sentence_with_blank_html=question.sentence_with_blank_html,
                options=[QuestionOption(**opt) for opt in question.options],
            )
        )

    known_words = sorted(known_surface_forms(db))

    db.commit()
    return SessionResponse(questions=questions_out, known_words=known_words)


@router.post("/answer", response_model=AnswerResponse)
@beartype
async def submit_answer(
    request: AnswerRequest,
    db: Session = Depends(get_db),
) -> AnswerResponse:
    """POST /review/answer — see ARCHITECTURE.md §8/§9 task 2.5.

    Persists the QuestionAttempt (with a best-effort error_type classification, SPEC idea-doc
    §29), runs the SRS scheduler to update grammar_progress, and returns a contrastive
    explanation (SPEC.md §14) alongside the updated next_review.
    """
    question = db.get(Question, request.question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")

    progress = db.get(GrammarProgress, question.grammar_id)
    if progress is None:
        # Shouldn't happen — every Grammar row gets a GrammarProgress row at seed-import
        # time (ARCHITECTURE.md ADR-5). Fail loudly rather than silently skip SRS scheduling.
        raise HTTPException(status_code=500, detail="Grammar progress record missing for this question")

    grammar = db.get(Grammar, question.grammar_id)
    if grammar is None:
        raise HTTPException(status_code=500, detail="Grammar record missing for this question")

    is_correct = request.selected_option == question.correct_option
    error_type = None if is_correct else classify_error_type(db, question, request.selected_option)

    db.add(
        QuestionAttempt(
            question_id=question.id,
            grammar_id=question.grammar_id,
            selected_option=request.selected_option,
            correct_option=question.correct_option,
            is_correct=is_correct,
            response_time_ms=request.response_time_ms,
            error_type=error_type,
        )
    )

    now = datetime.now(timezone.utc)
    apply_answer(db, progress, is_correct, now)
    record_exposures(db, question.sentence_full_html, is_correct, now)

    explanation_ru = build_explanation_ru(question, grammar, request.selected_option)

    db.commit()

    return AnswerResponse(
        is_correct=is_correct,
        correct_option=question.correct_option,
        explanation_ru=explanation_ru,
        sentence_full_html=question.sentence_full_html,
        next_review=progress.next_review,
    )
