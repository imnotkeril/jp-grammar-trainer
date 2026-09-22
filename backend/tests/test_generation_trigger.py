from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.question import Question, QuestionSource, ValidationStatus
from app.services.generation.provider import RawGeneratedSentence
from app.services.generation.trigger import generate_batch_for_grammar
from tests.conftest import make_grammar


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
