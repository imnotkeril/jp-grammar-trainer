from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.grammar_progress import GrammarStatus
from app.services.srs import (
    FIXED_INTERVALS_DAYS,
    GrammarProgressState,
    derive_status,
    rolling_accuracy,
    schedule_next,
)

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _fresh_state() -> GrammarProgressState:
    return GrammarProgressState(
        status=GrammarStatus.NEW,
        interval_step=0,
        interval_days=0,
        repetitions=0,
        lapses=0,
        recall_score=0.0,
        last_reviewed=None,
        next_review=NOW,
    )


def test_correct_streak_advances_interval_steps() -> None:
    state = _fresh_state()
    for _ in range(len(FIXED_INTERVALS_DAYS) - 1):
        state = schedule_next(state, is_correct=True, now=NOW)
    assert state.interval_step == len(FIXED_INTERVALS_DAYS) - 1
    assert state.status == GrammarStatus.MASTERED
    assert state.interval_days == FIXED_INTERVALS_DAYS[-1]


def test_correct_streak_never_exceeds_max_step() -> None:
    state = _fresh_state()
    for _ in range(len(FIXED_INTERVALS_DAYS) + 5):
        state = schedule_next(state, is_correct=True, now=NOW)
    assert state.interval_step == len(FIXED_INTERVALS_DAYS) - 1


def test_error_drops_two_steps_not_full_reset() -> None:
    state = _fresh_state()
    for _ in range(5):  # advance to interval_step 5
        state = schedule_next(state, is_correct=True, now=NOW)
    assert state.interval_step == 5

    state = schedule_next(state, is_correct=False, now=NOW)
    assert state.interval_step == 3  # 5 - 2, not reset to 0
    assert state.repetitions == 0
    assert state.lapses == 1


def test_error_step_floors_at_zero() -> None:
    state = _fresh_state()
    state = schedule_next(state, is_correct=False, now=NOW)
    assert state.interval_step == 0
    assert state.interval_days == 0


def test_derive_status_table() -> None:
    assert derive_status(interval_step=0, repetitions=0, lapses=0) == GrammarStatus.NEW
    assert derive_status(interval_step=0, repetitions=0, lapses=1) == GrammarStatus.LEARNING
    assert derive_status(interval_step=1, repetitions=1, lapses=0) == GrammarStatus.LEARNING
    assert derive_status(interval_step=2, repetitions=2, lapses=0) == GrammarStatus.REVIEW
    assert derive_status(interval_step=len(FIXED_INTERVALS_DAYS) - 1, repetitions=7, lapses=0) == GrammarStatus.MASTERED


def test_next_review_date_matches_interval() -> None:
    state = _fresh_state()
    state = schedule_next(state, is_correct=True, now=NOW)
    assert state.interval_days == FIXED_INTERVALS_DAYS[1]
    assert (state.next_review - NOW).days == FIXED_INTERVALS_DAYS[1]


def test_rolling_accuracy_moves_toward_correct() -> None:
    # reused (per SPEC.md idea doc §28) by application_score/discrimination_score, starting
    # from their neutral 0.5 default rather than recall_score's 0.0 — verify the EMA math
    # itself is default-agnostic.
    assert rolling_accuracy(0.5, is_correct=True) == pytest.approx(0.6)


def test_rolling_accuracy_moves_toward_incorrect() -> None:
    assert rolling_accuracy(0.5, is_correct=False) == pytest.approx(0.4)


def test_rolling_accuracy_custom_alpha() -> None:
    assert rolling_accuracy(0.0, is_correct=True, alpha=0.5) == pytest.approx(0.5)


def test_rolling_accuracy_converges_with_repeated_correct_answers() -> None:
    value = 0.5
    for _ in range(50):
        value = rolling_accuracy(value, is_correct=True)
    assert value == pytest.approx(1.0, abs=1e-3)
