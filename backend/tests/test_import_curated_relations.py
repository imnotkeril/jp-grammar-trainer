from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.grammar_relation import GrammarRelation, RelationSource, RelationType
from app.scripts.import_curated_relations import (
    _as_dict,
    _direction_to_columns,
    _resolve_reference,
    default_seed_paths,
    run_import,
)
from app.scripts.seed_import_authored import compute_source_note_id
from tests.conftest import make_grammar, make_relation, requires_db

# --- Pure-function unit tests -----------------------------------------------------------------


def test_as_dict_narrows_object_to_dict() -> None:
    assert _as_dict({"level": "N3", "key": "x"}) == {"level": "N3", "key": "x"}


def test_as_dict_rejects_non_dict() -> None:
    with pytest.raises(TypeError):
        _as_dict("not-a-dict")


def test_direction_to_columns_symmetric_canonicalizes_by_sorted_id() -> None:
    a, b = _direction_to_columns(RelationType.COMMONLY_CONFUSED, "b-id", "a-id", None)
    assert (a, b) == ("a-id", "b-id")


def test_direction_to_columns_directional_default_a_to_b() -> None:
    a, b = _direction_to_columns(RelationType.PREREQUISITE, "a-id", "b-id", None)
    assert (a, b) == ("a-id", "b-id")


def test_direction_to_columns_directional_b_to_a() -> None:
    a, b = _direction_to_columns(RelationType.PREREQUISITE, "a-id", "b-id", "b_to_a")
    assert (a, b) == ("b-id", "a-id")


def test_default_seed_paths_only_matches_relations_curated_glob() -> None:
    # default_seed_paths() derives repo_root from this module's own __file__ (3 parents up),
    # so it isn't practical to redirect it at a tmp_path fixture — instead confirm against the
    # real repo's data/seed dir that whatever it returns only ever matches the
    # relations_curated_* glob (never, say, a *_grammar_authored.json file).
    paths = default_seed_paths()
    assert isinstance(paths, list)
    assert all(p.name.startswith("relations_curated_") for p in paths)


# --- Reference resolution (DB-backed) -----------------------------------------------------------


@requires_db
def test_resolve_reference_by_key_for_authored_levels(db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="間に", source_note_id=compute_source_note_id("N4", "k1"))
    db_session.commit()

    resolved = _resolve_reference(db_session, {"level": "N4", "key": "k1"})
    assert resolved is not None
    assert resolved.id == grammar.id


@requires_db
def test_resolve_reference_by_target_construction_for_n3(db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="わけだ", source_note_id=9_800_001, level="N3")
    db_session.commit()

    resolved = _resolve_reference(db_session, {"level": "N3", "target_construction": "わけだ"})
    assert resolved is not None
    assert resolved.id == grammar.id


@requires_db
def test_resolve_reference_by_expression_clean_fallback_for_empty_target(db_session: Session) -> None:
    grammar = make_grammar(db_session, target_construction="", source_note_id=9_800_002, level="N3")
    grammar.expression_clean = "ある特定の文"
    db_session.commit()

    # target_construction absent -> falls back to expression_clean
    resolved = _resolve_reference(db_session, {"level": "N3", "expression_clean": "ある特定の文"})
    assert resolved is not None
    assert resolved.id == grammar.id


@requires_db
def test_resolve_reference_returns_none_when_unresolved(db_session: Session) -> None:
    assert _resolve_reference(db_session, {"level": "N3", "target_construction": "存在しない"}) is None
    assert _resolve_reference(db_session, {"level": "N4", "key": "no_such_key"}) is None


@requires_db
def test_resolve_reference_returns_none_on_ambiguous_match(db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="に際して", source_note_id=9_800_005, level="N3")
    b = make_grammar(db_session, target_construction="に際し", source_note_id=9_800_006, level="N3")
    a.expression_clean = "同じ表現"
    b.expression_clean = "同じ表現"
    db_session.commit()

    assert _resolve_reference(db_session, {"level": "N3", "expression_clean": "同じ表現"}) is None


# --- run_import integration tests (ADR-22 precedence + idempotency) ----------------------------


