from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.grammar_progress import GrammarProgress, GrammarStatus
from app.services.production import check_sentence, normalize, plain_text, split_pattern_text
from tests.conftest import make_grammar, make_progress


def test_normalize_folds_width_whitespace_and_trailing_punctuation() -> None:
    assert normalize("  ｱｲ ウエ。 ") == "アイウエ"


@pytest.mark.parametrize(
    ("answer", "target", "match"),
    [
        ("気がつかないうちに外は暗くなった。", "うちに", "exact"),
        ("先生に本をいただいた。", "いただきました", "stem"),
        ("私は毎日学校に行きます。", "うちに", "none"),
        ("", "うちに", "empty"),
        ("hello world", "うちに", "empty"),
    ],
)
def test_check_sentence_match_kinds(answer: str, target: str, match: str) -> None:
    assert check_sentence(answer, target).match == match


def test_short_targets_never_stem_match() -> None:
    # 3-char target: a stem would be too short to be meaningful, so exact match only.
    assert check_sentence("ため息をついた。", "ために").match == "none"


def test_too_short_flags_bare_construction() -> None:
    assert check_sentence("うちに", "うちに").too_short is True
    assert check_sentence("寝ているうちに朝になった。", "うちに").too_short is False


def test_check_sentence_empty_target_is_none() -> None:
    assert check_sentence("私は学生です。", "").match == "none"


def test_split_pattern_text_handles_convention_and_fallback() -> None:
    assert split_pattern_text("Паттерн: V+うちに\nЗначение: пока") == ("V+うちに", "пока")
    assert split_pattern_text("свободный текст") == ("свободный текст", "")


def test_plain_text_strips_ruby_and_tags() -> None:
    assert plain_text("гл.<ruby>辞書<rt>じしょ</rt></ruby><ruby>形<rt>けい</rt></ruby>+<b>うちに</b>") == "гл.辞書形+うちに"


def test_session_returns_prompts_without_leaking_target(client: TestClient, db_session: Session) -> None:
    g = make_grammar(db_session, target_construction="うちに", pattern_text="Паттерн: V+うちに\nЗначение: пока")
    make_progress(db_session, g, status=GrammarStatus.NEW)
    db_session.commit()

    resp = client.post("/production/session", json={"size": 5})
    assert resp.status_code == 200
    prompts = resp.json()["prompts"]
    assert len(prompts) == 1
    assert prompts[0]["grammar_id"] == str(g.id)
    assert prompts[0]["pattern_hint"] == "V+うちに"
    assert prompts[0]["meaning_hint"] == "пока"
    assert "target_construction" not in prompts[0]
    assert "model_sentence_html" not in prompts[0]


def test_session_prefers_due_then_tops_up_and_respects_level(client: TestClient, db_session: Session) -> None:
    now = datetime.now(timezone.utc)
    due = make_grammar(db_session, target_construction="期限", source_note_id=9_700_001, level="N4")
    later = make_grammar(db_session, target_construction="後で", source_note_id=9_700_002, level="N4")
    other_level = make_grammar(db_session, target_construction="別", source_note_id=9_700_003, level="N2")
    make_progress(db_session, due, status=GrammarStatus.REVIEW, next_review=now - timedelta(days=2))
    make_progress(db_session, later, status=GrammarStatus.REVIEW, next_review=now + timedelta(days=9))
    make_progress(db_session, other_level, status=GrammarStatus.REVIEW, next_review=now - timedelta(days=5))
    db_session.commit()

    body = client.post("/production/session", json={"size": 5, "level": "N4"}).json()
    ids = [p["grammar_id"] for p in body["prompts"]]
    assert ids[0] == str(due.id)  # overdue first
    assert set(ids) == {str(due.id), str(later.id)}  # topped up from not-due, N2 excluded


def test_session_skips_items_without_usable_example(client: TestClient, db_session: Session) -> None:
    g = make_grammar(db_session, target_construction="", source_note_id=9_700_010)
    make_progress(db_session, g)
    db_session.commit()
    assert client.post("/production/session", json={"size": 5}).json() == {"prompts": []}


def test_check_reveals_model_sentence_and_does_not_touch_progress(
    client: TestClient, db_session: Session
) -> None:
    g = make_grammar(db_session, target_construction="うちに")
    progress = make_progress(db_session, g, status=GrammarStatus.NEW)
    db_session.commit()
    before = (progress.repetitions, progress.status, progress.next_review)

    resp = client.post(
        "/production/check", json={"grammar_id": str(g.id), "answer": "寝ているうちに朝になった。"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["match"] == "exact"
    assert body["too_short"] is False
    assert body["target_construction"] == "うちに"
    assert body["model_sentence_clean"] == g.expression_clean

    db_session.refresh(progress)
    assert (progress.repetitions, progress.status, progress.next_review) == before
    assert db_session.scalar(select(func.count()).select_from(GrammarProgress)) == 1


def test_check_unknown_grammar_is_404(client: TestClient) -> None:
    resp = client.post(
        "/production/check", json={"grammar_id": "00000000-0000-0000-0000-000000000000", "answer": "テスト"}
    )
    assert resp.status_code == 404


def test_check_rejects_oversized_answer(client: TestClient, db_session: Session) -> None:
    g = make_grammar(db_session, target_construction="うちに")
    db_session.commit()
    resp = client.post("/production/check", json={"grammar_id": str(g.id), "answer": "あ" * 501})
    assert resp.status_code == 422
