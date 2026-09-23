from __future__ import annotations

import random
import uuid

import pytest

from app.services.distractors import pick_distractors


def _candidates(n: int) -> list[tuple[uuid.UUID, str]]:
    return [(uuid.uuid4(), f"候補{i}") for i in range(n)]


def test_pick_distractors_uniform_random_when_no_preferred() -> None:
    correct_id = uuid.uuid4()
    candidates = _candidates(5)
    chosen = pick_distractors(correct_id, "正解", candidates, count=3, rng=random.Random(1))
    assert len(chosen) == 3
    assert len(set(chosen)) == 3
    assert all(c in {text for _gid, text in candidates} for c in chosen)


def test_pick_distractors_raises_when_pool_too_small() -> None:
    correct_id = uuid.uuid4()
    candidates = _candidates(2)
    with pytest.raises(ValueError):
        pick_distractors(correct_id, "正解", candidates, count=3, rng=random.Random(1))


def test_pick_distractors_prefers_preferred_pool_first() -> None:
    correct_id = uuid.uuid4()
    candidates = _candidates(5)
    preferred = ["あいだに", "からには"]
    chosen = pick_distractors(
        correct_id, "正解", candidates, count=3, rng=random.Random(1), preferred=preferred
    )
    assert len(chosen) == 3
    # both preferred items must be used before falling back to the random pool
    assert "あいだに" in chosen
    assert "からには" in chosen


def test_pick_distractors_preferred_excludes_correct_answer_text() -> None:
    correct_id = uuid.uuid4()
    candidates = _candidates(5)
    preferred = ["正解", "からには"]  # "正解" equals correct_answer_text, must be dropped
    chosen = pick_distractors(
        correct_id, "正解", candidates, count=3, rng=random.Random(1), preferred=preferred
    )
    assert "正解" not in chosen
    assert "からには" in chosen


def test_pick_distractors_falls_back_to_pool_when_preferred_insufficient() -> None:
    correct_id = uuid.uuid4()
    candidates = _candidates(5)
    preferred = ["からには"]  # only 1 preferred, need 3 total
    chosen = pick_distractors(
        correct_id, "正解", candidates, count=3, rng=random.Random(1), preferred=preferred
    )
    assert len(chosen) == 3
    assert "からには" in chosen
    assert len(set(chosen)) == 3


def test_pick_distractors_empty_preferred_behaves_like_none() -> None:
    correct_id = uuid.uuid4()
    candidates = _candidates(5)
    chosen_none = pick_distractors(correct_id, "正解", candidates, count=3, rng=random.Random(7), preferred=None)
    chosen_empty = pick_distractors(correct_id, "正解", candidates, count=3, rng=random.Random(7), preferred=[])
    assert chosen_none == chosen_empty
