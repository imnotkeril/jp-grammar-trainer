from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.grammar_relation import GrammarRelation, RelationSource
from app.scripts.generate_relations import run
from tests.conftest import make_grammar


async def test_run_falls_back_to_heuristic_when_no_api_key_configured(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Core V2.4 constraint: with no ANTHROPIC/OPENAI key configured (the real state of
    backend/.env right now), the script must still produce useful heuristic-sourced rows,
    not silently no-op and not attempt to call an LLM provider.
    """
    monkeypatch.setattr("app.scripts.generate_relations.settings.anthropic_api_key", None)
    monkeypatch.setattr("app.scripts.generate_relations.settings.openai_api_key", None)

    # Mock get_provider so the test would fail loudly if the fallback path is wrong and
    # accidentally tries to call it (same mocking pattern as test_generation_trigger.py).
    def _boom() -> None:
        raise AssertionError("get_provider() must not be called when no API key is configured")

    monkeypatch.setattr("app.scripts.generate_relations.get_provider", _boom)

    make_grammar(db_session, target_construction="わけだ", meaning_ru="причина и следствие", source_note_id=9_700_001)
    make_grammar(
        db_session, target_construction="わけではない", meaning_ru="отрицание причины", source_note_id=9_700_002
    )
    make_grammar(
        db_session, target_construction="わけがない", meaning_ru="полная невозможность", source_note_id=9_700_003
    )
    db_session.commit()

    report = await run(db_session)

    assert report["mode"] == "heuristic_fallback"
    assert report["candidate_count"] > 0
    assert report["classified_count"] == report["candidate_count"]

    rows = list(db_session.scalars(select(GrammarRelation)))
    assert len(rows) > 0
    assert all(row.source == RelationSource.HEURISTIC for row in rows)
    assert all(row.note is not None for row in rows)
    # canonicalized ordering: grammar_id must be the lexicographically-smaller id (ADR-11)
    assert all(str(row.grammar_id) < str(row.related_grammar_id) for row in rows)


async def test_run_is_idempotent_on_rerun(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.scripts.generate_relations.settings.anthropic_api_key", None)
    monkeypatch.setattr("app.scripts.generate_relations.settings.openai_api_key", None)

    make_grammar(db_session, target_construction="わけだ", meaning_ru="причина", source_note_id=9_700_101)
    make_grammar(db_session, target_construction="わけではない", meaning_ru="отрицание", source_note_id=9_700_102)
    db_session.commit()

    report1 = await run(db_session)
    rows_after_first = list(db_session.scalars(select(GrammarRelation)))

    report2 = await run(db_session)
    rows_after_second = list(db_session.scalars(select(GrammarRelation)))

    assert report1["candidate_count"] == report2["candidate_count"]
    assert len(rows_after_first) == len(rows_after_second)  # no duplicate edges from rerun


async def test_run_llm_pass_upgrades_and_replaces_heuristic_rows(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When a key IS configured, the LLM classification result must replace the
    heuristic-only row for the same pair (module docstring point 3 / ADR-12 upgrade path),
    not sit alongside it as a duplicate."""
    from app.services.generation.provider import RelationClassification

    a = make_grammar(db_session, target_construction="わけだ", meaning_ru="причина", source_note_id=9_700_201)
    b = make_grammar(db_session, target_construction="わけではない", meaning_ru="отрицание", source_note_id=9_700_202)
    db_session.commit()

    # First run: no key -> heuristic-only row.
    monkeypatch.setattr("app.scripts.generate_relations.settings.anthropic_api_key", None)
    monkeypatch.setattr("app.scripts.generate_relations.settings.openai_api_key", None)
    await run(db_session)
    heuristic_rows = list(db_session.scalars(select(GrammarRelation)))
    assert len(heuristic_rows) == 1
    assert heuristic_rows[0].source == RelationSource.HEURISTIC

    # Second run: key configured, LLM classifies the same pair as commonly_confused.
    monkeypatch.setattr("app.scripts.generate_relations.settings.anthropic_api_key", "fake-key")

    class _FakeProvider:
        model_name = "fake-model"

        async def generate_sentences(self, prompt: object) -> list[object]:
            raise AssertionError("not used in this test")

        async def classify_relations(self, candidates: list[object]) -> list[RelationClassification]:
            return [
                RelationClassification(
                    grammar_a_id=c.grammar_a_id,  # type: ignore[attr-defined]
                    grammar_b_id=c.grammar_b_id,  # type: ignore[attr-defined]
                    relation_type="commonly_confused",
                    direction=None,
                    strength=0.95,
                    note="both negate/assert the same reasoning pattern differently",
                )
                for c in candidates
            ]

    monkeypatch.setattr("app.scripts.generate_relations.get_provider", lambda: _FakeProvider())

    await run(db_session)
    rows_after_llm = list(db_session.scalars(select(GrammarRelation)))
    assert len(rows_after_llm) == 1, "heuristic row must be replaced, not duplicated"
    assert rows_after_llm[0].source == RelationSource.LLM_CLASSIFIED
    assert rows_after_llm[0].relation_type.value == "commonly_confused"
    assert str(rows_after_llm[0].grammar_id) < str(rows_after_llm[0].related_grammar_id)
