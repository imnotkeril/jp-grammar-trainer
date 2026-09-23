from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress, GrammarStatus
from app.scripts.seed_import_authored import (
    _coerce_formation_rules,
    _coerce_tags,
    _import_one_file,
    _validate_target_construction,
    compute_source_note_id,
    default_seed_paths,
)
from tests.conftest import requires_db

# --- Pure-function unit tests (no DB needed) -------------------------------------------------


def test_compute_source_note_id_deterministic() -> None:
    a = compute_source_note_id("N4", "n4_012_aida")
    b = compute_source_note_id("N4", "n4_012_aida")
    assert a == b
    assert a > 0


def test_compute_source_note_id_differs_by_level_and_key() -> None:
    base = compute_source_note_id("N4", "n4_012_aida")
    assert compute_source_note_id("N2", "n4_012_aida") != base
    assert compute_source_note_id("N4", "n4_013_other") != base


def test_default_seed_paths_points_at_data_seed() -> None:
    paths = default_seed_paths()
    assert [p.name for p in paths] == ["n4_grammar_authored.json", "n2_grammar_authored.json"]
    assert all(p.parent.name == "seed" for p in paths)


def test_coerce_tags_narrows_object_to_list_of_str() -> None:
    assert _coerce_tags(["N4", "time", "lesson:na"]) == ["N4", "time", "lesson:na"]
    assert _coerce_tags(None) == []
    assert _coerce_tags("not-a-list") == []


def test_coerce_formation_rules_narrows_object_to_list_of_dict_str_str() -> None:
    raw = [{"pos": "гл.ている", "form_label": "гл.ている", "example_html": "<b>間</b>"}, "not-a-dict"]
    result = _coerce_formation_rules(raw)
    assert result == [{"pos": "гл.ている", "form_label": "гл.ている", "example_html": "<b>間</b>"}]


def test_validate_target_construction() -> None:
    assert _validate_target_construction("にほんにいるあいだにのぼる", "あいだに")
    assert not _validate_target_construction("にほんにいるあいだにのぼる", "うちに")


# --- Integration tests against a fixture JSON file (mirrors real V4.1 schema) -----------------

_FIXTURE_ITEM: dict[str, object] = {
    "key": "n4_test_aida",
    "expression_html": (
        "<ruby>日本<rt>にほん</rt></ruby>にいる<b>間</b>に"
        "<ruby>一度富士山<rt>いちどふじさん</rt></ruby>に<ruby>登<rt>のぼ</rt></ruby>ってみたい。"
    ),
    "reading": "にほんにいる<b>あいだ</b>に いちど ふじさんに のぼってみたい。",
    "meaning_ru": "Пока я в Японии, хочу хоть раз подняться на Фудзи.",
    "pattern_text": "Паттерн: [期間/状態] + 間（に） (N4)\nЗначение: тест",
    "formation_rules": [
        {"pos": "сущ.の", "form_label": "сущ.の", "example_html": "<b>間</b>"},
    ],
    "target_construction": "間に",
    "tags": ["N4", "time", "lesson:na"],
}


def _write_fixture(
    tmp_path: Path, items: list[dict[str, object]], level: str = "N4", name: str = "fixture.json"
) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"level": level, "items": items}, ensure_ascii=False), encoding="utf-8")
    return path


@requires_db
def test_import_one_file_inserts_grammar_and_progress(db_session: Session, tmp_path: Path) -> None:
    path = _write_fixture(tmp_path, [_FIXTURE_ITEM])

    report = _import_one_file(db_session, path)
    db_session.commit()

    assert report["level"] == "N4"
    assert report["total"] == 1
    assert report["inserted"] == 1
    assert report["updated"] == 0
    assert report["anomalies"] == []

    expected_id = compute_source_note_id("N4", "n4_test_aida")
    grammar = db_session.scalar(select(Grammar).where(Grammar.source_note_id == expected_id))
    assert grammar is not None
    assert grammar.level == "N4"
    assert grammar.target_construction == "間に"
    assert grammar.tags == ["N4", "time", "lesson:na"]
    assert grammar.formation_rules == [{"pos": "сущ.の", "form_label": "сущ.の", "example_html": "<b>間</b>"}]

    progress = db_session.scalar(select(GrammarProgress).where(GrammarProgress.grammar_id == grammar.id))
    assert progress is not None
    assert progress.status.value == "new"


