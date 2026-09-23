"""Tests for the V4 slice's `level` filter across GET /grammar, POST /review/session, and
GET /stats. See ARCHITECTURE.md "V4 Slice" §V4.4.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.grammar_progress import GrammarStatus
from app.models.grammar_relation import RelationType
from tests.conftest import make_grammar, make_progress, make_relation


def test_list_grammar_level_filter(client: TestClient, db_session: Session) -> None:
    g_n3 = make_grammar(db_session, target_construction="わけだ", source_note_id=9_900_001, level="N3")
    make_progress(db_session, g_n3)
    g_n4 = make_grammar(db_session, target_construction="間に", source_note_id=9_900_002, level="N4")
    make_progress(db_session, g_n4)
    g_n2 = make_grammar(db_session, target_construction="に際して", source_note_id=9_900_003, level="N2")
    make_progress(db_session, g_n2)
    db_session.commit()

    resp = client.get("/grammar")
    assert resp.status_code == 200
    assert resp.json()["total"] == 3

    resp = client.get("/grammar", params={"level": "N4"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["target_construction"] == "間に"

    resp = client.get("/grammar", params={"level": "N2"})
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["target_construction"] == "に際して"


def test_review_session_level_filter_due_mode(client: TestClient, db_session: Session) -> None:
    from tests.conftest import make_question

    now = datetime.now(timezone.utc)
    g_n3 = make_grammar(db_session, target_construction="わけだ", source_note_id=9_900_101, level="N3")
    make_progress(db_session, g_n3, next_review=now - timedelta(days=1))
    make_question(db_session, g_n3)

    g_n4 = make_grammar(db_session, target_construction="間に", source_note_id=9_900_102, level="N4")
    make_progress(db_session, g_n4, next_review=now - timedelta(days=1))
    make_question(db_session, g_n4)
    db_session.commit()

    resp = client.post("/review/session", json={"size": 5, "mode": "due", "level": "N4"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["questions"]) == 1
    assert body["questions"][0]["grammar_id"] == str(g_n4.id)


def test_review_session_level_filter_weak_points_mode(client: TestClient, db_session: Session) -> None:
    from tests.conftest import make_question

    g_n3 = make_grammar(db_session, target_construction="わけだ", source_note_id=9_900_201, level="N3")
    p_n3 = make_progress(db_session, g_n3)
    p_n3.repetitions = 3
    p_n3.application_score = 0.1
    p_n3.discrimination_score = 0.1
    make_question(db_session, g_n3)

    g_n4 = make_grammar(db_session, target_construction="間に", source_note_id=9_900_202, level="N4")
    p_n4 = make_progress(db_session, g_n4)
    p_n4.repetitions = 3
    p_n4.application_score = 0.1
    p_n4.discrimination_score = 0.1
    make_question(db_session, g_n4)
    db_session.commit()

    resp = client.post("/review/session", json={"size": 5, "mode": "weak_points", "level": "N3"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["questions"]) == 1
    assert body["questions"][0]["grammar_id"] == str(g_n3.id)


def test_review_session_level_filter_confusion_mode(client: TestClient, db_session: Session) -> None:
    from tests.conftest import make_question

    a_n3 = make_grammar(db_session, target_construction="わけだ", source_note_id=9_900_301, level="N3")
    make_progress(db_session, a_n3)
    make_question(db_session, a_n3)
    b_n3 = make_grammar(db_session, target_construction="わけではない", source_note_id=9_900_302, level="N3")
    make_progress(db_session, b_n3)
    make_question(db_session, b_n3)
    make_relation(db_session, a_n3, b_n3, relation_type=RelationType.COMMONLY_CONFUSED, strength=0.9)

    a_n4 = make_grammar(db_session, target_construction="間に", source_note_id=9_900_303, level="N4")
    make_progress(db_session, a_n4)
    make_question(db_session, a_n4)
    b_n4 = make_grammar(db_session, target_construction="うちに", source_note_id=9_900_304, level="N4")
    make_progress(db_session, b_n4)
    make_question(db_session, b_n4)
    make_relation(db_session, a_n4, b_n4, relation_type=RelationType.COMMONLY_CONFUSED, strength=0.9)
    db_session.commit()

    resp = client.post("/review/session", json={"size": 5, "mode": "confusion", "level": "N3"})
    assert resp.status_code == 200
    grammar_ids = {q["grammar_id"] for q in resp.json()["questions"]}
    assert grammar_ids == {str(a_n3.id), str(b_n3.id)}


def test_stats_level_filter_scopes_counts_and_total_items(client: TestClient, db_session: Session) -> None:
    g_n3 = make_grammar(db_session, target_construction="わけだ", source_note_id=9_900_401, level="N3")
    make_progress(db_session, g_n3, status=GrammarStatus.NEW)
    g_n4_a = make_grammar(db_session, target_construction="間に", source_note_id=9_900_402, level="N4")
    make_progress(db_session, g_n4_a, status=GrammarStatus.NEW)
    g_n4_b = make_grammar(db_session, target_construction="うちに", source_note_id=9_900_403, level="N4")
    make_progress(db_session, g_n4_b, status=GrammarStatus.LEARNING)
    db_session.commit()

    resp = client.get("/stats")
    assert resp.status_code == 200
    assert resp.json()["total_items"] == 3

    resp = client.get("/stats", params={"level": "N4"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_items"] == 2
    assert body["new_count"] == 1
    assert body["learning_count"] == 1

    resp = client.get("/stats", params={"level": "N3"})
    body = resp.json()
    assert body["total_items"] == 1
    assert body["new_count"] == 1
    assert body["learning_count"] == 0
