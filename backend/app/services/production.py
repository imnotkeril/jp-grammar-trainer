"""Sentence-production practice (roadmap item 4), fully offline.

The learner sees the abstract pattern + the Russian translation of a seeded example and types
their own Japanese sentence. There is no LLM or network call: a cheap string check reports
whether the target construction shows up, then the model sentence is revealed for the learner
to self-rate. Nothing here writes to grammar_progress — production results are stateless, so
the SRS data from recognition reviews is never touched by this mode.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from beartype import beartype
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress

MatchKind = Literal["exact", "stem", "none", "empty"]

# Japanese-ish text: kana, CJK ideographs, halfwidth katakana.
_JAPANESE_RE = re.compile(r"[぀-ヿ㐀-鿿ｦ-ﾟ]")
_TRAILING_PUNCT_RE = re.compile(r"[。．.！!？?\s]+$")
_WHITESPACE_RE = re.compile(r"\s+")
_RT_SPAN_RE = re.compile(r"<rt>.*?</rt>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_PATTERN_LINE_RE = re.compile(r"Паттерн:\s*(.+)")
_MEANING_LINE_RE = re.compile(r"Значение:\s*(.+)")
# Targets are the conjugated form from the seeded example (いただきました), so a correct answer
# may inflect differently (いただいた). Longer targets also match on their leading half; shorter
# ones (し, 間, ために, かと思うと) must match exactly or a 1-2 character stem would hit nearly
# any sentence.
_MIN_STEM_SOURCE_LENGTH = 6
_MIN_STEM_LENGTH = 3
_MIN_EXTRA_CHARS = 3  # a "sentence" must have more text than the construction alone


@dataclass(frozen=True, slots=True)
class ProductionCheck:
    match: MatchKind
    too_short: bool


@beartype
def normalize(text: str) -> str:
    """NFKC + whitespace removal + trailing punctuation strip, for comparison only."""
    folded = unicodedata.normalize("NFKC", text)
    return _TRAILING_PUNCT_RE.sub("", _WHITESPACE_RE.sub("", folded))


@beartype
def plain_text(html: str) -> str:
    """Drop furigana readings and markup (Anki-derived rows carry <ruby> in form labels)."""
    return _TAG_RE.sub("", _RT_SPAN_RE.sub("", html)).strip()


@beartype
def check_sentence(answer: str, target_construction: str) -> ProductionCheck:
    """Compare a typed answer against the seeded target form (see module docstring)."""
    typed = normalize(answer)
    if not typed or not _JAPANESE_RE.search(typed):
        return ProductionCheck(match="empty", too_short=True)

    target = normalize(target_construction)
    too_short = len(typed) < len(target) + _MIN_EXTRA_CHARS
    if not target:
        return ProductionCheck(match="none", too_short=too_short)
    if target in typed:
        return ProductionCheck(match="exact", too_short=too_short)
    if len(target) >= _MIN_STEM_SOURCE_LENGTH and target[: max(_MIN_STEM_LENGTH, len(target) // 2)] in typed:
        return ProductionCheck(match="stem", too_short=too_short)
    return ProductionCheck(match="none", too_short=too_short)


@beartype
def split_pattern_text(pattern_text: str) -> tuple[str, str]:
    """(pattern line, meaning line) from the "Паттерн: ...\\nЗначение: ..." convention shared
    by the Anki-derived N3 and authored N4/N2 content. Falls back to the raw text / empty."""
    pattern = _PATTERN_LINE_RE.search(pattern_text)
    meaning = _MEANING_LINE_RE.search(pattern_text)
    return (
        pattern.group(1).strip() if pattern else pattern_text.strip(),
        meaning.group(1).strip() if meaning else "",
    )


@beartype
def select_production_grammar(
    db: Session, size: int, level: str | None = None, now: datetime | None = None
) -> list[Grammar]:
    """Up to `size` grammar items that have a usable example, overdue ones first (so production
    practice follows the same recall schedule), topped up with random others."""
    now = now or datetime.now(timezone.utc)
    usable = (Grammar.target_construction != "", Grammar.expression_clean != "")

    due_stmt = (
        select(Grammar)
        .join(GrammarProgress, GrammarProgress.grammar_id == Grammar.id)
        .where(GrammarProgress.next_review <= now, *usable)
        .order_by(GrammarProgress.next_review.asc())
        .limit(size)
    )
    if level is not None:
        due_stmt = due_stmt.where(Grammar.level == level)
    chosen = list(db.scalars(due_stmt))

    if len(chosen) < size:
        top_up = select(Grammar).where(*usable).order_by(func.random()).limit(size - len(chosen))
        if chosen:
            top_up = top_up.where(Grammar.id.not_in([g.id for g in chosen]))
        if level is not None:
            top_up = top_up.where(Grammar.level == level)
        chosen += list(db.scalars(top_up))
    return chosen[:size]


@beartype
def get_grammar_or_none(db: Session, grammar_id: uuid.UUID) -> Grammar | None:
    return db.get(Grammar, grammar_id)
