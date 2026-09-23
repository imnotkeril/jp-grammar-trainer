from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from beartype import beartype
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress, GrammarStatus
from app.models.grammar_relation import GrammarRelation, RelationType
from app.models.question import Question, ValidationStatus
from app.services.srs import GrammarProgressState, schedule_next

# SPEC.md (idea doc) §29 error taxonomy. MVP uses a best-effort heuristic (no grammar-graph
# / confusion-set data on MVP, per ARCHITECTURE.md §11) rather than the full classifier.
ERROR_TYPE_SIMILAR_GRAMMAR_CONFUSION = "similar_grammar_confusion"
ERROR_TYPE_CONFUSION = "confusion"


@beartype
def select_due_progress(db: Session, size: int, now: datetime | None = None) -> list[GrammarProgress]:
    """Select up to `size` due grammar_progress rows, overdue-first then new.

    "Due" = next_review <= now (ARCHITECTURE.md §8). Ordering: non-new (overdue) items first,
    most-overdue (smallest next_review) first within that group; new items (next_review set
    to their creation time, per ADR-5/seed_import) come after, in the same next_review order.
    See ARCHITECTURE.md §9 task 2.4.
    """
    now = now or datetime.now(timezone.utc)
    is_new_last = case((GrammarProgress.status == GrammarStatus.NEW, 1), else_=0)
    stmt = (
        select(GrammarProgress)
        .where(GrammarProgress.next_review <= now)
        .order_by(is_new_last, GrammarProgress.next_review.asc())
        .limit(size)
    )
    return list(db.scalars(stmt))


# Both types per the architect's ADR: the no-API-key heuristic fallback in
# generate_relations.py never emits commonly_confused, only similar_form/similar_meaning/
# related — restricting to commonly_confused alone would make Confusion Practice return
# nothing at all on a DB that hasn't run real LLM classification yet (ARCHITECTURE.md V3.3).
CONFUSION_RELATION_TYPES: frozenset[RelationType] = frozenset(
    {RelationType.COMMONLY_CONFUSED, RelationType.SIMILAR_FORM}
)


@beartype
def select_confusion_progress(db: Session, size: int) -> list[GrammarProgress]:
    """Confusion Practice (idea doc §15, ARCHITECTURE.md V3.3): up to `size` grammar items
    drawn only from items connected by a commonly_confused/similar_form edge, ranked by their
    strongest qualifying edge. Ignores due-ness entirely — may return fewer than `size` items
    (or none) if too few/no qualifying edges exist yet.
    """
    stmt = select(
        GrammarRelation.grammar_id, GrammarRelation.related_grammar_id, GrammarRelation.strength
    ).where(GrammarRelation.relation_type.in_(CONFUSION_RELATION_TYPES))

    best_strength: dict[uuid.UUID, float] = {}
    for grammar_id, related_grammar_id, strength in db.execute(stmt).all():
        for gid in (grammar_id, related_grammar_id):
            if strength > best_strength.get(gid, -1.0):
                best_strength[gid] = strength

    if not best_strength:
        return []

    ordered_ids = [
        gid for gid, _ in sorted(best_strength.items(), key=lambda kv: kv[1], reverse=True)
    ][:size]

    progress_by_id = {
        p.grammar_id: p
        for p in db.scalars(select(GrammarProgress).where(GrammarProgress.grammar_id.in_(ordered_ids)))
    }
    return [progress_by_id[gid] for gid in ordered_ids if gid in progress_by_id]


@beartype
def select_weak_progress(
    db: Session, size: int, exclude_ids: frozenset[uuid.UUID] = frozenset()
) -> list[GrammarProgress]:
    """Weak Points (idea doc §28/§37, ARCHITECTURE.md V3.3): the `size` worst-performing
    already-attempted grammar items, ranked by (application_score + discrimination_score)
    ascending. Never-attempted (`repetitions == 0`) items are excluded — weakness must be
    demonstrated, not assumed from a default 0.0 score.
    """
    if size <= 0:
        return []
    stmt = select(GrammarProgress).where(GrammarProgress.repetitions > 0)
    if exclude_ids:
        stmt = stmt.where(GrammarProgress.grammar_id.not_in(exclude_ids))
    stmt = stmt.order_by(
        (GrammarProgress.application_score + GrammarProgress.discrimination_score).asc(),
        GrammarProgress.next_review.asc(),
    ).limit(size)
    return list(db.scalars(stmt))