@requires_db
def test_import_one_file_is_idempotent_and_never_resets_progress(db_session: Session, tmp_path: Path) -> None:
    path = _write_fixture(tmp_path, [_FIXTURE_ITEM])

    first = _import_one_file(db_session, path)
    db_session.commit()
    assert first["inserted"] == 1

    expected_id = compute_source_note_id("N4", "n4_test_aida")
    grammar = db_session.scalar(select(Grammar).where(Grammar.source_note_id == expected_id))
    assert grammar is not None
    progress = db_session.scalar(select(GrammarProgress).where(GrammarProgress.grammar_id == grammar.id))
    assert progress is not None
    progress.status = GrammarStatus.REVIEW
    db_session.commit()

    # Re-run on the identical file: upserts the same row (source_note_id unchanged), never
    # touches grammar_progress (§V4.2 step 5).
    second = _import_one_file(db_session, path)
    db_session.commit()
    assert second["inserted"] == 0
    assert second["updated"] == 1

    grammars = list(db_session.scalars(select(Grammar).where(Grammar.source_note_id == expected_id)))
    assert len(grammars) == 1

    progress_after = db_session.scalar(select(GrammarProgress).where(GrammarProgress.grammar_id == grammar.id))
    assert progress_after is not None
    assert progress_after.status.value == "review"  # untouched by the re-import


@requires_db
def test_import_one_file_updates_content_on_edit(db_session: Session, tmp_path: Path) -> None:
    path = _write_fixture(tmp_path, [_FIXTURE_ITEM])
    _import_one_file(db_session, path)
    db_session.commit()

    edited_item = dict(_FIXTURE_ITEM)
    edited_item["meaning_ru"] = "Обновлённый перевод."
    path2 = _write_fixture(tmp_path, [edited_item])

    report = _import_one_file(db_session, path2)
    db_session.commit()
    assert report["updated"] == 1

    expected_id = compute_source_note_id("N4", "n4_test_aida")
    grammar = db_session.scalar(select(Grammar).where(Grammar.source_note_id == expected_id))
    assert grammar is not None
    assert grammar.meaning_ru == "Обновлённый перевод."


@requires_db
def test_import_one_file_flags_target_construction_mismatch_but_still_imports(
    db_session: Session, tmp_path: Path
) -> None:
    bad_item = dict(_FIXTURE_ITEM)
    bad_item["key"] = "n4_test_mismatch"
    bad_item["target_construction"] = "存在しない構文"
    path = _write_fixture(tmp_path, [bad_item])

    report = _import_one_file(db_session, path)
    db_session.commit()

    assert report["inserted"] == 1  # not blocked
    assert len(report["anomalies"]) == 1
    assert report["anomalies"][0]["type"] == "target_construction_mismatch"
    assert report["anomalies"][0]["key"] == "n4_test_mismatch"


@requires_db
def test_import_one_file_flags_malformed_rt_payload(db_session: Session, tmp_path: Path) -> None:
    bad_item = dict(_FIXTURE_ITEM)
    bad_item["key"] = "n4_test_bad_rt"
    bad_item["expression_html"] = "<ruby>もの<rt>ものvs<b>こと</b>の違い</rt></ruby><b>間</b>"
    path = _write_fixture(tmp_path, [bad_item])

    report = _import_one_file(db_session, path)
    db_session.commit()

    assert report["inserted"] == 1
    anomaly_types = {a["type"] for a in report["anomalies"]}
    assert "malformed_rt_payload" in anomaly_types


@requires_db
def test_import_one_file_n3_and_n4_keys_never_collide(db_session: Session, tmp_path: Path) -> None:
    """Two files, same `key`, different `level` — ADR-21's hash is over (level, key)
    together, so these must resolve to two distinct Grammar rows, not one."""
    n4_item = dict(_FIXTURE_ITEM)
    n2_item = dict(_FIXTURE_ITEM)
    n4_path = _write_fixture(tmp_path, [n4_item], level="N4", name="n4.json")
    n2_path = _write_fixture(tmp_path, [n2_item], level="N2", name="n2.json")

    _import_one_file(db_session, n4_path)
    _import_one_file(db_session, n2_path)
    db_session.commit()

    rows = list(db_session.scalars(select(Grammar).where(Grammar.target_construction == "間に")))
    assert len(rows) == 2
    assert {r.level for r in rows} == {"N4", "N2"}
