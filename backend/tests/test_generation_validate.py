from __future__ import annotations

from app.services.generation.provider import RawGeneratedSentence
from app.services.generation.validate import (
    dedup_hash,
    has_grammar_target,
    normalize_for_dedup,
    validate_generated_sentence,
)


def _sentence(full_html: str, answer: str = "うちに") -> RawGeneratedSentence:
    return RawGeneratedSentence(
        sentence_full_html=full_html,
        sentence_with_blank_html=full_html.replace(answer, "___"),
        correct_answer_text=answer,
        explanation_ru="test",
    )


def test_has_grammar_target_true_when_present() -> None:
    html = "<ruby>日本<rt>にほん</rt></ruby>にいる<b>うちに</b>行きたい。"
    assert has_grammar_target(html, "うちに")


def test_has_grammar_target_false_when_missing() -> None:
    html = "<ruby>日本<rt>にほん</rt></ruby>に行きたい。"
    assert not has_grammar_target(html, "うちに")


def test_validate_generated_sentence_rejects_missing_target() -> None:
    sentence = _sentence("全く違う文です。", answer="全く違う文です。")
    assert not validate_generated_sentence(sentence, target_construction="うちに")


def test_validate_generated_sentence_accepts_valid() -> None:
    sentence = _sentence("<b>うちに</b>食べてください。")
    assert validate_generated_sentence(sentence, target_construction="うちに")


def test_validate_generated_sentence_rejects_empty_text() -> None:
    sentence = _sentence("", answer="")
    assert not validate_generated_sentence(sentence, target_construction="うちに")


def test_normalize_for_dedup_strips_html_and_punctuation() -> None:
    a = normalize_for_dedup("<ruby>日本<rt>にほん</rt></ruby>に<b>うちに</b>行きたい。")
    b = normalize_for_dedup("日本にうちに行きたい")
    assert a == b


def test_dedup_hash_is_stable_and_collision_free_for_different_sentences() -> None:
    h1 = dedup_hash("<b>うちに</b>食べてください。")
    h2 = dedup_hash("<b>うちに</b>食べてください。")
    h3 = dedup_hash("<b>間</b>に寝てしまった。")
    assert h1 == h2
    assert h1 != h3
