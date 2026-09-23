from __future__ import annotations

import re
from datetime import datetime

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models.vocabulary import UserVocabulary, Vocabulary
from app.services.furigana import _RUBY_PAIR_RE, _STRIP_TAGS_RE

# See ARCHITECTURE.md "V3 Slice: Adaptive Practice & Vocabulary", V3.4, ADR-15/16/19.


@beartype
def extract_ruby_bases(html: str) -> list[str]:
    """Pull every <ruby>base<rt>...</rt></ruby> base string out of `html`, tags stripped.

    Reuses furigana._RUBY_PAIR_RE (ADR-15) so vocabulary matching stays in lockstep with
    whatever the furigana renderer itself considers one ruby span — no second regex to drift.
    """
    return [_STRIP_TAGS_RE.sub("", m.group(1)) for m in _RUBY_PAIR_RE.finditer(html)]


@beartype
def known_surface_forms(db: Session) -> frozenset[str]:
    """Every vocabulary.surface_form whose user_vocabulary row is currently "known"
    (known_since IS NOT NULL). See ARCHITECTURE.md V3.4."""
    stmt = (
        select(Vocabulary.surface_form)
        .join(UserVocabulary, UserVocabulary.vocabulary_id == Vocabulary.id)
        .where(UserVocabulary.known_since.is_not(None))
    )
    return frozenset(db.scalars(stmt).all())


@beartype
def record_exposures(db: Session, sentence_full_html: str, is_correct: bool, now: datetime) -> None:
    """Update per-word exposure/streak state for every vocabulary word matched in the
    sentence just answered. Whole-sentence correctness is credited to every matched word
    (ADR-19 — deliberate approximation, not per-word comprehension).
    """
    bases = set(extract_ruby_bases(sentence_full_html))
    if not bases:
        return

    vocab_rows = db.scalars(select(Vocabulary).where(Vocabulary.surface_form.in_(bases))).all()
    for vocab in vocab_rows:
        uv = db.get(UserVocabulary, vocab.id)
        if uv is None:
            uv = UserVocabulary(vocabulary_id=vocab.id)
            db.add(uv)

        if is_correct:
            uv.correct_exposures += 1
            uv.correct_streak += 1
            if uv.correct_streak >= settings.known_streak_threshold and uv.known_since is None:
                uv.known_since = now
        else:
            uv.incorrect_exposures += 1
            uv.correct_streak = 0
            uv.known_since = None  # relapse — ADR-16
        uv.last_exposed_at = now
