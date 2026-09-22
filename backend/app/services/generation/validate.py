from __future__ import annotations

import hashlib
import re

from beartype import beartype

from app.services.generation.provider import RawGeneratedSentence

_RT_SPAN_RE = re.compile(r"<rt>.*?</rt>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")
_PUNCTUATION_RE = re.compile(r"[、。！？「」『』・,.!?\"'\s]+")


@beartype
def strip_html(html: str) -> str:
    """Plain reader-visible text: drop furigana readings (<rt>...</rt>) and all remaining
    tags/whitespace, so dedup/grammar-fit checks compare the actual sentence, not the
    reading annotations layered on top of it.
    """
    without_readings = _RT_SPAN_RE.sub("", html)
    return _WHITESPACE_RE.sub("", _TAG_RE.sub("", without_readings))


@beartype
def normalize_for_dedup(sentence_full_html: str) -> str:
    """Normalize a generated sentence for exact-match dedup (ARCHITECTURE.md §7.4 / ADR-9)."""
    plain = strip_html(sentence_full_html)
    return _PUNCTUATION_RE.sub("", plain).lower()


@beartype
def dedup_hash(sentence_full_html: str) -> str:
    normalized = normalize_for_dedup(sentence_full_html)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@beartype
def has_grammar_target(sentence_full_html: str, target_construction: str) -> bool:
    """Grammar-fit check: the target construction must literally appear in the de-ruby'd text.

    Deterministic, cheap check per ARCHITECTURE.md §7.4 step 2 — catches the model silently
    dropping or mis-forming the target construction. Not a substitute for real grammatical
    validation (out of scope for MVP).
    """
    plain = strip_html(sentence_full_html)
    return target_construction.strip() in plain


@beartype
def validate_generated_sentence(
    sentence: RawGeneratedSentence,
    target_construction: str,
) -> bool:
    """Structural + grammar-fit checks. Dedup (against existing DB rows) happens at the
    DB-insert layer via the unique (grammar_id, dedup_hash) index — see ARCHITECTURE.md §7.4.
    """
    if not sentence.sentence_full_html.strip() or not sentence.correct_answer_text.strip():
        return False
    return has_grammar_target(sentence.sentence_full_html, target_construction)