def _write_edges_file(tmp_path: Path, edges: list[dict[str, object]], name: str = "relations_curated_test.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"edges": edges}, ensure_ascii=False), encoding="utf-8")
    return path


@requires_db
def test_run_import_curated_edge_supersedes_heuristic_and_llm_rows_for_same_pair(
    db_session: Session, tmp_path: Path
) -> None:
    a = make_grammar(db_session, target_construction="わけだ", source_note_id=9_810_001, level="N3")
    b = make_grammar(db_session, target_construction="わけではない", source_note_id=9_810_002, level="N3")
    make_relation(db_session, a, b, relation_type=RelationType.RELATED, source=RelationSource.HEURISTIC)
    db_session.commit()

    edges: list[dict[str, object]] = [
        {
            "a": {"level": "N3", "target_construction": "わけだ"},
            "b": {"level": "N3", "target_construction": "わけではない"},
            "relation_type": "commonly_confused",
            "strength": 0.95,
            "note": "classic confusion pair",
        }
    ]
    path = _write_edges_file(tmp_path, edges)

    report = run_import(db_session, [path])

    assert report["resolved"] == 1
    assert report["unresolved"] == []
    assert report["heuristic_rows_replaced"] == 1
    assert report["inserted"] == 1

    rows = list(
        db_session.scalars(
            select(GrammarRelation).where(
                GrammarRelation.grammar_id.in_([a.id, b.id]), GrammarRelation.related_grammar_id.in_([a.id, b.id])
            )
        )
    )
    assert len(rows) == 1
    assert rows[0].source == RelationSource.MANUAL
    assert rows[0].relation_type == RelationType.COMMONLY_CONFUSED
    assert rows[0].note == "classic confusion pair"


@requires_db
def test_run_import_leaves_uncovered_heuristic_pairs_alone(db_session: Session, tmp_path: Path) -> None:
    a = make_grammar(db_session, target_construction="ものの", source_note_id=9_810_101, level="N3")
    b = make_grammar(db_session, target_construction="とはいえ", source_note_id=9_810_102, level="N3")
    make_relation(db_session, a, b, relation_type=RelationType.RELATED, source=RelationSource.HEURISTIC)
    db_session.commit()

    make_grammar(db_session, target_construction="わけだ", source_note_id=9_810_103, level="N3")
    make_grammar(db_session, target_construction="わけではない", source_note_id=9_810_104, level="N3")
    edges: list[dict[str, object]] = [
        {
            "a": {"level": "N3", "target_construction": "わけだ"},
            "b": {"level": "N3", "target_construction": "わけではない"},
            "relation_type": "commonly_confused",
        }
    ]
    path = _write_edges_file(tmp_path, edges)

    run_import(db_session, [path])

    untouched = db_session.scalar(
        select(GrammarRelation).where(GrammarRelation.grammar_id == a.id, GrammarRelation.related_grammar_id == b.id)
    )
    assert untouched is not None
    assert untouched.source == RelationSource.HEURISTIC


@requires_db
def test_run_import_rejects_self_loops(db_session: Session, tmp_path: Path) -> None:
    make_grammar(db_session, target_construction="わけだ", source_note_id=9_810_201, level="N3")
    db_session.commit()

    edges: list[dict[str, object]] = [
        {
            "a": {"level": "N3", "target_construction": "わけだ"},
            "b": {"level": "N3", "target_construction": "わけだ"},
            "relation_type": "related",
        }
    ]
    path = _write_edges_file(tmp_path, edges)

    report = run_import(db_session, [path])
    assert report["self_loops_rejected"] == 1
    assert report["inserted"] == 0


@requires_db
def test_run_import_flags_unresolved_reference(db_session: Session, tmp_path: Path) -> None:
    make_grammar(db_session, target_construction="わけだ", source_note_id=9_810_301, level="N3")
    db_session.commit()

    edges: list[dict[str, object]] = [
        {
            "a": {"level": "N3", "target_construction": "わけだ"},
            "b": {"level": "N3", "target_construction": "存在しない構文"},
            "relation_type": "related",
        }
    ]
    path = _write_edges_file(tmp_path, edges)

    report = run_import(db_session, [path])
    assert report["resolved"] == 0
    assert len(report["unresolved"]) == 1
    assert report["unresolved"][0]["side"] == "b"


@requires_db
def test_run_import_is_idempotent_on_rerun(db_session: Session, tmp_path: Path) -> None:
    make_grammar(db_session, target_construction="わけだ", source_note_id=9_810_401, level="N3")
    make_grammar(db_session, target_construction="わけではない", source_note_id=9_810_402, level="N3")
    db_session.commit()

    edges: list[dict[str, object]] = [
        {
            "a": {"level": "N3", "target_construction": "わけだ"},
            "b": {"level": "N3", "target_construction": "わけではない"},
            "relation_type": "commonly_confused",
            "strength": 0.9,
        }
    ]
    path = _write_edges_file(tmp_path, edges)

    first = run_import(db_session, [path])
    assert first["inserted"] == 1
    assert first["updated"] == 0

    second = run_import(db_session, [path])
    assert second["inserted"] == 0
    assert second["updated"] == 1

    rows = list(db_session.scalars(select(GrammarRelation).where(GrammarRelation.source == RelationSource.MANUAL)))
    assert len(rows) == 1


@requires_db
def test_run_import_resolves_cross_level_edge_by_key_and_target_construction(
    db_session: Session, tmp_path: Path
) -> None:
    n4 = make_grammar(
        db_session, target_construction="間に", source_note_id=compute_source_note_id("N4", "n4_012_aida"), level="N4"
    )
    n3 = make_grammar(db_session, target_construction="うちに", source_note_id=9_810_501, level="N3")
    db_session.commit()

    edges: list[dict[str, object]] = [
        {
            "a": {"level": "N4", "key": "n4_012_aida"},
            "b": {"level": "N3", "target_construction": "うちに"},
            "relation_type": "advanced_version",
            "direction": "b_to_a",
            "strength": 0.85,
        }
    ]
    path = _write_edges_file(tmp_path, edges)

    report = run_import(db_session, [path])
    assert report["resolved"] == 1

    row = db_session.scalar(select(GrammarRelation).where(GrammarRelation.source == RelationSource.MANUAL))
    assert row is not None
    # direction "b_to_a" -> grammar_id = b (N3 うちに), related_grammar_id = a (N4 間に)
    assert row.grammar_id == n3.id
    assert row.related_grammar_id == n4.id
    assert row.relation_type == RelationType.ADVANCED_VERSION


@requires_db
def test_run_import_purge_remaining_heuristic_flag(db_session: Session, tmp_path: Path) -> None:
    a = make_grammar(db_session, target_construction="ものの", source_note_id=9_810_601, level="N3")
    b = make_grammar(db_session, target_construction="とはいえ", source_note_id=9_810_602, level="N3")
    make_relation(db_session, a, b, relation_type=RelationType.RELATED, source=RelationSource.HEURISTIC)
    db_session.commit()

    path = _write_edges_file(tmp_path, [])

    report = run_import(db_session, [path], purge_remaining_heuristic=True)
    assert report["purge_remaining_heuristic_ran"] is True
    assert report["heuristic_rows_purged"] == 1

    remaining = list(db_session.scalars(select(GrammarRelation).where(GrammarRelation.source == RelationSource.HEURISTIC)))
    assert remaining == []
