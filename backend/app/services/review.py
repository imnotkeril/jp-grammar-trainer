from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from beartype import beartype
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, aliased

from app.config import settings
from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress, GrammarStatus
from app.models.grammar_relation import GrammarRelation, RelationType
from app.models.question import Question, QuestionSource, ValidationStatus
from app.services.srs import GrammarProgressState, rolling_accuracy, schedule_next

# SPEC.md (idea doc) §29 error taxonomy. MVP uses a best-effort heuristic (no grammar-graph
# / confusion-set data on MVP, per ARCHITECTURE.md §11) rather than the full classifier.
ERROR_TYPE_SIMILAR_GRAMMAR_CONFUSION = "similar_grammar_confusion"
ERROR_TYPE_CONFUSION = "confusion"


@beartype
def select_due_progress(
    db: Session, size: int, now: datetime | None = None, level: str | None = None
) -> list[GrammarProgress]:
    """Select up to `size` due grammar_progress rows, overdue-first then new.

    "Due" = next_review <= now (ARCHITECTURE.md §8). Ordering: non-new (overdue) items first,
    most-overdue (smallest next_review) first within that group; new items (next_review set
    to their creation time, per ADR-5/seed_import) come after, in the same next_review order.
    See ARCHITECTURE.md §9 task 2.4.

    `level` (ARCHITECTURE.md V4 slice §V4.4) is an optional additional filter on
    `Grammar.level` — omitted/None spans all levels together, unchanged behavior.
    """
    now = now or datetime.now(timezone.utc)
    is_new_last = case((GrammarProgress.status == GrammarStatus.NEW, 1), else_=0)
    stmt = select(GrammarProgress).where(GrammarProgress.next_review <= now)
    if level is not None:
        stmt = stmt.join(Grammar, Grammar.id == GrammarProgress.grammar_id).where(Grammar.level == level)
    stmt = stmt.order_by(is_new_last, GrammarProgress.next_review.asc()).limit(size)
    return list(db.scalars(stmt))


# Both types per the architect's ADR: the no-API-key heuristic fallback in
# generate_relations.py never emits commonly_confused, only similar_form/similar_meaning/
# related — restricting to commonly_confused alone would make Confusion Practice return
# nothing at all on a DB that hasn't run real LLM classification yet (ARCHITECTURE.md V3.3).
CONFUSION_RELATION_TYPES: frozenset[RelationType] = frozenset(
    {RelationType.COMMONLY_CONFUSED, RelationType.SIMILAR_FORM}
)


@beartype
def family_member_ids(db: Session, anchor_id: uuid.UUID) -> frozenset[uuid.UUID]:
    """The relation "family" containing `anchor_id`: its connected component over *every*
    grammar_relation edge, treated as undirected. Mirrors the frontend's
    `computeRelationClusters` (the "Группы похожих конструкций" cards on /grammar), so a
    cluster card and the practice session it launches always cover the same items.

    Returns an empty set when `anchor_id` has no edges at all — a lone item is not a family.
    """
    adjacency: dict[uuid.UUID, set[uuid.UUID]] = {}
    for a, b in db.execute(select(GrammarRelation.grammar_id, GrammarRelation.related_grammar_id)).all():
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    if anchor_id not in adjacency:
        return frozenset()
    seen = {anchor_id}
    stack = [anchor_id]
    while stack:
        for neighbor in adjacency[stack.pop()]:
            if neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return frozenset(seen)


