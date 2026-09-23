"""Vocabulary seed script: external Anki-export CSVs -> repo-local JSON snapshot ->
`vocabulary` rows. See ARCHITECTURE.md "V3 Slice: Adaptive Practice & Vocabulary", V3.2,
[ADR-14].

Run with:
    uv run python -m app.scripts.seed_vocabulary

Pipeline (mirrors `seed_import.py`'s idempotent-upsert pattern):
  1. Read every `*.csv` in both `{vocabulary_csv_source_dir}/слова н3` (word rows) and
     `{vocabulary_csv_source_dir}/кандзи н3` (kanji rows) — headerless, comma-separated,
     UTF-8-with-BOM-on-first-field. `vocabulary_csv_source_dir` defaults to the owner's
     personal path (app/config.py), never read at request time — this script is the only
     caller.
  2. Parse rows per the column mapping confirmed in ARCHITECTURE.md V3.2. Dedupe within each
     family by `surface_form` — first occurrence (by file sort order, then row order) wins;
     collisions are counted in the report, not silently dropped.
  3. Write `data/seed/vocabulary_n3.json` (repo-committed snapshot, both families tagged by
     `entry_type`) — [ADR-14]: the DB-populating step below reads THIS file, never the
     external directory directly, so the backend never depends on the external drive being
     present at deploy/CI time.
  4. Upsert into `vocabulary` on `(surface_form, entry_type)` — updates
     reading/meaning_ru/examples/source_tag, NEVER touches `user_vocabulary` (re-running this
     script must not reset the owner's retention progress).
  5. Print/write `seed_vocabulary_report.json` next to this script (same convention as
     `seed_import_report.json` / `generate_relations_report.json`).
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import TypedDict

from beartype import beartype
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.vocabulary import Vocabulary, VocabularyEntryType

_REPORT_PATH = Path(__file__).with_name("seed_vocabulary_report.json")


class VocabularyRow(TypedDict):
    surface_form: str
    entry_type: str  # "word" | "kanji"
    reading: str
    meaning_ru: str
    example_sentence_jp: str | None
    example_sentence_reading: str | None
    example_sentence_ru: str | None
    source_tag: str | None


@beartype
def parse_word_csv(path: Path) -> list[VocabularyRow]:
    """`слова н3/*.csv` column mapping (ARCHITECTURE.md V3.2): surface_form, reading,
    meaning_ru, example_sentence_jp, example_sentence_reading, example_sentence_ru,
    category_tag (-> source_tag verbatim).
    """
    rows: list[VocabularyRow] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for line in csv.reader(f):
            if len(line) < 7 or not line[0].strip():
                continue
            rows.append(
                VocabularyRow(
                    surface_form=line[0].strip(),
                    entry_type=VocabularyEntryType.WORD.value,
                    reading=line[1].strip(),
                    meaning_ru=line[2].strip(),
                    example_sentence_jp=line[3].strip() or None,
                    example_sentence_reading=line[4].strip() or None,
                    example_sentence_ru=line[5].strip() or None,
                    source_tag=line[6].strip() or None,
                )
            )
    return rows


@beartype
def parse_kanji_csv(path: Path) -> list[VocabularyRow]:
    """`кандзи н3/*.csv` column mapping (ARCHITECTURE.md V3.2): kanji_char,
    primary_kun_reading (-> reading, the one that appears standalone in running text),
    on_readings, all_kun_readings (both packed into source_tag as "on=... kun=..." for audit
    only, not used for matching), meaning_ru, compound_examples (dropped — not modeled),
    example_sentence_jp, example_sentence_ru.
    """
    rows: list[VocabularyRow] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for line in csv.reader(f):
            if len(line) < 8 or not line[0].strip():
                continue
            kanji_char, primary_kun, on_readings, all_kun, meaning_ru = (
                line[0].strip(),
                line[1].strip(),
                line[2].strip(),
                line[3].strip(),
                line[4].strip(),
            )
            example_sentence_jp = line[6].strip() or None
            example_sentence_ru = line[7].strip() or None
            rows.append(
                VocabularyRow(
                    surface_form=kanji_char,
                    entry_type=VocabularyEntryType.KANJI.value,
                    reading=primary_kun,
                    meaning_ru=meaning_ru,
                    example_sentence_jp=example_sentence_jp,
                    example_sentence_reading=None,
                    example_sentence_ru=example_sentence_ru,
                    source_tag=f"on={on_readings} kun={all_kun}",
                )
            )
    return rows


class ParseReport(TypedDict):
    word_files: int
    word_rows_read: int
    word_dedup_collisions: int
    kanji_files: int
    kanji_rows_read: int
    kanji_dedup_collisions: int
    total_rows_written: int


@beartype
def _dedupe(rows: list[VocabularyRow]) -> tuple[list[VocabularyRow], int]:
    """First occurrence by surface_form wins within one family (V3.2 step 2)."""
    seen: dict[str, VocabularyRow] = {}
    collisions = 0
    for row in rows:
        if row["surface_form"] in seen:
            collisions += 1
            continue
        seen[row["surface_form"]] = row
    return list(seen.values()), collisions


@beartype
def build_snapshot(source_dir: Path) -> tuple[list[VocabularyRow], ParseReport]:
    word_dir = source_dir / "слова н3"
    kanji_dir = source_dir / "кандзи н3"

    word_files = sorted(word_dir.glob("*.csv")) if word_dir.is_dir() else []
    kanji_files = sorted(kanji_dir.glob("*.csv")) if kanji_dir.is_dir() else []

    word_rows_raw = [row for path in word_files for row in parse_word_csv(path)]
    kanji_rows_raw = [row for path in kanji_files for row in parse_kanji_csv(path)]

    word_rows, word_collisions = _dedupe(word_rows_raw)
    kanji_rows, kanji_collisions = _dedupe(kanji_rows_raw)

    all_rows = [*word_rows, *kanji_rows]
    report = ParseReport(
        word_files=len(word_files),
        word_rows_read=len(word_rows_raw),
        word_dedup_collisions=word_collisions,
        kanji_files=len(kanji_files),
        kanji_rows_read=len(kanji_rows_raw),
        kanji_dedup_collisions=kanji_collisions,
        total_rows_written=len(all_rows),
    )
    return all_rows, report


@beartype
def default_snapshot_path() -> Path:
    # backend/app/scripts/seed_vocabulary.py -> repo root is 3 parents up.
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "data" / "seed" / "vocabulary_n3.json"


@beartype
def upsert_vocabulary(db: Session, rows: list[VocabularyRow]) -> None:
    """Upsert on (surface_form, entry_type) — never touches user_vocabulary (V3.2 step 4)."""
    for row in rows:
        stmt = pg_insert(Vocabulary).values(
            surface_form=row["surface_form"],
            entry_type=row["entry_type"],
            reading=row["reading"],
            meaning_ru=row["meaning_ru"],
            example_sentence_jp=row["example_sentence_jp"],
            example_sentence_reading=row["example_sentence_reading"],
            example_sentence_ru=row["example_sentence_ru"],
            source_tag=row["source_tag"],
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_vocabulary_surface_entry_type",
            set_={
                "reading": stmt.excluded.reading,
                "meaning_ru": stmt.excluded.meaning_ru,
                "example_sentence_jp": stmt.excluded.example_sentence_jp,
                "example_sentence_reading": stmt.excluded.example_sentence_reading,
                "example_sentence_ru": stmt.excluded.example_sentence_ru,
                "source_tag": stmt.excluded.source_tag,
            },
        )
        db.execute(stmt)
    db.commit()


@beartype
def run(source_dir: Path, snapshot_path: Path, db: Session) -> dict[str, object]:
    rows, parse_report = build_snapshot(source_dir)

    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # Determine insert/update counts up front (before upserting) for an accurate report.
    existing_keys = {
        (surface_form, entry_type)
        for surface_form, entry_type in db.execute(
            select(Vocabulary.surface_form, Vocabulary.entry_type)
        ).all()
    }
    inserted = sum(1 for r in rows if (r["surface_form"], VocabularyEntryType(r["entry_type"])) not in existing_keys)
    updated = len(rows) - inserted

    upsert_vocabulary(db, rows)

    total_count = db.execute(select(func.count()).select_from(Vocabulary)).scalar_one()

    report: dict[str, object] = {
        "source_dir": str(source_dir),
        "snapshot_path": str(snapshot_path),
        **parse_report,
        "inserted": inserted,
        "updated": updated,
        "vocabulary_row_count_after": total_count,
    }
    return report


def main() -> None:
    source_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(settings.vocabulary_csv_source_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Vocabulary CSV source dir not found: {source_dir}")

    snapshot_path = default_snapshot_path()

    with SessionLocal() as db:
        report = run(source_dir, snapshot_path, db)

    _REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nReport written to {_REPORT_PATH}")


if __name__ == "__main__":
    main()
