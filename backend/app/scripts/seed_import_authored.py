"""Seed-import script for N4/N2 authored content (DB-ready JSON, no Anki intermediate) ->
`grammar` (+ `grammar_progress`) rows. See ARCHITECTURE.md "V4 Slice" §V4.1/§V4.2.

Run with:
    uv run python -m app.scripts.seed_import_authored
        # defaults to data/seed/n4_grammar_authored.json + data/seed/n2_grammar_authored.json
    uv run python -m app.scripts.seed_import_authored path/to/custom.json [more.json ...]

Level-parameterized and reusable for both N4 and N2 (and any future level authored in the
same schema) — the `level` value comes from each file's own top-level `level` field, not a
CLI flag. Reuses `seed_import.py`'s helpers (`strip_tags`, `check_rt_payloads_are_kana`,
`import_seed_questions`) rather than duplicating them; never touches
`n3_grammar_anki_export.json` or reads/writes any N3 row directly. Idempotent: upserts by a
deterministic `source_note_id` derived from `(level, key)` per ADR-21.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress, GrammarStatus
from app.scripts.seed_import import (
    SeedQuestionReport,
    check_rt_payloads_are_kana,
    import_seed_questions,
    strip_tags,
)


@beartype
def compute_source_note_id(level: str, key: str) -> int:
    """[ADR-21] Deterministic 60-bit positive integer from `(level, key)`, used as the
    idempotency key for N4/N2 upserts — same role `note_id` plays for the N3 Anki import,
    but synthesized instead of sourced from Anki (N4/N2 have no Anki note ids).

    Collides with real Anki note_ids (~13 digits) or with each other only at
    cryptographic-hash-collision probability; see ARCHITECTURE.md ADR-21 for the full
    rationale, including the one documented failure mode (renaming `key` after first import
    orphans the old row instead of updating it — an authoring-time discipline rule, not
    solved in code here).
    """
    digest = hashlib.sha256(f"{level}:{key}".encode()).hexdigest()
    return int(digest[:15], 16)


@beartype
def _resolve_source_html(item: dict[str, object]) -> str:
    return str(item["expression_html"])


class ItemAnomaly(TypedDict):
    key: str
    level: str
    type: str
    detail: object


@beartype
def _validate_target_construction(expression_clean: str, target_construction: str) -> bool:
    """True if `target_construction` (already stripped of markup by the caller) literally
    appears in `expression_clean` — per ARCHITECTURE.md V4.1's field table. A mismatch is
    flagged, not a hard failure (same "flag, don't block" posture as ADR-6/ADR-6b)."""
    return target_construction in expression_clean


class AuthoredFileReport(TypedDict):
    level: str
    total: int
    inserted: int
    updated: int
    anomalies: list[dict[str, object]]


class AuthoredImportReport(TypedDict):
    files: list[AuthoredFileReport]
    seed_questions: SeedQuestionReport


@beartype
def _import_one_file(db: Session, path: Path) -> AuthoredFileReport:
    payload = json.loads(path.read_text(encoding="utf-8"))
    level = str(payload["level"])
    items: list[dict[str, object]] = payload["items"]

    inserted = 0
    updated = 0
    anomalies: list[dict[str, object]] = []

    for item in items:
        key = str(item["key"])
        expression_html = _resolve_source_html(item)
        expression_clean = strip_tags(expression_html)
        target_construction = str(item["target_construction"])
        formation_rules = item.get("formation_rules", [])
        tags = list(item.get("tags", []))

        if not _validate_target_construction(expression_clean, target_construction):
            anomalies.append(
                {"key": key, "level": level, "type": "target_construction_mismatch", "detail": target_construction}
            )

        rt_problems = check_rt_payloads_are_kana(expression_html)
        if rt_problems:
            anomalies.append({"key": key, "level": level, "type": "malformed_rt_payload", "detail": rt_problems})

        source_note_id = compute_source_note_id(level, key)
        existing = db.scalar(select(Grammar).where(Grammar.source_note_id == source_note_id))
        if existing is None:
            grammar = Grammar(
                source_note_id=source_note_id,
                expression_html=expression_html,
                expression_clean=expression_clean,
                reading=str(item["reading"]),
                meaning_ru=str(item["meaning_ru"]),
                pattern_text=str(item["pattern_text"]),
                formation_rules=formation_rules,
                level=level,
                tags=tags,
                target_construction=target_construction,
            )
            db.add(grammar)
            db.flush()
            db.add(
                GrammarProgress(
                    grammar_id=grammar.id, status=GrammarStatus.NEW, next_review=datetime.now(timezone.utc)
                )
            )
            inserted += 1
        else:
            # Update path touches every content field but never grammar_progress (§V4.2 step
            # 5) — an edit to wording shouldn't reset SRS state on an item already reviewed.
            existing.expression_html = expression_html
            existing.expression_clean = expression_clean
            existing.reading = str(item["reading"])
            existing.meaning_ru = str(item["meaning_ru"])
            existing.pattern_text = str(item["pattern_text"])
            existing.formation_rules = formation_rules
            existing.level = level
            existing.tags = tags
            existing.target_construction = target_construction
            updated += 1

    db.commit()

    return AuthoredFileReport(
        level=level, total=len(items), inserted=inserted, updated=updated, anomalies=anomalies
    )


@beartype
def default_seed_paths() -> list[Path]:
    # backend/app/scripts/seed_import_authored.py -> repo root is 3 parents up.
    repo_root = Path(__file__).resolve().parents[3]
    seed_dir = repo_root / "data" / "seed"
    return [seed_dir / "n4_grammar_authored.json", seed_dir / "n2_grammar_authored.json"]


@beartype
def run_import(paths: list[Path]) -> AuthoredImportReport:
    file_reports: list[AuthoredFileReport] = []
    with SessionLocal() as db:
        for path in paths:
            file_reports.append(_import_one_file(db, path))

        # Runs once, after ALL files are upserted — naturally picks up every new N4/N2
        # Grammar row (no SEED question yet) via the existing, unmodified, level-agnostic
        # logic (ARCHITECTURE.md §V4.2 step 6).
        seed_questions_report = import_seed_questions(db)

    return AuthoredImportReport(files=file_reports, seed_questions=seed_questions_report)


def main() -> None:
    paths = [Path(p) for p in sys.argv[1:]] if len(sys.argv) > 1 else default_seed_paths()
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Seed file(s) not found: {missing}")

    report = run_import(paths)

    report_path = Path(__file__).with_name("seed_import_authored_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for fr in report["files"]:
        print(
            f"[{fr['level']}] {fr['inserted']} inserted, {fr['updated']} updated, "
            f"{len(fr['anomalies'])} anomalies flagged."
        )
    sq = report["seed_questions"]
    print(
        f"Seed questions: {sq['inserted']} inserted, {sq['skipped_existing']} already existed, "
        f"{sq['skipped_no_target']} skipped (no target construction), "
        f"{sq['skipped_no_bold_span']} skipped (no <b> span), "
        f"{len(sq['skipped_insufficient_distractors'])} skipped (insufficient distractor pool)."
    )
    print(f"Report written to {report_path}")


if __name__ == "__main__":
    main()
