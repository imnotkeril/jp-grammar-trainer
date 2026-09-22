from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.grammar_progress import GrammarStatus
from tests.conftest import make_grammar, make_progress


def test_stats_empty_db(client: TestClient, db_session: Session) -> None:
    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "due_count": 0,
        "new_count": 0,
        "learning_count": 0,
        "review_count": 0,
        "mastered_count": 0,
        "recall_pct": 0.0,
        "application_avg": 0.0,
        "discrimination_avg": 0.0,
    }


def test_stats_counts_by_status_and_due(client: TestClient, db_session: Session) -> None:
    now = datetime.now(timezone.utc)

    g1 = make_grammar(db_session, target_construction="a1", source_note_id=9_300_001)
    make_progress(db_session, g1, status=GrammarStatus.NEW, next_review=now)  # due (new)

    g2 = make_grammar(db_session, target_construction="a2", source_note_id=9_300_002)
    make_progress(
        db_session, g2, status=GrammarStatus.REVIEW, next_review=now - timedelta(days=1)
    )  # due (overdue)

    g3 = make_grammar(db_session, target_construction="a3", source_note_id=9_300_003)
    make_progress(
        db_session, g3, status=GrammarStatus.MASTERED, next_review=now + timedelta(days=60)
    )  # not due

    g4 = make_grammar(db_session, target_construction="a4", source_note_id=9_300_004)
    make_progress(db_session, g4, status=GrammarStatus.LEARNING, next_review=now + timedelta(days=1))
    db_session.commit()

    resp = client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert body["due_count"] == 2
    assert body["new_count"] == 1
    assert body["review_count"] == 1
    assert body["mastered_count"] == 1
    assert body["learning_count"] == 1


def test_stats_recall_pct_reflects_recall_scores(client: TestClient, db_session: Session) -> None:
    g1 = make_grammar(db_session, target_construction="a1", source_note_id=9_300_101)
    p1 = make_progress(db_session, g1, status=GrammarStatus.REVIEW)
    p1.recall_score = 0.8

    g2 = make_grammar(db_session, target_construction="a2", source_note_id=9_300_102)
    p2 = make_progress(db_session, g2, status=GrammarStatus.REVIEW)
    p2.recall_score = 0.4
    db_session.commit()

    resp = client.get("/stats")
    assert resp.status_code == 200
    assert resp.json()["recall_pct"] == 60.0
