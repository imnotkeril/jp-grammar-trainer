from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.grammar_progress import GrammarProgress, GrammarStatus
from app.models.question import QuestionSource
from app.models.question_attempt import QuestionAttempt
from app.services.srs import FIXED_INTERVALS_DAYS
from tests.conftest import make_grammar, make_progress, make_question


def test_answer_correct_advances_srs_and_returns_explanation(client: TestClient, db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="うちに", pattern_text="Паттерн: X / Значение: пока")
    progress = make_progress(db_session, grammar, status=GrammarStatus.NEW)
    question = make_question(db_session, grammar)
    db_session.commit()

    resp = client.post(
        "/review/answer",
        json={"question_id": str(question.id), "selected_option": "A", "response_time_ms": 1200},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_correct"] is True
    assert body["correct_option"] == "A"
    assert body["explanation_ru"]
    assert body["sentence_full_html"] == question.sentence_full_html

    refreshed = db_session.get(GrammarProgress, grammar.id)
    assert refreshed is not None
    assert refreshed.interval_step == 1
    assert refreshed.interval_days == FIXED_INTERVALS_DAYS[1]
    assert refreshed.repetitions == 1
    assert refreshed.first_seen is not None

    attempts = db_session.query(QuestionAttempt).filter_by(question_id=question.id).all()
    assert len(attempts) == 1
    assert attempts[0].is_correct is True
    assert attempts[0].error_type is None


def test_answer_wrong_drops_two_steps_and_sets_error_type(client: TestClient, db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="うちに")
    progress = make_progress(db_session, grammar, status=GrammarStatus.REVIEW)
    # advance progress to interval_step 5 first, like the srs unit tests do
    progress.interval_step = 5
    progress.repetitions = 5
    db_session.flush()
    question = make_question(db_session, grammar)
    db_session.commit()

    resp = client.post(
        "/review/answer",
        json={"question_id": str(question.id), "selected_option": "B", "response_time_ms": 3000},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_correct"] is False
    assert body["correct_option"] == "A"
    assert "не подходит" in body["explanation_ru"]

    refreshed = db_session.get(GrammarProgress, grammar.id)
    assert refreshed is not None
    assert refreshed.interval_step == 3  # 5 - 2
    assert refreshed.repetitions == 0
    assert refreshed.lapses == 1

    attempts = db_session.query(QuestionAttempt).filter_by(question_id=question.id).all()
    assert len(attempts) == 1
    assert attempts[0].is_correct is False
    # "B" option text ("A案") doesn't match any real grammar's target_construction in this
    # fixture set, so the heuristic falls back to the generic "confusion" bucket.
    assert attempts[0].error_type == "confusion"


def test_answer_wrong_option_matching_real_grammar_is_similar_grammar_confusion(
    client: TestClient, db_session: Session
) -> None:
    correct_grammar = make_grammar(db_session, target_construction="うちに", source_note_id=9_200_001)
    confusable_grammar = make_grammar(db_session, target_construction="あいだに", source_note_id=9_200_002)
    make_progress(db_session, confusable_grammar, status=GrammarStatus.NEW)
    progress = make_progress(db_session, correct_grammar, status=GrammarStatus.NEW)
    question = make_question(
        db_session,
        correct_grammar,
        distractor_texts=("あいだに", "B案", "C案"),
    )
    db_session.commit()

    # find the option key assigned to "あいだに"
    b_option = next(o for o in question.options if o["text"] == "あいだに")

    resp = client.post(
        "/review/answer",
        json={"question_id": str(question.id), "selected_option": b_option["key"]},
    )
    assert resp.status_code == 200

    attempts = db_session.query(QuestionAttempt).filter_by(question_id=question.id).all()
    assert attempts[0].error_type == "similar_grammar_confusion"


def test_answer_on_ai_generated_question_updates_application_score(
    client: TestClient, db_session: Session
) -> None:
    grammar = make_grammar(db_session, target_construction="うちに", source_note_id=9_600_001)
    progress = make_progress(db_session, grammar, status=GrammarStatus.REVIEW)
    assert progress.application_score == pytest.approx(0.5)  # neutral default, never written yet
    question = make_question(db_session, grammar, source=QuestionSource.AI_GENERATED)
    db_session.commit()

    resp = client.post(
        "/review/answer",
        json={"question_id": str(question.id), "selected_option": "A"},
    )
    assert resp.status_code == 200

    refreshed = db_session.get(GrammarProgress, grammar.id)
    assert refreshed is not None
    # rolling_accuracy(0.5, True) with alpha=0.2 -> 0.6
    assert refreshed.application_score == pytest.approx(0.6)
    assert refreshed.discrimination_score == pytest.approx(0.5)  # untouched, no confusion distractor


def test_answer_on_seed_question_leaves_application_score_at_neutral_default(
    client: TestClient, db_session: Session
) -> None:
    grammar = make_grammar(db_session, target_construction="うちに", source_note_id=9_600_002)
    make_progress(db_session, grammar, status=GrammarStatus.REVIEW)
    question = make_question(db_session, grammar, source=QuestionSource.SEED)
    db_session.commit()

    resp = client.post(
        "/review/answer",
        json={"question_id": str(question.id), "selected_option": "A"},
    )
    assert resp.status_code == 200

    refreshed = db_session.get(GrammarProgress, grammar.id)
    assert refreshed is not None
    # seed question -> not "fresh context" -> application_score untouched (no data yet)
    assert refreshed.application_score == pytest.approx(0.5)


def test_answer_with_confusion_distractor_updates_discrimination_score(
    client: TestClient, db_session: Session
) -> None:
    grammar = make_grammar(db_session, target_construction="うちに", source_note_id=9_600_003)
    make_progress(db_session, grammar, status=GrammarStatus.REVIEW)
    question = make_question(db_session, grammar, has_confusion_distractor=True)
    db_session.commit()

    # answer wrong, on purpose, to check the EMA moves toward 0 for an incorrect informative attempt
    resp = client.post(
        "/review/answer",
        json={"question_id": str(question.id), "selected_option": "B"},
    )
    assert resp.status_code == 200

    refreshed = db_session.get(GrammarProgress, grammar.id)
    assert refreshed is not None
    # rolling_accuracy(0.5, False) with alpha=0.2 -> 0.4
    assert refreshed.discrimination_score == pytest.approx(0.4)
    assert refreshed.application_score == pytest.approx(0.5)  # seed question, untouched


def test_answer_without_confusion_distractor_leaves_discrimination_score_at_neutral_default(
    client: TestClient, db_session: Session
) -> None:
    grammar = make_grammar(db_session, target_construction="うちに", source_note_id=9_600_004)
    make_progress(db_session, grammar, status=GrammarStatus.REVIEW)
    question = make_question(db_session, grammar, has_confusion_distractor=False)
    db_session.commit()

    resp = client.post(
        "/review/answer",
        json={"question_id": str(question.id), "selected_option": "A"},
    )
    assert resp.status_code == 200

    refreshed = db_session.get(GrammarProgress, grammar.id)
    assert refreshed is not None
    assert refreshed.discrimination_score == pytest.approx(0.5)


def test_answer_unknown_question_404(client: TestClient, db_session: Session) -> None:
    resp = client.post(
        "/review/answer",
        json={"question_id": str(uuid.uuid4()), "selected_option": "A"},
    )
    assert resp.status_code == 404
