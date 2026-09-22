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
import random
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.grammar import Grammar
from app.models.grammar_progress import GrammarProgress, GrammarStatus
from app.models.question import Question, QuestionSource, ValidationStatus
from app.services.distractors import pick_distractors
from app.services.generation.validate import dedup_hash as compute_dedup_hash

_OPTION_KEYS = ("A", "B", "C", "D")

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
def build_blanked_sentence_html(expression_html: str) -> str | None:
    """Replace the target-construction `<b>...</b>` span with the same "___" blank marker
    convention used by the AI-generation prompt (ARCHITECTURE.md §7.3), preserving any
    `<ruby><rt>` markup outside that span so furigana on the rest of the sentence survives
    intact. Returns None if `expression_html` has no `<b>` span at all — defensive: the only
    205-row rows with an empty `target_construction` (ADR-6b) also lack this span entirely,
    so a row reaching this function should always have one, but callers must not assume it.
    """
    if not _BOLD_RE.search(expression_html):
        return None
    return _BOLD_RE.sub("___", expression_html, count=1)


class SeedQuestionReport(TypedDict):
    inserted: int
    skipped_existing: int
    skipped_no_target: int
    skipped_no_bold_span: int
    skipped_insufficient_distractors: list[int]


@beartype
def import_seed_questions(db: Session) -> SeedQuestionReport:
    """Build one first-party `Question` (source=SEED, validation_status=VALID — seed content
    is owner-curated, not LLM output that needs the same review, per ARCHITECTURE.md §7.4/§3
    default) per eligible `Grammar` row, from the grammar's own example sentence + target
    construction. Distractors reuse `services/distractors.py::pick_distractors`, the same
    function wired into the AI-generation path (`services/generation/trigger.py`).

    Idempotent: skips any grammar item that already has a SEED question, same idempotency
    pattern as the Grammar/GrammarProgress upsert above (safe to re-run).
    """
    all_grammar = list(db.scalars(select(Grammar)).all())
    candidates: list[tuple[uuid.UUID, str]] = [
        (g.id, g.target_construction) for g in all_grammar if g.target_construction
    ]
    existing_seed_grammar_ids = set(
        db.scalars(select(Question.grammar_id).where(Question.source == QuestionSource.SEED))
    )

    inserted = 0
    skipped_existing = 0
    skipped_no_target = 0
    skipped_no_bold_span = 0
    skipped_insufficient_distractors: list[int] = []

    for grammar in all_grammar:
        if grammar.id in existing_seed_grammar_ids:
            skipped_existing += 1
            continue
        if not grammar.target_construction:
            # 3/205 rows, ADR-6b — no <b> markup at all, nothing to build a question from.
            skipped_no_target += 1
            continue
        # `extract_target_construction` (called during the grammar upsert above) prefers the
        # <b> span in `expression_html` (ruby-marked-up), falling back to the <b> span in
        # `reading` (plain kana, no ruby) when `expression_html` has none — 29/205 real rows
        # only mark the target in `reading`. Build the blank from whichever field actually
        # carries the <b> span, so the blanked sentence and the plain-kana fallback rows both
        # get a question instead of being dropped. See ARCHITECTURE.md §4.
        source_html = grammar.expression_html if _BOLD_RE.search(grammar.expression_html) else grammar.reading
        blanked = build_blanked_sentence_html(source_html)
        if blanked is None:
            skipped_no_bold_span += 1
            continue

        rng = random.Random(grammar.source_note_id)  # deterministic per-item, order-independent
        try:
            distractor_texts = pick_distractors(
                grammar.id, grammar.target_construction, candidates, count=3, rng=rng
            )
        except ValueError:
            skipped_insufficient_distractors.append(grammar.source_note_id)
            continue

        texts = [grammar.target_construction, *distractor_texts]
        rng.shuffle(texts)
        options = [{"key": key, "text": text} for key, text in zip(_OPTION_KEYS, texts, strict=True)]
        correct_option = next(opt["key"] for opt in options if opt["text"] == grammar.target_construction)

        question = Question(
            grammar_id=grammar.id,
            sentence_with_blank_html=blanked,
            sentence_full_html=source_html,
            options=options,
            correct_option=correct_option,
            explanation_ru=None,
            source=QuestionSource.SEED,
            generation_model=None,
            generation_prompt_version=None,
            validation_status=ValidationStatus.VALID,
            dedup_hash=compute_dedup_hash(source_html),
        )
        db.add(question)
        inserted += 1

    db.commit()
    return SeedQuestionReport(
        inserted=inserted,
        skipped_existing=skipped_existing,
        skipped_no_target=skipped_no_target,
        skipped_no_bold_span=skipped_no_bold_span,
        skipped_insufficient_distractors=skipped_insufficient_distractors,
    )


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
    seed_questions: SeedQuestionReport


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

        seed_questions_report = import_seed_questions(db)

    return ImportReport(
        total=len(raw_items),
        inserted=inserted_count,
        updated=updated_count,
        anomalies=anomalies,
        seed_questions=seed_questions_report,
    )


def main() -> None:
    seed_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_seed_path()
    if not seed_path.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_path}")

    report = run_import(seed_path)

    report_path = Path(__file__).with_name("seed_import_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    sq = report["seed_questions"]
    print(f"Seed import done: {report['inserted']} inserted, {report['updated']} updated, "
          f"{len(report['anomalies'])} anomalies flagged (see {report_path.name}).")
    print(f"Seed questions: {sq['inserted']} inserted, {sq['skipped_existing']} already existed, "
          f"{sq['skipped_no_target']} skipped (no target construction), "
          f"{sq['skipped_no_bold_span']} skipped (no <b> span), "
          f"{len(sq['skipped_insufficient_distractors'])} skipped (insufficient distractor pool).")


if __name__ == "__main__":
    main()
