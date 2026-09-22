from __future__ import annotations

import random
import uuid

from beartype import beartype


@beartype
def pick_distractors(
    correct_grammar_id: uuid.UUID,
    correct_answer_text: str,
    candidates: list[tuple[uuid.UUID, str]],
    count: int = 3,
    rng: random.Random | None = None,
) -> list[str]:
    """Pick `count` distractor strings from other grammar items' target constructions.

    MVP approach (ARCHITECTURE.md §7.5 / ADR-10): uniform random over all other grammar
    items, excluding the correct grammar item itself and any candidate whose text is
    literally identical to the correct answer (avoid a trivially duplicate-looking option).
    No tag/graph similarity on MVP — that's a V2 upgrade.
    """
    rng = rng or random.Random()
    pool = [
        text
        for gid, text in candidates
        if gid != correct_grammar_id and text.strip() != correct_answer_text.strip()
    ]
    if len(pool) < count:
        raise ValueError(
            f"Not enough distractor candidates: need {count}, have {len(pool)}. "
            "Seed the grammar table with more items first."
        )
    return rng.sample(pool, count)