@beartype
def select_confusion_progress(
    db: Session, size: int, level: str | None = None, family_of: uuid.UUID | None = None
) -> list[GrammarProgress]:
    """Confusion Practice (idea doc §15, ARCHITECTURE.md V3.3): up to `size` grammar items
    drawn only from items connected by a commonly_confused/similar_form edge, ranked by their
    strongest qualifying edge. Ignores due-ness entirely — may return fewer than `size` items
    (or none) if too few/no qualifying edges exist yet.

    `level` (ARCHITECTURE.md V4 slice §V4.4): when set, only edges where BOTH sides belong to
    that level are considered, and the ranked ids are narrowed to that level.

    `family_of` (roadmap: family-scoped confusion practice): when set, the session is limited
    to the relation family containing that grammar id (see `family_member_ids`) instead of
    pooling every confusable item. All family members are eligible — a member linked only by
    a non-confusion edge (e.g. similar_meaning) still belongs to the group the learner clicked
    — but those with a confusion edge are ranked first, strongest edge first. A "family" of
    fewer than 2 items yields no session.
    """
    family: frozenset[uuid.UUID] | None = None
    if family_of is not None:
        family = family_member_ids(db, family_of)
        if len(family) < 2:
            return []

    stmt = select(
        GrammarRelation.grammar_id, GrammarRelation.related_grammar_id, GrammarRelation.strength
    ).where(GrammarRelation.relation_type.in_(CONFUSION_RELATION_TYPES))

    if level is not None:
        grammar_a = aliased(Grammar)
        grammar_b = aliased(Grammar)
        stmt = (
            stmt.join(grammar_a, grammar_a.id == GrammarRelation.grammar_id)
            .join(grammar_b, grammar_b.id == GrammarRelation.related_grammar_id)
            .where(grammar_a.level == level, grammar_b.level == level)
        )

    best_strength: dict[uuid.UUID, float] = {}
    for grammar_id, related_grammar_id, strength in db.execute(stmt).all():
        for gid in (grammar_id, related_grammar_id):
            if strength > best_strength.get(gid, -1.0):
                best_strength[gid] = strength

    if family is not None:
        ranked = {gid: best_strength.get(gid, -1.0) for gid in family}
        if level is not None:
            in_level = set(db.scalars(select(Grammar.id).where(Grammar.id.in_(family), Grammar.level == level)))
            ranked = {gid: strength for gid, strength in ranked.items() if gid in in_level}
    else:
        ranked = best_strength

    if not ranked:
        return []

    ordered_ids = [gid for gid, _ in sorted(ranked.items(), key=lambda kv: kv[1], reverse=True)][:size]

    progress_by_id = {
        p.grammar_id: p
        for p in db.scalars(select(GrammarProgress).where(GrammarProgress.grammar_id.in_(ordered_ids)))
    }
    return [progress_by_id[gid] for gid in ordered_ids if gid in progress_by_id]


@beartype
def select_weak_progress(
    db: Session,
    size: int,
    exclude_ids: frozenset[uuid.UUID] = frozenset(),
    level: str | None = None,
) -> list[GrammarProgress]:
    """Weak Points (idea doc §28/§37, ARCHITECTURE.md V3.3): the `size` worst-performing
    already-attempted grammar items, ranked by (application_score + discrimination_score)
    ascending. Never-attempted (`repetitions == 0`) items are excluded — weakness must be
    demonstrated, not assumed from a default score.

    Both scores are real, apply_answer-computed EMAs as of this fix (see apply_answer /
    is_application_informative / is_discrimination_informative in this module) — an item with
    no informative attempts yet for one or both dimensions simply keeps that dimension's
    neutral 0.5 default (grammar_progress.py) rather than a misleading confirmed-bad 0.0.

    `level` (ARCHITECTURE.md V4 slice §V4.4): optional additional filter on `Grammar.level`.
    """
    if size <= 0:
        return []
    stmt = select(GrammarProgress).where(GrammarProgress.repetitions > 0)
    if exclude_ids:
        stmt = stmt.where(GrammarProgress.grammar_id.not_in(exclude_ids))
    if level is not None:
        stmt = stmt.join(Grammar, Grammar.id == GrammarProgress.grammar_id).where(Grammar.level == level)
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
    level: str | None = None,
) -> list[GrammarProgress]:
    """Default `due` mode with a weak-point mix-in (ARCHITECTURE.md V3.3, ADR-17): reserves
    `round(size * weak_ratio)` slots (only when size >= 5) for the weakest already-attempted
    items, filling the rest from the ordinary due queue. Tops back up from due items if too
    few weak-eligible items exist to fill the reserved slots.

    `level` (ARCHITECTURE.md V4 slice §V4.4): optional additional filter threaded through to
    both the due queue and the weak-point mix-in — `None` (default) pools all levels together
    exactly as before.
    """
    now = now or datetime.now(timezone.utc)
    # ADR-17: reserving even one slot out of a 5-question session would over-weight it
    # relative to the 20%-of-10 intent, so only size > 5 (10/20) gets a mix-in.
    weak_slots = round(size * weak_ratio) if size > 5 else 0

    due_items = select_due_progress(db, size - weak_slots, now, level=level)
    weak_items = select_weak_progress(
        db, weak_slots, exclude_ids=frozenset(p.grammar_id for p in due_items), level=level
    )
    combined = due_items + weak_items

    if len(combined) < size:
        seen = {p.grammar_id for p in combined}
        topped_up = [p for p in select_due_progress(db, size, now, level=level) if p.grammar_id not in seen]
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
def is_application_informative(question: Question) -> bool:
    """True when this question tests applying the grammar in a *fresh* context rather than a
    fixed, drillable one the learner might just pattern-match against — SPEC.md idea doc §28's
    "application" skill dimension. Operationalized as `source == "ai_generated"` (a genuinely
    novel sentence) vs `source == "seed"` (the one fixed sentence per grammar item imported
    from the Anki export, ARCHITECTURE.md §7.4).
    """
    return question.source == QuestionSource.AI_GENERATED


