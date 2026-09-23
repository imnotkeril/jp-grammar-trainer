from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.grammar_progress import GrammarStatus
from app.models.question import Question
from app.models.vocabulary import UserVocabulary, Vocabulary, VocabularyEntryType
from tests.conftest import make_grammar, make_progress, make_question


def make_vocab(db: Session, *, surface_form: str) -> Vocabulary:
    vocab = Vocabulary(
        surface_form=surface_form,
        entry_type=VocabularyEntryType.WORD,
        reading="よみ",
        meaning_ru="значение",
    )
    db.add(vocab)
    db.flush()
    return vocab


def test_submit_answer_records_vocabulary_exposure(client: TestClient, db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="うちに")
    make_progress(db_session, grammar, status=GrammarStatus.NEW)
    question = make_question(db_session, grammar)
    # give the question ruby-marked-up sentence content so exposure recording has something
    # to match against.
    question.sentence_full_html = "<ruby>母<rt>かあ</rt></ruby>は<b>うちに</b>寝た。"
    vocab = make_vocab(db_session, surface_form="母")
    db_session.commit()

    resp = client.post(
        "/review/answer",
        json={"question_id": str(question.id), "selected_option": "A"},
    )
    assert resp.status_code == 200

    uv = db_session.get(UserVocabulary, vocab.id)
    assert uv is not None
    assert uv.correct_exposures == 1
    assert uv.correct_streak == 1


def test_session_response_includes_known_words(client: TestClient, db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="うちに")
    make_progress(db_session, grammar, status=GrammarStatus.NEW)
    make_question(db_session, grammar)
    vocab = make_vocab(db_session, surface_form="母")
    db_session.add(UserVocabulary(vocabulary_id=vocab.id, correct_streak=5, known_since=None))
    db_session.flush()
    from datetime import datetime, timezone

    uv = db_session.get(UserVocabulary, vocab.id)
    assert uv is not None
    uv.known_since = datetime.now(timezone.utc)
    db_session.commit()

    resp = client.post("/review/session", json={"size": 10})
    assert resp.status_code == 200
    assert resp.json()["known_words"] == ["母"]
