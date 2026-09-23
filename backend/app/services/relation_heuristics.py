"""Pure-Python heuristic candidate scoring for the grammar relation graph.

Split out from app/scripts/generate_relations.py so the scoring logic is independently
unit-testable without a DB (per ARCHITECTURE.md V2.5 test plan: "unit tests for the
heuristic scorer against known N3 confusable sets ... score high").

See ARCHITECTURE.md V2 slice, "V2.2 Relation population strategy" for the full rationale
of each signal.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from beartype import beartype

# ~30 common N3 function-word / grammatical-pattern stems, extracted by eye from scanning
# this deck's target_construction values (ARCHITECTURE.md V2.2 step 1). Pairs sharing a stem
# are strong candidates for similar_form/commonly_confused — e.g. the わけ family
# (わけだ/わけではない/わけがない/わけにはいかない) all share the "わけ" stem.
FUNCTION_WORD_STEMS: tuple[str, ...] = (
    "わけ",
    "ばかり",
    "たら",
    "なら",
    "ので",
    "のに",
    "ながら",
    "つつ",
    "きり",
    "がち",
    "気味",
    "っぽい",
    "ようがない",
    "あげく",
    "すえ",
    "とたん",
    "からには",
    "ものの",
    "ものを",
    "ものだ",
    "はず",
    "べき",
    "しかない",
    "ざるを得ない",
    "てはいけない",
    "というより",
    "うちに",
    "あいだに",
    "たびに",
    "につれて",
    "にしたがって",
    "うえで",
    "うえに",
    "かのように",
    "かのようだ",
    "に違いない",
    "に決まっている",
)
# Sort longest-first so e.g. "かのようだ" is preferred over the shorter "かのように" when both
# would match, and more specific stems win over generic substrings.
_STEMS_BY_LENGTH = tuple(sorted(FUNCTION_WORD_STEMS, key=len, reverse=True))

# Small, fixed Russian stopword list for meaning_ru tokenization (ARCHITECTURE.md V2.2
# step 1.2) — not exhaustive, just enough to stop short/common connective words from
# dominating the Jaccard overlap score.
RUSSIAN_STOPWORDS: frozenset[str] = frozenset(
    {
        "и", "в", "во", "на", "с", "со", "что", "как", "для", "не", "да", "но", "а", "у",
        "к", "ко", "о", "об", "от", "по", "за", "до", "из", "же", "ли", "то", "это", "эта",
        "этот", "если", "когда", "где", "чтобы", "или", "бы", "уже", "еще", "также", "так",
        "его", "ее", "их", "он", "она", "оно", "они", "мы", "вы", "я", "ты", "того", "тому",
        "при", "без", "под", "над", "перед", "после",
    }
)

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_KANJI_RE = re.compile(r"[一-鿿]")


@beartype
def match_stem(text: str) -> str | None:
    """Longest FUNCTION_WORD_STEMS entry contained in `text`, or None."""
    for stem in _STEMS_BY_LENGTH:
        if stem in text:
            return stem
    return None


@beartype
def tokenize_ru(text: str) -> frozenset[str]:
    """Lowercase, strip punctuation, split on whitespace, drop stopwords/empties."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    stripped = _PUNCT_RE.sub(" ", normalized)
    tokens = {tok for tok in stripped.split() if tok and tok not in RUSSIAN_STOPWORDS}
    return frozenset(tokens)


@beartype
def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


@beartype
def extract_kanji(text: str) -> frozenset[str]:
    return frozenset(_KANJI_RE.findall(text))


@beartype
def build_kanji_rarity(all_kanji_sets: list[frozenset[str]]) -> dict[str, float]:
    """Rarity weight per kanji = 1 / (number of items containing it), across the whole
    corpus. A kanji appearing in only 2 items scores 0.5; one appearing in 50 items scores
    0.02 — shared common kanji contribute little, shared rare kanji contribute a lot, per
    ARCHITECTURE.md V2.2 step 1.3.
    """
    counts: dict[str, int] = {}
    for kanji_set in all_kanji_sets:
        for kanji in kanji_set:
            counts[kanji] = counts.get(kanji, 0) + 1
    return {kanji: 1.0 / count for kanji, count in counts.items()}


@dataclass(frozen=True, slots=True)
class ScorableItem:
    """Minimal shape needed to score a candidate pair — decoupled from the ORM model so
    this module has no DB dependency (and is trivially unit-testable)."""

    item_id: str
    target_construction: str
    meaning_ru: str
    expression_clean: str


@dataclass(frozen=True, slots=True)
class Candidate:
    item_a_id: str
    item_b_id: str
    score: float
    shared_stem: str | None
    meaning_jaccard: float


# Score weights: shared-stem match is the strongest signal (this deck's actual
# construction-family clusters, ARCHITECTURE.md V2.2 step 4), meaning overlap next,
# shared-kanji rarity is a weak tie-breaker/topical proxy.
_STEM_WEIGHT = 3.0
_JACCARD_WEIGHT = 2.0
_KANJI_WEIGHT = 1.0

# Below this combined score a pair isn't worth surfacing as a candidate at all.
MIN_CANDIDATE_SCORE = 0.15


@beartype
def score_pair(
    a: ScorableItem,
    b: ScorableItem,
    kanji_rarity: dict[str, float],
) -> Candidate:
    stem_a = match_stem(a.target_construction)
    stem_b = match_stem(b.target_construction)
    shared_stem = stem_a if stem_a is not None and stem_a == stem_b else None
    stem_score = _STEM_WEIGHT if shared_stem else 0.0

    tokens_a = tokenize_ru(a.meaning_ru)
    tokens_b = tokenize_ru(b.meaning_ru)
    meaning_score = jaccard(tokens_a, tokens_b)

    kanji_a = extract_kanji(a.expression_clean)
    kanji_b = extract_kanji(b.expression_clean)
    shared_kanji = kanji_a & kanji_b
    kanji_score = sum(kanji_rarity.get(k, 0.0) for k in shared_kanji)

    total = stem_score + _JACCARD_WEIGHT * meaning_score + _KANJI_WEIGHT * kanji_score
    return Candidate(
        item_a_id=a.item_id,
        item_b_id=b.item_id,
        score=total,
        shared_stem=shared_stem,
        meaning_jaccard=meaning_score,
    )


@beartype
def top_candidates(items: list[ScorableItem], per_item_cap: int = 6) -> list[Candidate]:
    """All-pairs heuristic scoring, capped to the top `per_item_cap` partners per item, then
    symmetric-deduplicated. See ARCHITECTURE.md V2.2 step 4 for the ≤205×6/2 cap rationale.
    """
    kanji_rarity = build_kanji_rarity([extract_kanji(item.expression_clean) for item in items])

    per_item_best: dict[str, list[Candidate]] = {item.item_id: [] for item in items}
    for i, a in enumerate(items):
        for b in items[i + 1 :]:
            candidate = score_pair(a, b, kanji_rarity)
            if candidate.score < MIN_CANDIDATE_SCORE:
                continue
            per_item_best[a.item_id].append(candidate)
            per_item_best[b.item_id].append(candidate)

    kept: dict[tuple[str, str], Candidate] = {}
    for item_id, candidates in per_item_best.items():
        top = sorted(candidates, key=lambda c: c.score, reverse=True)[:per_item_cap]
        for c in top:
            lo, hi = sorted((c.item_a_id, c.item_b_id))
            kept[(lo, hi)] = c  # symmetric dedup: same pair keeps a single Candidate

    return sorted(kept.values(), key=lambda c: c.score, reverse=True)
