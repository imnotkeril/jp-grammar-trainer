from __future__ import annotations

from app.services.relation_heuristics import (
    ScorableItem,
    extract_kanji,
    jaccard,
    match_stem,
    tokenize_ru,
    top_candidates,
)


def test_match_stem_finds_shared_wake_family_stem() -> None:
    """The わけ family from idea doc §10 / ARCHITECTURE.md V2.2: わけだ, わけではない,
    わけがない, わけにはいかない should all share the "わけ" stem."""
    for text in ["わけだ", "わけではない", "わけがない", "わけにはいかない"]:
        assert match_stem(text) == "わけ"


def test_match_stem_returns_none_for_unrelated_text() -> None:
    assert match_stem("食べ物") is None


def test_tokenize_ru_drops_stopwords_and_punctuation() -> None:
    tokens = tokenize_ru("Это значение, которое выражает причину и следствие.")
    assert "это" not in tokens
    assert "и" not in tokens
    assert "значение," not in tokens  # punctuation must be stripped, not left attached
    assert "значение" in tokens


def test_jaccard_identical_and_disjoint() -> None:
    a = frozenset({"причина", "следствие"})
    assert jaccard(a, a) == 1.0
    assert jaccard(a, frozenset({"совсем", "другое"})) == 0.0
    assert jaccard(frozenset(), frozenset()) == 0.0


def test_extract_kanji_ignores_kana() -> None:
    assert extract_kanji("食べる") == frozenset({"食"})
    assert extract_kanji("わけだ") == frozenset()


def test_top_candidates_scores_wake_family_high_and_unrelated_pair_low() -> None:
    items = [
        ScorableItem("wake-da", "わけだ", "означает причину и следствие", "わけだ"),
        ScorableItem("wake-dewa-nai", "わけではない", "отрицает причину, но не факт", "わけではない"),
        ScorableItem("wake-ga-nai", "わけがない", "выражает полную невозможность", "わけがない"),
        # Unrelated item: no shared stem, no meaning overlap, no shared kanji.
        ScorableItem("tabemono", "食べ物", "еда, то что едят", "食べ物"),
    ]

    candidates = top_candidates(items, per_item_cap=6)
    pairs = {frozenset((c.item_a_id, c.item_b_id)): c for c in candidates}

    wake_pair = pairs.get(frozenset(("wake-da", "wake-dewa-nai")))
    assert wake_pair is not None
    assert wake_pair.shared_stem == "わけ"

    # every わけ-family pair should score strictly higher than any pair involving the
    # unrelated 食べ物 item (which may or may not even clear MIN_CANDIDATE_SCORE).
    wake_scores = [
        c.score
        for c in candidates
        if {c.item_a_id, c.item_b_id} <= {"wake-da", "wake-dewa-nai", "wake-ga-nai"}
    ]
    unrelated_scores = [
        c.score for c in candidates if "tabemono" in (c.item_a_id, c.item_b_id)
    ]
    assert wake_scores, "expected at least one わけ-family candidate pair"
    if unrelated_scores:
        assert min(wake_scores) > max(unrelated_scores)


def test_top_candidates_caps_total_pairs_well_below_all_pairs() -> None:
    """10 items all sharing the same stem -> all-pairs would be C(10,2)=45. The per-item cap
    (ARCHITECTURE.md V2.2 step 4: ~205*6/2 for the real deck) must keep this well below that,
    not just quietly return everything.
    """
    items = [ScorableItem(f"g{i}", f"わけ{i}", f"значение {i}", f"わけ{i}") for i in range(10)]
    candidates = top_candidates(items, per_item_cap=3)
    all_pairs_count = 10 * 9 // 2
    assert 0 < len(candidates) < all_pairs_count
