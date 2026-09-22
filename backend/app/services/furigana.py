from __future__ import annotations

import re
from typing import Literal

from beartype import beartype

FuriganaMode = Literal["always", "never", "by_level"]

_RT_TAG_RE = re.compile(r"<rt>.*?</rt>", re.DOTALL)
_BOLD_BLOCK_RE = re.compile(r"<b>.*?</b>", re.DOTALL)


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

    return _BOLD_BLOCK_RE.sub(_strip_within_bold, html)


@beartype
def render_furigana(html: str, mode: FuriganaMode) -> str:
    """Apply the furigana display mode to ruby-marked-up HTML. Pure function, no DB access.

    - "always": return as-is, browsers render <ruby><rt> natively.
    - "never": strip every <rt> payload.
    - "by_level": strip <rt> only inside the <b> (tested target) span (MVP heuristic,
      ARCHITECTURE.md ADR-7 — true adaptive per-word furigana is V2).
    """
    if mode == "always":
        return html
    if mode == "never":
        return strip_all_furigana(html)
    if mode == "by_level":
        return strip_furigana_inside_bold(html)
    raise ValueError(f"Unknown furigana mode: {mode!r}")
