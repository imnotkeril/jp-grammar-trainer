from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.grammar_progress import GrammarStatus
from app.models.grammar_relation import RelationType
from app.services.review import (
    select_confusion_progress,
    select_due_progress_mixed,
    select_weak_progress,
)
from tests.conftest import make_grammar, make_progress, make_question, make_relation


def test_select_confusion_progress_returns_only_edge_connected_items(db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="うちに", source_note_id=9_500_001)
    b = make_grammar(db_session, target_construction="あいだに", source_note_id=9_500_002)
    isolated = make_grammar(db_session, target_construction="からには", source_note_id=9_500_003)
    make_progress(db_session, a, status=GrammarStatus.REVIEW)
    make_progress(db_session, b, status=GrammarStatus.REVIEW)
    make_progress(db_session, isolated, status=GrammarStatus.REVIEW)
    make_relation(db_session, a, b, relation_type=RelationType.COMMONLY_CONFUSED, strength=0.9)
    db_session.commit()

    result = select_confusion_progress(db_session, 10)
    result_ids = {p.grammar_id for p in result}
    assert result_ids == {a.id, b.id}
    assert isolated.id not in result_ids


def test_select_confusion_progress_includes_similar_form_edges(db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="うちに", source_note_id=9_500_010)
    b = make_grammar(db_session, target_construction="あいだに", source_note_id=9_500_011)
    make_progress(db_session, a, status=GrammarStatus.REVIEW)
    make_progress(db_session, b, status=GrammarStatus.REVIEW)
    make_relation(db_session, a, b, relation_type=RelationType.SIMILAR_FORM, strength=0.5)
    db_session.commit()

    result = select_confusion_progress(db_session, 10)
    assert {p.grammar_id for p in result} == {a.id, b.id}


def test_select_confusion_progress_ignores_unrelated_relation_types(db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="うちに", source_note_id=9_500_020)
    b = make_grammar(db_session, target_construction="あいだに", source_note_id=9_500_021)
    make_progress(db_session, a, status=GrammarStatus.REVIEW)
    make_progress(db_session, b, status=GrammarStatus.REVIEW)
    make_relation(db_session, a, b, relation_type=RelationType.SIMILAR_MEANING, strength=0.9)
    db_session.commit()

    assert select_confusion_progress(db_session, 10) == []


def test_select_confusion_progress_respects_size_and_strength_order(db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="A", source_note_id=9_500_030)
    b = make_grammar(db_session, target_construction="B", source_note_id=9_500_031)
    c = make_grammar(db_session, target_construction="C", source_note_id=9_500_032)
    d = make_grammar(db_session, target_construction="D", source_note_id=9_500_033)
    for g in (a, b, c, d):
        make_progress(db_session, g, status=GrammarStatus.REVIEW)
    make_relation(db_session, a, b, relation_type=RelationType.COMMONLY_CONFUSED, strength=0.9)
    make_relation(db_session, c, d, relation_type=RelationType.COMMONLY_CONFUSED, strength=0.2)
    db_session.commit()

    result = select_confusion_progress(db_session, 2)
    assert len(result) == 2
    assert {p.grammar_id for p in result} == {a.id, b.id}


def test_select_weak_progress_excludes_never_attempted(db_session: Session) -> None:
    attempted = make_grammar(db_session, target_construction="うちに", source_note_id=9_500_040)
    never_attempted = make_grammar(db_session, target_construction="あいだに", source_note_id=9_500_041)
    progress = make_progress(db_session, attempted, status=GrammarStatus.REVIEW)
    progress.repetitions = 3
    progress.application_score = 0.1
    progress.discrimination_score = 0.1
    make_progress(db_session, never_attempted, status=GrammarStatus.NEW)  # repetitions=0
    db_session.commit()

    result = select_weak_progress(db_session, 10)
    assert {p.grammar_id for p in result} == {attempted.id}


def test_select_weak_progress_orders_ascending_by_combined_score(db_session: Session) -> None:
    strong = make_grammar(db_session, target_construction="強い", source_note_id=9_500_050)
    weak = make_grammar(db_session, target_construction="弱い", source_note_id=9_500_051)
    strong_p = make_progress(db_session, strong, status=GrammarStatus.REVIEW)
    strong_p.repetitions = 3
    strong_p.application_score = 0.9
    strong_p.discrimination_score = 0.9
    weak_p = make_progress(db_session, weak, status=GrammarStatus.REVIEW)
    weak_p.repetitions = 3
    weak_p.application_score = 0.1
    weak_p.discrimination_score = 0.1
    db_session.commit()

    result = select_weak_progress(db_session, 10)
    assert [p.grammar_id for p in result] == [weak.id, strong.id]


