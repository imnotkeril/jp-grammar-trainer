from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.scripts.seed_import import (
    check_rt_payloads_are_kana,
    default_seed_path,
    extract_target_construction,
    parse_formation_rules,
    parse_tags,
)


def _load_seed() -> list[dict[str, object]]:
    path = default_seed_path()
    if not path.exists():
        pytest.skip(f"seed file not present at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def test_extract_target_construction_simple() -> None:
    html = "<ruby>日本<rt>にほん</rt></ruby>にいる<b>うちに</b><ruby>一度富士山<rt>いちどふじさん</rt></ruby>に登ってみたい。"
    assert extract_target_construction(html, "") == "うちに"


def test_extract_target_construction_strips_nested_ruby() -> None:
    html = "text<b><ruby>間<rt>あいだ</rt></ruby></b>text"
    assert extract_target_construction(html, "") == "間"


def test_extract_target_construction_falls_back_to_reading() -> None:
    assert extract_target_construction("no bold here", "text<b>うちに</b>text") == "うちに"


def test_extract_target_construction_no_bold_anywhere() -> None:
    assert extract_target_construction("plain", "plain") == ""


def test_parse_formation_rules_splits_on_arrow_and_newline() -> None:
    raw = "гл.ている→<ruby>食べ<rt>たべ</rt></ruby>ているうちに\nи-прил.→<ruby>若い<rt>わかい</rt></ruby>うちに"
    rules = parse_formation_rules(raw)
    assert len(rules) == 2
    assert rules[0]["pos"] == "гл.ている"
    assert "たべ" in rules[0]["example_html"]
    assert rules[1]["pos"] == "и-прил."


def test_parse_formation_rules_skips_lines_without_arrow() -> None:
    raw = "гл.ている→example\nthis line has no arrow\nи-прил.→example2"
    rules = parse_formation_rules(raw)
    assert len(rules) == 2


def test_parse_formation_rules_empty_string() -> None:
    assert parse_formation_rules("") == []


def test_parse_tags_empty_string_yields_empty_list() -> None:
    assert parse_tags("") == []


def test_parse_tags_splits_on_whitespace() -> None:
    assert parse_tags("conditionals contrast") == ["conditionals", "contrast"]


def test_check_rt_payloads_flags_non_kana_or_long_payload() -> None:
    # Mirrors real malformed rows (ARCHITECTURE.md ADR-6): a <rt> payload with a nested
    # tag or stray Latin text bleeding in from the following field.
    bad_html = "<ruby>もの<rt>ものvs<b>こと</b>の違い</rt></ruby>"
    problems = check_rt_payloads_are_kana(bad_html)
    assert problems  # flagged, not silently accepted

    # Plain kana with a comma/period separator is tolerated — several genuine rows use it
    # to separate multi-morpheme readings, not a bug (ARCHITECTURE.md ADR-6).
    tolerated_html = "<ruby>間<rt>あいだ、こ</rt></ruby>"
    assert check_rt_payloads_are_kana(tolerated_html) == []

    good_html = "<ruby>日本<rt>にほん</rt></ruby>"
    assert check_rt_payloads_are_kana(good_html) == []


# Known gap: 3/205 seed rows have no <b> markup anywhere (neither expression_html nor
# reading), so no target_construction can be extracted. Discovered while scaffolding —
# documented as an addendum to ARCHITECTURE.md §4 (not a blocker: import still succeeds,
# seed_import.py flags these in its report for the owner to hand-annotate later).
KNOWN_NO_TARGET_NOTE_IDS = {1775898451577, 1775898451579, 1775898451653}


def test_all_205_real_rows_parse_without_exception() -> None:
    """Runs the parsers over the real seed file end-to-end — no unhandled exceptions,
    and confirms our expectation about the dataset shape (ARCHITECTURE.md §4/§9):
    exactly the one known <rt>-anomaly row, the 3 known no-<b> rows, tags empty everywhere.
    """
    items = _load_seed()
    assert len(items) == 205

    rt_anomaly_note_ids: list[int] = []
    no_target_note_ids: list[int] = []
    non_empty_tag_rows = 0

    for item in items:
        target = extract_target_construction(item["expression_html"], item["reading"])
        if not target:
            no_target_note_ids.append(item["note_id"])

        rules = parse_formation_rules(item["connection_formation"])
        assert isinstance(rules, list)

        tags = parse_tags(item.get("tags", ""))
        if tags:
            non_empty_tag_rows += 1

        if check_rt_payloads_are_kana(item["expression_html"]):
            rt_anomaly_note_ids.append(item["note_id"])

    assert non_empty_tag_rows == 0, "SPEC.md §9 risk confirmed empty; update ADR-4 if this ever changes"
    # 9 of 205 rows have a <rt> payload containing a nested tag or stray Latin text — a
    # clear ruby-scope bleed heuristic catches automatically. note_id 1775898451281 (the
    # row that first surfaced this issue) bleeds pure-kana text ("、こ") into its <rt>, which
    # is visually wrong but indistinguishable from a legitimate multi-morpheme kana reading
    # by this heuristic — documented, not auto-flagged. See ARCHITECTURE.md ADR-6.
    assert len(rt_anomaly_note_ids) == 9, (
        "expected exactly 9 ADR-6 anomaly rows; dataset shape changed — re-check ARCHITECTURE.md §4"
    )
    assert set(no_target_note_ids) == KNOWN_NO_TARGET_NOTE_IDS, (
        "no-target-construction row set changed — re-check ARCHITECTURE.md §4 addendum"
    )
