from __future__ import annotations

import re
from typing import Literal

from beartype import beartype

FuriganaMode = Literal["always", "never", "by_level", "adaptive"]

_RT_TAG_RE = re.compile(r"<rt>.*?</rt>", re.DOTALL)
_BOLD_BLOCK_RE = re.compile(r"<b>.*?</b>", re.DOTALL)
# The seed/AI sentence markup wraps the tested target as <ruby><b>目</b><rt>め</rt></ruby> —
# the <rt> is a SIBLING of <b>, not nested inside it. `strip_furigana_inside_bold` below must
# also catch this sibling form or it silently never strips anything on real data (the <b> span
# alone never contains an <rt>).
_BOLD_THEN_SIBLING_RT_RE = re.compile(r"(<b>.*?</b>)<rt>.*?</rt>", re.DOTALL)

# A handful of rows in the Anki-sourced seed data have a malformed <rt> span whose payload
# is the rest of the sentence (or another bled-in fragment) rather than a short kana reading
# for the immediately preceding base text — see ARCHITECTURE.md ADR-6/ADR-6b; the seed import
# intentionally leaves these un-hand-fixed in the source JSON. A real reading is never more
# than a few kana per base character, so any <rt> payload far longer than that relative to
# its base text is dropped rather than rendered, mirroring frontend/.../FuriganaText.tsx.
_RUBY_PAIR_RE = re.compile(r"<ruby>((?:(?!</ruby>)[\s\S])*?)<rt>(.*?)</rt></ruby>", re.DOTALL)
_STRIP_TAGS_RE = re.compile(r"<[^>]+>")
_MAX_RT_RATIO = 4
_MAX_RT_SLACK = 2


@beartype
def strip_malformed_furigana(html: str) -> str:
    """Drop <rt> payloads that are implausibly long for the base text they annotate,
    keeping the base text visible. Applied unconditionally, before any mode-specific
    stripping — a bad reading should never render regardless of furigana mode.
    """

    def _drop_if_malformed(match: re.Match[str]) -> str:
        base, rt = match.group(1), match.group(2)
        base_length = len(_STRIP_TAGS_RE.sub("", base)) or 1
        threshold = base_length * _MAX_RT_RATIO + _MAX_RT_SLACK
        if len(rt) > threshold:
            return base
        return match.group(0)

    return _RUBY_PAIR_RE.sub(_drop_if_malformed, html)


@beartype
def strip_all_furigana(html: str) -> str:
    """Remove every <rt>...</rt> payload, keeping the base <ruby> kanji text (mode: never)."""
    return _RT_TAG_RE.sub("", html)


@beartype
def strip_furigana_inside_bold(html: str) -> str:
    """Strip <rt> only within <b>...</b> spans, keep it everywhere else (mode: by_level).

    See ARCHITECTURE.md §5 / ADR-7: the tested target construction stays furigana-free so
    the learner reads the kanji they're being quizzed on; surrounding context keeps its
    reading aids.
    """

    def _strip_within_bold(match: re.Match[str]) -> str:
        return _RT_TAG_RE.sub("", match.group(0))

    without_nested = _BOLD_BLOCK_RE.sub(_strip_within_bold, html)
    return _BOLD_THEN_SIBLING_RT_RE.sub(r"\1", without_nested)


@beartype
def strip_known_words(html: str, known_surface_forms: frozenset[str]) -> str:
    """Additionally strip <rt> for <ruby> spans whose base is in known_surface_forms.

    Applied on top of the by_level baseline for mode="adaptive" (ARCHITECTURE.md V3.4,
    ADR-15/16). Exact-match only: `base` (with any inner tags like <b> stripped) must equal
    one of the known surface forms verbatim.
    """

    def _drop_if_known(match: re.Match[str]) -> str:
        base = _STRIP_TAGS_RE.sub("", match.group(1))
        return match.group(1) if base in known_surface_forms else match.group(0)

    return _RUBY_PAIR_RE.sub(_drop_if_known, html)


@beartype
def render_furigana(
    html: str, mode: FuriganaMode, known_surface_forms: frozenset[str] = frozenset()
) -> str:
    """Apply the furigana display mode to ruby-marked-up HTML. Pure function, no DB access.

    - "always": return as-is, browsers render <ruby><rt> natively.
    - "never": strip every <rt> payload.
    - "by_level": strip <rt> only inside the <b> (tested target) span (MVP heuristic,
      ARCHITECTURE.md ADR-7).
    - "adaptive": by_level baseline, plus strip <rt> for any <ruby> span whose base
      exact-matches a currently-known word (ARCHITECTURE.md V3.4).
    """
    sanitized = strip_malformed_furigana(html)
    if mode == "always":
        return sanitized
    if mode == "never":
        return strip_all_furigana(sanitized)
    if mode == "by_level":
        return strip_furigana_inside_bold(sanitized)
    if mode == "adaptive":
        return strip_known_words(strip_furigana_inside_bold(sanitized), known_surface_forms)
    raise ValueError(f"Unknown furigana mode: {mode!r}")
