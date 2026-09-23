from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.grammar_progress import GrammarStatus
from app.models.grammar_relation import RelationType
from tests.conftest import make_grammar, make_progress, make_relation


def test_list_grammar_returns_items_and_total_wrapper(client: TestClient, db_session: Session) -> None:
    g1 = make_grammar(db_session, target_construction="わけだ", source_note_id=9_600_001)
    make_progress(db_session, g1, status=GrammarStatus.NEW)
    g2 = make_grammar(db_session, target_construction="わけではない", source_note_id=9_600_002)
    make_progress(db_session, g2, status=GrammarStatus.LEARNING)
    db_session.commit()

    resp = client.get("/grammar")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    assert {item["target_construction"] for item in body["items"]} == {"わけだ", "わけではない"}
    assert all("status" in item and "recall_score" in item for item in body["items"])


def test_list_grammar_search_matches_expected_rows(client: TestClient, db_session: Session) -> None:
    g1 = make_grammar(
        db_session,
        target_construction="うちに",
        meaning_ru="пока не наступило изменение",
        source_note_id=9_600_101,
    )
    make_progress(db_session, g1)
    g2 = make_grammar(
        db_session,
        target_construction="あいだに",
        meaning_ru="совершенно другое значение",
        source_note_id=9_600_102,
    )
    make_progress(db_session, g2)
    db_session.commit()

    resp = client.get("/grammar", params={"q": "измен"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["target_construction"] == "うちに"


def test_list_grammar_status_filter(client: TestClient, db_session: Session) -> None:
    g1 = make_grammar(db_session, target_construction="a1", source_note_id=9_600_201)
    make_progress(db_session, g1, status=GrammarStatus.MASTERED)
    g2 = make_grammar(db_session, target_construction="a2", source_note_id=9_600_202)
    make_progress(db_session, g2, status=GrammarStatus.NEW)
    db_session.commit()

    resp = client.get("/grammar", params={"status": "mastered"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["target_construction"] == "a1"


def test_list_grammar_pagination(client: TestClient, db_session: Session) -> None:
    for i in range(5):
        g = make_grammar(db_session, target_construction=f"item{i}", source_note_id=9_600_300 + i)
        make_progress(db_session, g)
    db_session.commit()

    resp = client.get("/grammar", params={"limit": 2, "offset": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


def test_grammar_detail_embeds_symmetric_relation_both_directions(
    client: TestClient, db_session: Session
) -> None:
    a = make_grammar(db_session, target_construction="わけだ", source_note_id=9_600_401)
    make_progress(db_session, a)
    b = make_grammar(db_session, target_construction="わけではない", source_note_id=9_600_402)
    make_progress(db_session, b)
    make_relation(
        db_session, a, b, relation_type=RelationType.COMMONLY_CONFUSED, note="both mean X but..."
    )
    db_session.commit()

    resp_a = client.get(f"/grammar/{a.id}")
    assert resp_a.status_code == 200
    body_a = resp_a.json()
    assert len(body_a["relations"]) == 1
    rel = body_a["relations"][0]
    assert rel["relation_type"] == "commonly_confused"
    assert rel["direction"] == "symmetric"
    assert rel["related_grammar"]["target_construction"] == "わけではない"

    # Same edge viewed from the OTHER side must also appear, still "symmetric", with the
    # OTHER item as related_grammar this time (ADR-11's "hides which physical column held
    # which id" contract).
    resp_b = client.get(f"/grammar/{b.id}")
    body_b = resp_b.json()
    assert len(body_b["relations"]) == 1
    assert body_b["relations"][0]["direction"] == "symmetric"
    assert body_b["relations"][0]["related_grammar"]["target_construction"] == "わけだ"


def test_grammar_detail_embeds_directional_relation_with_correct_direction(
    client: TestClient, db_session: Session
) -> None:
    base = make_grammar(db_session, target_construction="ば", source_note_id=9_600_501)
    make_progress(db_session, base)
    advanced = make_grammar(db_session, target_construction="なら", source_note_id=9_600_502)
    make_progress(db_session, advanced)
    # (base, advanced, prerequisite) reads "base is a prerequisite of advanced"
    make_relation(db_session, base, advanced, relation_type=RelationType.PREREQUISITE)
    db_session.commit()

    resp_base = client.get(f"/grammar/{base.id}")
    assert resp_base.json()["relations"][0]["direction"] == "outgoing"

    resp_adv = client.get(f"/grammar/{advanced.id}")
    assert resp_adv.json()["relations"][0]["direction"] == "incoming"


def test_grammar_relations_endpoint_matches_detail_relations(
    client: TestClient, db_session: Session
) -> None:
    a = make_grammar(db_session, target_construction="のに", source_note_id=9_600_601)
    make_progress(db_session, a)
    b = make_grammar(db_session, target_construction="ながら", source_note_id=9_600_602)
    make_progress(db_session, b)
    make_relation(db_session, a, b, relation_type=RelationType.RELATED)
    db_session.commit()

    resp = client.get(f"/grammar/{a.id}/relations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["relation_type"] == "related"


def test_grammar_relations_endpoint_404_for_missing_grammar(client: TestClient, db_session: Session) -> None:
    import uuid

    resp = client.get(f"/grammar/{uuid.uuid4()}/relations")
    assert resp.status_code == 404


def test_bulk_relations_endpoint_returns_full_edge_set(client: TestClient, db_session: Session) -> None:
    a = make_grammar(db_session, target_construction="a", source_note_id=9_600_701)
    make_progress(db_session, a)
    b = make_grammar(db_session, target_construction="b", source_note_id=9_600_702)
    make_progress(db_session, b)
    c = make_grammar(db_session, target_construction="c", source_note_id=9_600_703)
    make_progress(db_session, c)
    make_relation(db_session, a, b, relation_type=RelationType.SIMILAR_MEANING)
    make_relation(db_session, b, c, relation_type=RelationType.PREREQUISITE)
    db_session.commit()

    resp = client.get("/grammar/relations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    types = {edge["relation_type"] for edge in body}
    assert types == {"similar_meaning", "prerequisite"}


def test_grammar_route_ordering_relations_not_swallowed_by_id_param(
    client: TestClient, db_session: Session
) -> None:
    """GET /grammar/relations must resolve to the bulk-edges route, not 422 on trying to
    parse "relations" as a uuid grammar_id — regression guard for router registration order.
    """
    resp = client.get("/grammar/relations")
    assert resp.status_code == 200
    assert resp.json() == []
