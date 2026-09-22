"""Seed-import script: Anki JSON export -> `grammar` (+ `grammar_progress`) rows.

Run with:
    uv run python -m app.scripts.seed_import [path/to/n3_grammar_anki_export.json]

Defaults to `data/seed/n3_grammar_anki_export.json` relative to the repo root (two levels
up from `backend/`). Idempotent: upserts by `source_note_id`, safe to re-run.

See ARCHITECTURE.md §4 for the full field-mapping spec and known data-quality caveats
(ADR-6: one row has a malformed <ruby><rt> span — flagged in the import report, not
hand-fixed in the source JSON).
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from beartype import beartype
from sqlalchemy import select

from app.db import SessionLocal
from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress, GrammarStatus

_BOLD_RE = re.compile(r"<b>(.*?)</b>", re.DOTALL)
_RT_SPAN_RE = re.compile(r"<rt>.*?</rt>", re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
# A malformed <rt> payload: contains a nested tag or Latin letters (ruby-scope bleed, e.g.
# "vs<b>こと</b>" or "。それで、..." running into following prose) or is implausibly long for
# a furigana reading. Plain kana with commas/periods is tolerated — several genuine rows in
# this deck use 、 to separate multi-morpheme readings, that's not a bug. See ARCHITECTURE.md
# ADR-6.
_MALFORMED_RT_RE = re.compile(r"[<>A-Za-z]")
_MAX_PLAUSIBLE_RT_LENGTH = 25


class FormationRuleDict(TypedDict):
    pos: str
    form_label: str
    example_html: str


@beartype
def strip_tags(html: str) -> str:
    """Remove all tags AND furigana reading payloads (<rt>...</rt>), keeping only the base
    text. Used whenever we need the plain kanji/kana text a human would read, not the
    reading annotations layered on top of it.
    """
    without_readings = _RT_SPAN_RE.sub("", html)
    return _TAG_RE.sub("", without_readings)


@beartype
def extract_target_construction(expression_html: str, reading: str) -> str:
    """Extract the plain-text target construction from the <b>...</b> span in
    `expression_html`, stripping any nested <ruby>/<rt> markup. Falls back to the <b> span
    in `reading` if `expression_html` has none. Returns "" if neither has a <b> span at all
    — a known gap in 3 of 205 seed rows, see ARCHITECTURE.md §4 addendum / ADR-6b.
    """
    match = _BOLD_RE.search(expression_html)
    if match:
        return strip_tags(match.group(1)).strip()
    fallback = _BOLD_RE.search(reading)
    if fallback:
        return strip_tags(fallback.group(1)).strip()
    return ""


@beartype
def parse_formation_rules(connection_formation: str) -> list[dict[str, str]]:
    """Parse `connection_formation` lines of the shape `<pos label>→<example_html>` into
    structured rows (shape: FormationRuleDict). Lines without `→` are skipped (defensive —
    one malformed row out of 205 shouldn't fail the whole import). See ARCHITECTURE.md §4.
    """
    rules: list[dict[str, str]] = []
    for line in connection_formation.split("\n"):
        line = line.strip()
        if not line or "→" not in line:  # "→"
            continue
        pos, _, example_html = line.partition("→")
        pos = pos.strip()
        example_html = example_html.strip()
        if not pos or not example_html:
            continue
        rules.append({"pos": pos, "form_label": pos, "example_html": example_html})
    return rules


@beartype
def parse_tags(raw_tags: str) -> list[str]:
    """Anki tag string -> list. Empty string -> []. See ARCHITECTURE.md §4 / ADR-4."""
    return [t for t in raw_tags.split() if t]


@beartype
def check_rt_payloads_are_kana(html: str) -> list[str]:
    """Return the list of <rt>...</rt> payloads that look like genuine ruby-scope bleed
    (nested tags, stray Latin text, or implausible length) — a defensive pass surfacing
    anomalies like ADR-6's malformed rows without blocking import. See ARCHITECTURE.md §4.
    """
    problems: list[str] = []
    for rt_match in re.finditer(r"<rt>(.*?)</rt>", html, re.DOTALL):
        payload = rt_match.group(1)
        if len(payload) > _MAX_PLAUSIBLE_RT_LENGTH or _MALFORMED_RT_RE.search(payload):
            problems.append(payload)
    return problems


@beartype
def default_seed_path() -> Path:
    # backend/app/scripts/seed_import.py -> repo root is 3 parents up.
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "data" / "seed" / "n3_grammar_anki_export.json"


class ImportReport(TypedDict):
    total: int
    inserted: int
    updated: int
    anomalies: list[dict[str, object]]


@beartype
def run_import(seed_path: Path) -> ImportReport:
    raw_items = json.loads(seed_path.read_text(encoding="utf-8"))

    inserted_count = 0
    updated_count = 0
    anomalies: list[dict[str, object]] = []

    with SessionLocal() as db:
        for item in raw_items:
            target_construction = extract_target_construction(item["expression_html"], item["reading"])
            formation_rules = parse_formation_rules(item["connection_formation"])
            tags = parse_tags(item.get("tags", ""))
            rt_problems = check_rt_payloads_are_kana(item["expression_html"])
            if rt_problems:
                anomalies.append({"note_id": item["note_id"], "type": "malformed_rt_payload", "detail": rt_problems})
            if not target_construction:
                # Known gap (3/205 rows have no <b> markup at all) — see ARCHITECTURE.md §4
                # addendum. Not blocking: row still imports with an empty target_construction,
                # flagged here for the owner to hand-annotate later if it matters for
                # distractor/validation quality on that specific item.
                anomalies.append({"note_id": item["note_id"], "type": "no_target_construction_found"})

            existing = db.scalar(select(Grammar).where(Grammar.source_note_id == item["note_id"]))
            if existing is None:
                grammar = Grammar(
                    source_note_id=item["note_id"],
                    expression_html=item["expression_html"],
                    expression_clean=item["expression_clean"],
                    reading=item["reading"],
                    meaning_ru=item["meaning_ru"],
                    pattern_text=item["pattern"],
                    formation_rules=formation_rules,
                    level="N3",
                    tags=tags,
                    target_construction=target_construction,
                )
                db.add(grammar)
                db.flush()
                db.add(GrammarProgress(grammar_id=grammar.id, status=GrammarStatus.NEW, next_review=datetime.now(timezone.utc)))
                inserted_count += 1
            else:
                existing.expression_html = item["expression_html"]
                existing.expression_clean = item["expression_clean"]
                existing.reading = item["reading"]
                existing.meaning_ru = item["meaning_ru"]
                existing.pattern_text = item["pattern"]
                existing.formation_rules = formation_rules
                existing.tags = tags
                existing.target_construction = target_construction
                updated_count += 1

        db.commit()

    return ImportReport(
        total=len(raw_items),
        inserted=inserted_count,
        updated=updated_count,
        anomalies=anomalies,
    )


def main() -> None:
    seed_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_seed_path()
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")

    report = run_import(seed_path)

    report_path = Path(__file__).with_name("seed_import_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Seed import done: {report['inserted']} inserted, {report['updated']} updated, "
          f"{len(report['anomalies'])} anomalies flagged (see {report_path.name}).")


if __name__ == "__main__":
    main()
