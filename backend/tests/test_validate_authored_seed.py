from __future__ import annotations

import json
from copy import deepcopy

import pytest

from app.scripts.seed_import_authored import default_seed_paths
from app.scripts.validate_authored_seed import default_paths, validate_payload

_VALID_ITEM: dict[str, object] = {
    "key": "n5_001_desu",
    "expression_html": "<ruby>私<rt>わたし</rt></ruby>は<ruby>学生<rt>がくせい</rt></ruby><b>です</b>。",
    "reading": "わたしは がくせい<b>です</b>。",
    "meaning_ru": "Я студент.",
    "pattern_text": "Паттерн: N + です\nЗначение: вежливое утверждение",
    "formation_rules": [{"pos": "名詞", "form_label": "名詞＋です", "example_html": "学生<b>です</b>"}],
    "target_construction": "です",
    "tags": ["N5"],
}


def _payload(**item_overrides: object) -> dict[str, object]:
    item = deepcopy(_VALID_ITEM)
    item.update(item_overrides)
    return {"level": "N5", "items": [item]}


def test_valid_payload_has_no_errors_or_warnings() -> None:
    result = validate_payload(_payload())
    assert result.errors == []
    assert result.warnings == []


def test_empty_items_is_valid_scaffold() -> None:
    assert validate_payload({"level": "N1", "items": []}).errors == []


@pytest.mark.parametrize(
    ("payload", "needle"),
    [
        ([], "top level"),
        ({"level": "N9", "items": []}, "'level' must be one of"),
        ({"level": "N5", "items": {}}, "'items' must be a list"),
        (_payload(target_construction=""), "missing or empty 'target_construction'"),
        (_payload(key="N5 Desu"), "key must look like"),
        (_payload(key="n4_001_desu"), "key prefix does not match file level"),
        (_payload(expression_html="私は学生です。"), "no <b>target</b> span"),
        (_payload(meaning_ru="I am a student."), "meaning_ru should be Russian"),
        (_payload(formation_rules=[{"pos": "x"}]), "formation_rules must be a list"),
        (_payload(tags="N5"), "tags must be a list of strings"),
        (
            _payload(expression_html="<ruby>私<rt>watashi</rt></ruby>は<b>です</b>。"),
            "malformed <rt>",
        ),
    ],
)
def test_validation_errors(payload: object, needle: str) -> None:
    errors = validate_payload(payload).errors
    assert any(needle in e for e in errors), errors


def test_duplicate_keys_are_an_error() -> None:
    payload = _payload()
    payload["items"] = [deepcopy(_VALID_ITEM), deepcopy(_VALID_ITEM)]  # type: ignore[index]
    assert any("duplicate key" in e for e in validate_payload(payload).errors)


def test_target_mismatch_is_only_a_warning() -> None:
    result = validate_payload(_payload(target_construction="だ"))
    assert result.errors == []
    assert any("does not equal the <b> span" in w for w in result.warnings)


def test_every_shipped_authored_file_has_no_errors() -> None:
    paths = default_paths()
    assert len(paths) >= 2  # N4 + N2 content (N5/N1 are empty scaffolds until sourced)
    for path in paths:
        result = validate_payload(json.loads(path.read_text(encoding="utf-8")), path.name)
        assert result.errors == [], result.errors[:5]


def test_importer_default_paths_cover_the_validated_files() -> None:
    importable = {p.name for p in default_seed_paths()}
    assert {p.name for p in default_paths()} <= importable
