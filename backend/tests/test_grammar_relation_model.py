from __future__ import annotations

import pytest
from sqlalchemy import Text, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.grammar_relation import GrammarRelation, RelationSource, RelationType
from tests.conftest import make_grammar


def test_grammar_relation_roundtrips_enum_values_not_names(db_session: Session) -> None:
    """Regression test for the exact gotcha flagged for Question.source/validation_status:
    without values_callable, SQLAlchemy would persist the Python member NAME
    (e.g. "SIMILAR_MEANING") into the native Postgres enum column instead of its value
    (e.g. "similar_meaning"), which breaks silently until you read the enum back and see
    garbage or a DB-level enum-mismatch error. Reading the row back through a FRESH query
    (not the same identity-mapped Python object) is what actually exercises the real
    roundtrip through Postgres, not just SQLAlchemy's in-memory value.
    """
    a = make_grammar(db_session, target_construction="わけだ", source_note_id=9_500_001)
    b = make_grammar(db_session, target_construction="わけではない", source_note_id=9_500_002)
    relation = GrammarRelation(
        grammar_id=a.id,
        related_grammar_id=b.id,
        relation_type=RelationType.SIMILAR_FORM,
        strength=0.9,
        source=RelationSource.HEURISTIC,
        note="shared わけ stem",
    )
    a_id = a.id
    db_session.add(relation)
    db_session.commit()
    db_session.expunge_all()  # force a real reload from the DB row, not the cached Python object

    reloaded = db_session.scalars(select(GrammarRelation).where(GrammarRelation.grammar_id == a_id)).one()
    assert reloaded.relation_type is RelationType.SIMILAR_FORM
    assert reloaded.source is RelationSource.HEURISTIC

    # Also assert the raw column value stored in Postgres is the lowercase enum VALUE, not
    # the uppercase Python member name — the actual failure mode without values_callable.
    raw_value = db_session.execute(
        select(GrammarRelation.relation_type.cast(Text)).where(GrammarRelation.grammar_id == a_id)
    ).scalar_one()
    assert raw_value == "similar_form"


def test_self_loop_rejected_by_check_constraint(db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="のに", source_note_id=9_500_003)
    db_session.flush()
    relation = GrammarRelation(
        grammar_id=a.id,
        related_grammar_id=a.id,
        relation_type=RelationType.RELATED,
        strength=1.0,
        source=RelationSource.MANUAL,
    )
    db_session.add(relation)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()  # required after an IntegrityError before the session is usable again