def test_select_weak_progress_excludes_given_ids(db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="A", source_note_id=9_500_060)
    b = make_grammar(db_session, target_construction="B", source_note_id=9_500_061)
    for g in (a, b):
        p = make_progress(db_session, g, status=GrammarStatus.REVIEW)
        p.repetitions = 1
    db_session.commit()

    result = select_weak_progress(db_session, 10, exclude_ids=frozenset({a.id}))
    assert {p.grammar_id for p in result} == {b.id}


def test_select_due_progress_mixed_reserves_weak_slots(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    due_items = []
    for i in range(8):
        g = make_grammar(db_session, target_construction=f"due{i}", source_note_id=9_500_100 + i)
        p = make_progress(db_session, g, status=GrammarStatus.REVIEW, next_review=now - timedelta(days=1))
        due_items.append(p)

    weak_ids = []
    for i in range(2):
        weak = make_grammar(db_session, target_construction=f"weak{i}", source_note_id=9_500_200 + i)
        weak_p = make_progress(
            db_session, weak, status=GrammarStatus.REVIEW, next_review=now + timedelta(days=30)
        )
        weak_p.repetitions = 5
        weak_p.application_score = 0.0
        weak_p.discrimination_score = 0.0
        weak_ids.append(weak.id)
    db_session.commit()

    result = select_due_progress_mixed(db_session, 10, now)
    result_ids = {p.grammar_id for p in result}
    assert len(result) == 10
    # not due (next_review in future) but pulled in as the 2 reserved weak slots (10*0.2)
    assert set(weak_ids).issubset(result_ids)


def test_select_due_progress_mixed_no_mixin_below_size_5(db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    for i in range(5):
        g = make_grammar(db_session, target_construction=f"due{i}", source_note_id=9_500_300 + i)
        make_progress(db_session, g, status=GrammarStatus.REVIEW, next_review=now - timedelta(days=1))

    weak = make_grammar(db_session, target_construction="weak", source_note_id=9_500_400)
    weak_p = make_progress(db_session, weak, status=GrammarStatus.REVIEW, next_review=now + timedelta(days=30))
    weak_p.repetitions = 5
    weak_p.application_score = 0.0
    weak_p.discrimination_score = 0.0
    db_session.commit()

    result = select_due_progress_mixed(db_session, 5, now)
    result_ids = {p.grammar_id for p in result}
    assert weak.id not in result_ids  # size < 5 -> no mix-in slot reserved
    assert len(result) == 5


def test_session_endpoint_confusion_mode(client: TestClient, db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="うちに", source_note_id=9_500_500)
    b = make_grammar(db_session, target_construction="あいだに", source_note_id=9_500_501)
    make_progress(db_session, a, status=GrammarStatus.REVIEW)
    make_progress(db_session, b, status=GrammarStatus.REVIEW)
    make_question(db_session, a)
    make_question(db_session, b)
    make_relation(db_session, a, b, relation_type=RelationType.COMMONLY_CONFUSED, strength=0.9)
    db_session.commit()

    resp = client.post("/review/session", json={"size": 10, "mode": "confusion"})
    assert resp.status_code == 200
    body = resp.json()
    grammar_ids = {q["grammar_id"] for q in body["questions"]}
    assert grammar_ids == {str(a.id), str(b.id)}


def test_session_endpoint_weak_points_mode(client: TestClient, db_session: Session) -> None:
    weak = make_grammar(db_session, target_construction="弱い", source_note_id=9_500_600)
    weak_p = make_progress(db_session, weak, status=GrammarStatus.REVIEW)
    weak_p.repetitions = 3
    weak_p.application_score = 0.1
    weak_p.discrimination_score = 0.1
    make_question(db_session, weak)

    never_attempted = make_grammar(db_session, target_construction="新規", source_note_id=9_500_601)
    make_progress(db_session, never_attempted, status=GrammarStatus.NEW)
    make_question(db_session, never_attempted)
    db_session.commit()

    resp = client.post("/review/session", json={"size": 10, "mode": "weak_points"})
    assert resp.status_code == 200
    body = resp.json()
    grammar_ids = {q["grammar_id"] for q in body["questions"]}
    assert grammar_ids == {str(weak.id)}