@beartype
def select_due_progress_mixed(
    db: Session,
    size: int,
    now: datetime | None = None,
    weak_ratio: float = settings.weak_point_mix_ratio,
) -> list[GrammarProgress]:
    """Default `due` mode with a weak-point mix-in (ARCHITECTURE.md V3.3, ADR-17): reserves
    `round(size * weak_ratio)` slots (only when size >= 5) for the weakest already-attempted
    items, filling the rest from the ordinary due queue. Tops back up from due items if too
    few weak-eligible items exist to fill the reserved slots.
    """
    now = now or datetime.now(timezone.utc)
    # ADR-17: reserving even one slot out of a 5-question session would over-weight it
    # relative to the 20%-of-10 intent, so only size > 5 (10/20) gets a mix-in.
    weak_slots = round(size * weak_ratio) if size > 5 else 0

    due_items = select_due_progress(db, size - weak_slots, now)
    weak_items = select_weak_progress(
        db, weak_slots, exclude_ids=frozenset(p.grammar_id for p in due_items)
    )
    combined = due_items + weak_items

    if len(combined) < size:
        seen = {p.grammar_id for p in combined}
        topped_up = [p for p in select_due_progress(db, size, now) if p.grammar_id not in seen]
        combined += topped_up[: size - len(combined)]

    return combined[:size]


@beartype
def serve_question_for_grammar(db: Session, grammar_id: uuid.UUID) -> Question | None:
    """Pick one valid question to serve for `grammar_id` and mark it used.

    Prefers never-served questions (used_count == 0, the "unused" pool the shortage-trigger
    tracks, ARCHITECTURE.md §7.1); falls back to the least-recently-reused valid question if
    every valid question has already been served at least once (e.g. generation hasn't caught
    up yet). Returns None if no valid question exists yet at all.
    """
    stmt = (
        select(Question)
        .where(Question.grammar_id == grammar_id, Question.validation_status == ValidationStatus.VALID)
        .order_by(Question.used_count.asc(), Question.created_at.asc())
        .limit(1)
    )
    question = db.scalars(stmt).first()
    if question is not None:
        question.used_count += 1
    return question


@beartype
def classify_error_type(db: Session, question: Question, selected_option: str) -> str:
    """Best-effort error classification (SPEC idea-doc §29 categories).

    MVP heuristic: every distractor option is literally another grammar item's
    target_construction (ARCHITECTURE.md §7.5), so a wrong pick that matches a real grammar
    item is treated as `similar_grammar_confusion` (the learner mixed up two real
    constructions) — otherwise falls back to the generic `confusion` bucket. Full taxonomy
    (forgot_meaning/forgot_form/wrong_context/...) needs signals MVP doesn't capture yet
    (per-word vocab tracking, grammar graph) — noted as a V2 target, not built here.
    """
    selected_text = next(
        (opt["text"] for opt in question.options if opt["key"] == selected_option),
        None,
    )
    if selected_text is None:
        return ERROR_TYPE_CONFUSION
    confused_grammar = db.scalar(
        select(Grammar).where(Grammar.target_construction == selected_text, Grammar.target_construction != "")
    )
    if confused_grammar is not None:
        return ERROR_TYPE_SIMILAR_GRAMMAR_CONFUSION
    return ERROR_TYPE_CONFUSION


