"""Roadmap item 2: flag-gated LLM re-classification of existing heuristic relation edges.

All provider calls are mocked — nothing here can be verified against a real LLM without an API
key (see docs/plan.md "Needs owner")."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.grammar import Grammar
from app.models.grammar_relation import GrammarRelation, RelationSource, RelationType
from app.scripts.generate_relations import reclassify_heuristic_edges
from app.services.generation.provider import RelationClassification
from tests.conftest import make_grammar, make_relation

_SETTINGS = "app.scripts.generate_relations.settings"


class _FakeProvider:
    """Classifies every pair with `verdict` (None = "no relation") and counts calls."""

    model_name = "fake-model"

    def __init__(self, verdict: str | None = "commonly_confused") -> None:
        self.calls = 0
        self.verdict = verdict

    async def generate_sentences(self, prompt: object) -> list[object]:
        raise AssertionError("not used in this test")

    async def classify_relations(self, candidates: list[object]) -> list[RelationClassification]:
        self.calls += 1
        return [
            RelationClassification(
                grammar_a_id=c.grammar_a_id,  # type: ignore[attr-defined]
                grammar_b_id=c.grammar_b_id,  # type: ignore[attr-defined]
                relation_type=self.verdict,
                direction=None,
                strength=0.9,
                note="mocked verdict",
            )
            for c in candidates
        ]


class _FailingProvider(_FakeProvider):
    async def classify_relations(self, candidates: list[object]) -> list[RelationClassification]:
        raise RuntimeError("provider down")


def _enable(monkeypatch: pytest.MonkeyPatch, *, flag: bool = True, key: str | None = "fake-key") -> None:
    monkeypatch.setattr(f"{_SETTINGS}.llm_relation_reclassify", flag)
    monkeypatch.setattr(f"{_SETTINGS}.llm_provider", "anthropic")
    monkeypatch.setattr(f"{_SETTINGS}.anthropic_api_key", key)
    monkeypatch.setattr(f"{_SETTINGS}.openai_api_key", None)


def _seed(db: Session) -> tuple[Grammar, Grammar, Grammar]:
    a = make_grammar(db, target_construction="わけだ", source_note_id=9_800_001)
    b = make_grammar(db, target_construction="わけではない", source_note_id=9_800_002)
    c = make_grammar(db, target_construction="ものだ", source_note_id=9_800_003)
    make_relation(db, a, b, relation_type=RelationType.RELATED, source=RelationSource.HEURISTIC)
    make_relation(
        db, b, c, relation_type=RelationType.SIMILAR_MEANING, source=RelationSource.MANUAL, note="curated"
    )
    db.commit()
    return a, b, c


def _sources(db: Session) -> set[RelationSource]:
    return {r.source for r in db.scalars(select(GrammarRelation))}


async def test_skipped_when_flag_off_even_with_key(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch, flag=False)
    _seed(db_session)
    provider = _FakeProvider()

    report = await reclassify_heuristic_edges(db_session, lambda: provider)  # type: ignore[arg-type,return-value]

    assert report["mode"] == "skipped"
    assert provider.calls == 0
    assert _sources(db_session) == {RelationSource.HEURISTIC, RelationSource.MANUAL}


async def test_skipped_when_flag_on_but_no_key(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch, key=None)
    _seed(db_session)
    provider = _FakeProvider()

    assert (await reclassify_heuristic_edges(db_session, lambda: provider))["mode"] == "skipped"  # type: ignore[arg-type,return-value]
    assert provider.calls == 0


async def test_replaces_only_heuristic_edges(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    _seed(db_session)
    provider = _FakeProvider("commonly_confused")

    report = await reclassify_heuristic_edges(db_session, lambda: provider)  # type: ignore[arg-type,return-value]

    assert report["mode"] == "llm_reclassify"
    assert report["pairs_considered"] == 1  # the curated edge is never sent to the model
    assert report["classified_count"] == 1
    assert provider.calls == 1
    rows = {(r.source, r.relation_type.value) for r in db_session.scalars(select(GrammarRelation))}
    assert rows == {
        (RelationSource.LLM_CLASSIFIED, "commonly_confused"),
        (RelationSource.MANUAL, "similar_meaning"),
    }


async def test_drops_heuristic_edge_the_model_rejects(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    _seed(db_session)

    report = await reclassify_heuristic_edges(db_session, lambda: _FakeProvider(None))  # type: ignore[arg-type,return-value]

    assert report["none_count"] == 1
    assert report["dropped_heuristic_rows"] == 1
    assert _sources(db_session) == {RelationSource.MANUAL}


async def test_provider_error_leaves_edges_untouched(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    _seed(db_session)

    with pytest.raises(RuntimeError):
        await reclassify_heuristic_edges(db_session, lambda: _FailingProvider())  # type: ignore[arg-type,return-value]

    assert _sources(db_session) == {RelationSource.HEURISTIC, RelationSource.MANUAL}


async def test_nothing_to_reclassify_makes_no_calls(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(monkeypatch)
    provider = _FakeProvider()

    report = await reclassify_heuristic_edges(db_session, lambda: provider)  # type: ignore[arg-type,return-value]

    assert report["pairs_considered"] == 0
    assert provider.calls == 0
