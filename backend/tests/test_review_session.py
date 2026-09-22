from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.grammar_progress import GrammarStatus
from app.models.question import Question, ValidationStatus
from tests.conftest import make_grammar, make_progress, make_question


def test_session_empty_when_nothing_due(client: TestClient, db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="うちに")
    make_progress(
        db_session,
        grammar,
        status=GrammarStatus.REVIEW,
        next_review=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.commit()

    resp = client.post("/review/session", json={"size": 10})
    assert resp.status_code == 200
    assert resp.json() == {"questions": []}


def test_session_serves_due_item_with_valid_question(client: TestClient, db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="うちに")
    make_progress(db_session, grammar, status=GrammarStatus.NEW)
    make_question(db_session, grammar)
    db_session.commit()

    resp = client.post("/review/session", json={"size": 10})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["questions"]) == 1
    q = body["questions"][0]
    assert q["grammar_id"] == str(grammar.id)
    assert len(q["options"]) == 4
    assert "___" in q["sentence_with_blank_html"]


def test_session_respects_size(client: TestClient, db_session: Session) -> None:
    for i in range(3):
        grammar = make_grammar(db_session, target_construction=f"パターン{i}", source_note_id=9_000_000 + i)
        make_progress(db_session, grammar, status=GrammarStatus.NEW)
        make_question(db_session, grammar)
    db_session.commit()

    resp = client.post("/review/session", json={"size": 5})
    assert resp.status_code == 200
    # size=5 respected as an upper bound (only 3 due items exist)
    assert len(resp.json()["questions"]) == 3


def test_session_overdue_before_new(client: TestClient, db_session: Session) -> None:
    now = datetime.now(timezone.utc)

    new_grammar = make_grammar(db_session, target_construction="新しい", source_note_id=9_100_001)
    make_progress(db_session, new_grammar, status=GrammarStatus.NEW, next_review=now)
    make_question(db_session, new_grammar)

    overdue_grammar = make_grammar(db_session, target_construction="遅れた", source_note_id=9_100_002)
    make_progress(
        db_session,
        overdue_grammar,
        status=GrammarStatus.REVIEW,
        next_review=now - timedelta(days=10),
    )
    make_question(db_session, overdue_grammar)
    db_session.commit()

    resp = client.post("/review/session", json={"size": 5})
    assert resp.status_code == 200
    questions = resp.json()["questions"]
    assert len(questions) == 2
    # overdue item must come first (ARCHITECTURE.md §8: "priority: overdue first, then new")
    assert questions[0]["grammar_id"] == str(overdue_grammar.id)
    assert questions[1]["grammar_id"] == str(new_grammar.id)


def test_session_skips_due_item_with_no_valid_question(client: TestClient, db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="うちに")
    make_progress(db_session, grammar, status=GrammarStatus.NEW)
    # no Question row at all for this grammar item
    db_session.commit()

    resp = client.post("/review/session", json={"size": 10})
    assert resp.status_code == 200
    assert resp.json() == {"questions": []}


def test_session_marks_served_question_used(client: TestClient, db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="うちに")
    make_progress(db_session, grammar, status=GrammarStatus.NEW)
    question = make_question(db_session, grammar)
    db_session.commit()
    assert question.used_count == 0

    resp = client.post("/review/session", json={"size": 10})
    assert resp.status_code == 200

    refreshed = db_session.get(Question, question.id)
    assert refreshed is not None
    assert refreshed.used_count == 1


def test_session_triggers_shortage_generation(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fewer than GENERATION_SHORTAGE_THRESHOLD unused valid questions -> a background
    generation task is scheduled for that grammar item (ARCHITECTURE.md §7.1)."""
    grammar = make_grammar(db_session, target_construction="うちに")
    make_progress(db_session, grammar, status=GrammarStatus.NEW)
    make_question(db_session, grammar)  # only 1 unused valid question, threshold default is 5
    db_session.commit()

    scheduled: list[object] = []

    def fake_add_task(func: object, *args: object, **kwargs: object) -> None:
        scheduled.append(args[0] if args else None)

    monkeypatch.setattr(
        "fastapi.BackgroundTasks.add_task",
        lambda self, func, *args, **kwargs: fake_add_task(func, *args, **kwargs),
    )

    resp = client.post("/review/session", json={"size": 10})
    assert resp.status_code == 200
    assert scheduled == [grammar.id]


def test_session_no_shortage_generation_when_enough_unused_questions(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    grammar = make_grammar(db_session, target_construction="うちに")
    make_progress(db_session, grammar, status=GrammarStatus.NEW)
    for i in range(5):  # meets GENERATION_SHORTAGE_THRESHOLD default of 5
        make_question(db_session, grammar, distractor_texts=(f"x{i}", f"y{i}", f"z{i}"))
    db_session.commit()

    scheduled: list[object] = []
    monkeypatch.setattr(
        "fastapi.BackgroundTasks.add_task",
        lambda self, func, *args, **kwargs: scheduled.append(args[0] if args else None),
    )

    resp = client.post("/review/session", json={"size": 10})
    assert resp.status_code == 200
    assert scheduled == []


def test_session_ignores_rejected_questions(client: TestClient, db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="うちに")
    make_progress(db_session, grammar, status=GrammarStatus.NEW)
    make_question(db_session, grammar, validation_status=ValidationStatus.REJECTED)
    db_session.commit()

    resp = client.post("/review/session", json={"size": 10})
    assert resp.status_code == 200
    assert resp.json() == {"questions": []}
