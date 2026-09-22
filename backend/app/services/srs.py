from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from beartype import beartype

from app.models.grammar_progress import GrammarStatus

# Fixed SRS intervals in days. Index = interval_step. See ARCHITECTURE.md §6.
FIXED_INTERVALS_DAYS: list[int] = [0, 1, 3, 7, 14, 30, 60, 120]

# On a wrong answer, drop back this many steps (floor at 0) rather than a hard reset.
# See ARCHITECTURE.md ADR-8 for rationale.
ERROR_STEP_PENALTY: int = 2

# Weight for the rolling-accuracy exponential moving average (recall_score).
RECALL_EMA_ALPHA: float = 0.2


@dataclass(frozen=True, slots=True)
class GrammarProgressState:
    """Pure-data snapshot of a grammar_progress row, decoupled from the ORM."""

    status: GrammarStatus
    interval_step: int
    interval_days: int
    repetitions: int
    lapses: int
    recall_score: float
    last_reviewed: datetime | None
    next_review: datetime


@beartype
def derive_status(interval_step: int, repetitions: int, lapses: int) -> GrammarStatus:
    """Derive the display status from interval progression, never stored independently."""
    if repetitions == 0 and interval_step == 0:
        return GrammarStatus.NEW if lapses == 0 else GrammarStatus.LEARNING
    if interval_step <= 1:
        return GrammarStatus.LEARNING
    if interval_step < len(FIXED_INTERVALS_DAYS) - 1:
        return GrammarStatus.REVIEW
    return GrammarStatus.MASTERED


@beartype
def rolling_accuracy(prev: float, is_correct: bool, alpha: float = RECALL_EMA_ALPHA) -> float:
    """Exponential moving average, cheap proxy for recall_score. alpha=0.2 ~ last ~5 attempts."""
    return prev + alpha * ((1.0 if is_correct else 0.0) - prev)


@beartype
def schedule_next(
    progress: GrammarProgressState,
    is_correct: bool,
    now: datetime,
) -> GrammarProgressState:
    """Pure function: current progress + attempt result -> new progress state.

    See ARCHITECTURE.md §6 for the full algorithm and ADR-8 for the error-penalty rationale.
    """
    if is_correct:
        next_step = min(progress.interval_step + 1, len(FIXED_INTERVALS_DAYS) - 1)
        repetitions = progress.repetitions + 1
        lapses = progress.lapses
    else:
        next_step = max(progress.interval_step - ERROR_STEP_PENALTY, 0)
        repetitions = 0
        lapses = progress.lapses + 1

    interval_days = FIXED_INTERVALS_DAYS[next_step]
    status = derive_status(next_step, repetitions, lapses)

    return replace(
        progress,
        status=status,
        interval_step=next_step,
        interval_days=interval_days,
        repetitions=repetitions,
        lapses=lapses,
        last_reviewed=now,
        next_review=now + timedelta(days=interval_days),
        recall_score=rolling_accuracy(progress.recall_score, is_correct),
    )
