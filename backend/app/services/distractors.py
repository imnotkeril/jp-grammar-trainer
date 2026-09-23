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
    preferred: list[str] | None = None,
) -> list[str]:
    """Pick `count` distractor strings from other grammar items' target constructions.

    MVP approach (ARCHITECTURE.md §7.5 / ADR-10): uniform random over all other grammar
    items, excluding the correct grammar item itself and any candidate whose text is
    literally identical to the correct answer (avoid a trivially duplicate-looking option).

    `preferred` (ARCHITECTURE.md V3.5): an optional pool of target_construction texts from
    grammar items connected to the correct one via a commonly_confused/similar_form edge,
    tried before the uniform-random pool — once real confusion edges exist for an item, its
    distractors are drawn from its actual confusable partners first. Falls back to today's
    uniform-random behavior automatically when `preferred` is empty/None.
    """
    rng = rng or random.Random()
    preferred_pool = [t for t in (preferred or []) if t.strip() != correct_answer_text.strip()]
    rng.shuffle(preferred_pool)
    chosen = preferred_pool[:count]

    remaining = count - len(chosen)
    if remaining > 0:
        pool = [
            text
            for gid, text in candidates
            if gid != correct_grammar_id
            and text.strip() != correct_answer_text.strip()
            and text not in chosen
        ]
        if len(pool) < remaining:
            raise ValueError(
                f"Not enough distractor candidates: need {remaining}, have {len(pool)}. "
                "Seed the grammar table with more items first."
            )
        chosen += rng.sample(pool, remaining)
    return chosen
