from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.grammar_relation import RelationType
from app.models.question import Question, QuestionSource, ValidationStatus
from app.services.generation.provider import GenerationPrompt, RawGeneratedSentence, build_prompt
from app.services.generation.trigger import _fetch_confused_texts, generate_batch_for_grammar
from tests.conftest import make_grammar, make_relation


class _FakeProvider:
    model_name = "fake-model"

    def __init__(self, sentences: list[RawGeneratedSentence]) -> None:
        self._sentences = sentences

    async def generate_sentences(self, prompt: object) -> list[RawGeneratedSentence]:
        return self._sentences


async def test_generate_batch_wires_distractors_into_options(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    grammar = make_grammar(db_session, target_construction="うちに", source_note_id=9_400_001)
    # need >=3 other grammar items with a target_construction to serve as distractors
    for i, tc in enumerate(["あいだに", "からには", "ものの"]):
        make_grammar(db_session, target_construction=tc, source_note_id=9_400_100 + i)
    db_session.commit()

    fake_sentence = RawGeneratedSentence(
        sentence_full_html="<b>うちに</b>食べてください。",
        sentence_with_blank_html="___食べてください。",
        correct_answer_text="うちに",
        explanation_ru="説明。",
    )
    monkeypatch.setattr(
        "app.services.generation.trigger.get_provider",
        lambda: _FakeProvider([fake_sentence]),
    )

    inserted = await generate_batch_for_grammar(db_session, grammar.id)
    assert inserted == 1

    question = db_session.query(Question).filter_by(grammar_id=grammar.id).one()
    assert question.validation_status == ValidationStatus.VALID
    assert question.source == QuestionSource.AI_GENERATED
    assert len(question.options) == 4
    option_texts = {o["text"] for o in question.options}
    assert "うちに" in option_texts
    correct_opt = next(o for o in question.options if o["text"] == "うちに")
    assert question.correct_option == correct_opt["key"]
    # the 3 distractors must all be real, distinct target_constructions, none equal to correct
    distractor_texts = option_texts - {"うちに"}
    assert len(distractor_texts) == 3
    # no commonly_confused/similar_form relations exist for this grammar -> uniform-random pool
    assert question.has_confusion_distractor is False


async def test_generate_batch_rejects_when_target_missing(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    grammar = make_grammar(db_session, target_construction="うちに", source_note_id=9_400_002)
    for i, tc in enumerate(["あいだに", "からには", "ものの"]):
        make_grammar(db_session, target_construction=tc, source_note_id=9_400_200 + i)
    db_session.commit()

    bad_sentence = RawGeneratedSentence(
        sentence_full_html="全く関係ない文です。",
        sentence_with_blank_html="全く関係ない文です。",
        correct_answer_text="うちに",
        explanation_ru="説明。",
    )
    monkeypatch.setattr(
        "app.services.generation.trigger.get_provider",
        lambda: _FakeProvider([bad_sentence]),
    )

    inserted = await generate_batch_for_grammar(db_session, grammar.id)
    assert inserted == 0

    question = db_session.query(Question).filter_by(grammar_id=grammar.id).one()
    assert question.validation_status == ValidationStatus.REJECTED
    assert question.options == []


def test_fetch_confused_texts_returns_both_directions(db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="うちに", source_note_id=9_401_001)
    b = make_grammar(db_session, target_construction="あいだに", source_note_id=9_401_002)
    c = make_grammar(db_session, target_construction="からには", source_note_id=9_401_003)
    make_relation(db_session, a, b, relation_type=RelationType.COMMONLY_CONFUSED, strength=0.9)
    make_relation(db_session, c, a, relation_type=RelationType.SIMILAR_FORM, strength=0.4)
    db_session.commit()

    result = _fetch_confused_texts(db_session, a.id)
    texts = {text for text, _meaning, _strength in result}
    assert texts == {"あいだに", "からには"}


def test_fetch_confused_texts_ignores_unrelated_relation_types(db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="うちに", source_note_id=9_401_010)
    b = make_grammar(db_session, target_construction="あいだに", source_note_id=9_401_011)
    make_relation(db_session, a, b, relation_type=RelationType.SIMILAR_MEANING, strength=0.9)
    db_session.commit()

    assert _fetch_confused_texts(db_session, a.id) == []


async def test_generate_batch_biases_distractors_toward_confused_grammar(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    grammar = make_grammar(db_session, target_construction="うちに", source_note_id=9_401_020)
    confused = make_grammar(db_session, target_construction="あいだに", source_note_id=9_401_021)
    for i, tc in enumerate(["からには", "ものの", "つつ"]):
        make_grammar(db_session, target_construction=tc, source_note_id=9_401_100 + i)
    make_relation(db_session, grammar, confused, relation_type=RelationType.COMMONLY_CONFUSED, strength=0.9)
    db_session.commit()

    captured_prompts: list[GenerationPrompt] = []

    def _capturing_build_prompt(*args: object, **kwargs: object) -> GenerationPrompt:
        prompt = build_prompt(*args, **kwargs)  # type: ignore[arg-type]
        captured_prompts.append(prompt)
        return prompt

    monkeypatch.setattr("app.services.generation.trigger.build_prompt", _capturing_build_prompt)

    fake_sentence = RawGeneratedSentence(
        sentence_full_html="<b>うちに</b>食べてください。",
        sentence_with_blank_html="___食べてください。",
        correct_answer_text="うちに",
        explanation_ru="説明。",
    )
    monkeypatch.setattr(
        "app.services.generation.trigger.get_provider",
        lambda: _FakeProvider([fake_sentence]),
    )

    inserted = await generate_batch_for_grammar(db_session, grammar.id)
    assert inserted == 1

    assert len(captured_prompts) == 1
    assert captured_prompts[0].confusable_with == [
        {"target_construction": "あいだに", "meaning_ru": confused.meaning_ru}
    ]

    question = db_session.query(Question).filter_by(grammar_id=grammar.id).one()
    option_texts = {o["text"] for o in question.options}
    assert "あいだに" in option_texts  # preferred confusable partner used as a distractor
    assert question.has_confusion_distractor is True


async def test_generate_batch_rejects_when_not_enough_distractor_candidates(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    grammar = make_grammar(db_session, target_construction="うちに", source_note_id=9_400_003)
    # deliberately no other grammar items seeded -> 0 distractor candidates available
    db_session.commit()

    sentence = RawGeneratedSentence(
        sentence_full_html="<b>うちに</b>食べてください。",
        sentence_with_blank_html="___食べてください。",
        correct_answer_text="うちに",
        explanation_ru="説明。",
    )
    monkeypatch.setattr(
        "app.services.generation.trigger.get_provider",
        lambda: _FakeProvider([sentence]),
    )

    inserted = await generate_batch_for_grammar(db_session, grammar.id)
    assert inserted == 0

    question = db_session.query(Question).filter_by(grammar_id=grammar.id).one()
    assert question.validation_status == ValidationStatus.REJECTED