@beartype
def is_discrimination_informative(question: Question) -> bool:
    """True when this question tests distinguishing the grammar point from something it's
    commonly confused with — SPEC.md idea doc §28's "discrimination" skill dimension.
    Operationalized as `has_confusion_distractor` (set at generation/seed time, see
    question.py): at least one of the 3 served distractors was drawn from a real
    commonly_confused/similar_form `grammar_relation` edge (ARCHITECTURE.md V3.5) rather than
    the uniform-random fallback pool, so getting it wrong plausibly means confusing this item
    with a real confusable partner rather than just not knowing any answer.
    """
    return question.has_confusion_distractor


@beartype
def apply_answer(
    db: Session,
    progress: GrammarProgress,
    question: Question,
    is_correct: bool,
    now: datetime | None = None,
) -> GrammarProgressState:
    """Run SRS scheduling for one answer and write the result back onto `progress`.

    See ARCHITECTURE.md §6 (schedule_next) and §9 task 2.5. Also updates
    application_score/discrimination_score (real signals as of this fix, previously
    dead/always-0.0 columns) — each is only nudged by `rolling_accuracy` (the same EMA used
    for recall_score) on an "informative" attempt for that dimension (see
    is_application_informative/is_discrimination_informative above); a non-informative attempt
    leaves that score untouched, so an item with no AI-generated questions served yet (no API
    key configured, e.g.) simply keeps its neutral 0.5 default (grammar_progress.py) instead of
    drifting toward a misleading value from unrelated attempts.
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

    if is_application_informative(question):
        progress.application_score = rolling_accuracy(progress.application_score, is_correct)
    if is_discrimination_informative(question):
        progress.discrimination_score = rolling_accuracy(progress.discrimination_score, is_correct)

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
    total_items: int


@beartype
def compute_stats(db: Session, now: datetime | None = None, level: str | None = None) -> ReviewStats:
    """Aggregate dashboard stats per SPEC.md §27/§8 and ARCHITECTURE.md §9 task 2.6.

    `level` (ARCHITECTURE.md V4 slice §V4.4, ADR-23): optional filter scoping every count to
    that level's `grammar_progress` rows only. `None` (default) = combined stats across all
    levels, unchanged existing behavior.
    """
    now = now or datetime.now(timezone.utc)

    due_stmt = select(func.count()).select_from(GrammarProgress).where(GrammarProgress.next_review <= now)
    if level is not None:
        due_stmt = due_stmt.join(Grammar, Grammar.id == GrammarProgress.grammar_id).where(Grammar.level == level)
    due_count = db.execute(due_stmt).scalar_one()

    status_stmt = select(GrammarProgress.status, func.count())
    if level is not None:
        status_stmt = status_stmt.join(Grammar, Grammar.id == GrammarProgress.grammar_id).where(
            Grammar.level == level
        )
    status_counts: dict[GrammarStatus, int] = {
        status: count for status, count in db.execute(status_stmt.group_by(GrammarProgress.status)).all()
    }

    agg_stmt = select(
        func.coalesce(func.avg(GrammarProgress.recall_score), 0.0),
        func.coalesce(func.avg(GrammarProgress.application_score), 0.0),
        func.coalesce(func.avg(GrammarProgress.discrimination_score), 0.0),
    )
    if level is not None:
        agg_stmt = agg_stmt.join(Grammar, Grammar.id == GrammarProgress.grammar_id).where(Grammar.level == level)
    recall_avg, application_avg, discrimination_avg = db.execute(agg_stmt).one()

    total_items_stmt = select(func.count()).select_from(Grammar)
    if level is not None:
        total_items_stmt = total_items_stmt.where(Grammar.level == level)
    total_items = db.execute(total_items_stmt).scalar_one()

    return ReviewStats(
        due_count=int(due_count),
        new_count=int(status_counts.get(GrammarStatus.NEW, 0)),
        learning_count=int(status_counts.get(GrammarStatus.LEARNING, 0)),
        review_count=int(status_counts.get(GrammarStatus.REVIEW, 0)),
        mastered_count=int(status_counts.get(GrammarStatus.MASTERED, 0)),
        recall_pct=round(float(recall_avg) * 100, 1),
        application_avg=round(float(application_avg), 3),
        discrimination_avg=round(float(discrimination_avg), 3),
        total_items=int(total_items),
    )