@beartype
def build_explanation_ru(question: Question, grammar: Grammar, selected_option: str) -> str:
    """Contrastive explanation per SPEC.md §14: correct meaning, why it fits, why the top
    plausible distractor doesn't. Templated from grammar.pattern_text/meaning_ru on MVP — no
    fresh LLM call per answer (ARCHITECTURE.md §9 task 2.5 note); AI-generated questions
    already carry a contrastive `explanation_ru` from generation time (§7.3) and that's used
    verbatim as the base when present.
    """
    base = question.explanation_ru or f"{grammar.pattern_text} {grammar.meaning_ru}".strip()
    if selected_option == question.correct_option:
        return base

    correct_text = next(
        (opt["text"] for opt in question.options if opt["key"] == question.correct_option),
        grammar.target_construction,
    )
    selected_text = next(
        (opt["text"] for opt in question.options if opt["key"] == selected_option),
        selected_option,
    )
    contrast = (
        f' «{selected_text}» здесь не подходит — в этом контексте нужна конструкция '
        f'«{correct_text}» ({grammar.pattern_text.strip()}).'
    )
    return base + contrast


@beartype
def progress_state_from_row(progress: GrammarProgress) -> GrammarProgressState:
    return GrammarProgressState(
        status=progress.status,
        interval_step=progress.interval_step,
        interval_days=progress.interval_days,
        repetitions=progress.repetitions,
        lapses=progress.lapses,
        recall_score=progress.recall_score,
        last_reviewed=progress.last_reviewed,
        next_review=progress.next_review,
    )


@beartype
def apply_answer(
    db: Session,
    progress: GrammarProgress,
    is_correct: bool,
    now: datetime | None = None,
) -> GrammarProgressState:
    """Run SRS scheduling for one answer and write the result back onto `progress`.

    See ARCHITECTURE.md §6 (schedule_next) and §9 task 2.5.
    """
    now = now or datetime.now(timezone.utc)
    state = schedule_next(progress_state_from_row(progress), is_correct, now)

    progress.status = state.status
    progress.interval_step = state.interval_step
    progress.interval_days = state.interval_days
    progress.repetitions = state.repetitions
    progress.lapses = state.lapses
    progress.recall_score = state.recall_score
    progress.last_reviewed = state.last_reviewed
    progress.next_review = state.next_review
    if progress.first_seen is None:
        progress.first_seen = now

    return state


@dataclass(frozen=True, slots=True)
class ReviewStats:
    """Pure-data dashboard aggregate. See ARCHITECTURE.md §9 task 2.6, SPEC.md §27/§8."""

    due_count: int
    new_count: int
    learning_count: int
    review_count: int
    mastered_count: int
    recall_pct: float
    application_avg: float
    discrimination_avg: float


@beartype
def compute_stats(db: Session, now: datetime | None = None) -> ReviewStats:
    """Aggregate dashboard stats per SPEC.md §27/§8 and ARCHITECTURE.md §9 task 2.6."""
    now = now or datetime.now(timezone.utc)

    due_count = db.execute(
        select(func.count()).select_from(GrammarProgress).where(GrammarProgress.next_review <= now)
    ).scalar_one()

    status_counts: dict[GrammarStatus, int] = {
        status: count
        for status, count in db.execute(
            select(GrammarProgress.status, func.count()).group_by(GrammarProgress.status)
        ).all()
    }

    recall_avg, application_avg, discrimination_avg = db.execute(
        select(
            func.coalesce(func.avg(GrammarProgress.recall_score), 0.0),
            func.coalesce(func.avg(GrammarProgress.application_score), 0.0),
            func.coalesce(func.avg(GrammarProgress.discrimination_score), 0.0),
        )
    ).one()

    return ReviewStats(
        due_count=int(due_count),
        new_count=int(status_counts.get(GrammarStatus.NEW, 0)),
        learning_count=int(status_counts.get(GrammarStatus.LEARNING, 0)),
        review_count=int(status_counts.get(GrammarStatus.REVIEW, 0)),
        mastered_count=int(status_counts.get(GrammarStatus.MASTERED, 0)),
        recall_pct=round(float(recall_avg) * 100, 1),
        application_avg=round(float(application_avg), 3),
        discrimination_avg=round(float(discrimination_avg), 3),
    )
