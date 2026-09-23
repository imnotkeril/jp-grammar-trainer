"""Curated-relations import script: hand-authored relation-quality edges ->
`grammar_relation` rows with `source="manual"`, taking precedence over existing
`heuristic`/`llm_classified` edges for any pair they cover. See ARCHITECTURE.md
"V4 Slice" §V4.3 (ADR-22).

Run with:
    uv run python -m app.scripts.import_curated_relations
        # defaults to glob data/seed/relations_curated_*.json
    uv run python -m app.scripts.import_curated_relations --purge-remaining-heuristic
        # see ADR-22 — additionally deletes every remaining source="heuristic" row after
        # curated pairs are processed (off by default)
    uv run python -m app.scripts.import_curated_relations path/to/one.json [more.json ...]
        # explicit file list instead of the default glob

Reuses `generate_relations.py`'s `_canonicalize_symmetric`, `_delete_stale_heuristic_rows`
(generalized to also match `llm_classified` rows), and `_upsert_relation` rather than
reimplementing them — the persistence mechanics (upsert on the
`uq_grammar_relation_edge` constraint) are identical, only the source of truth for what to
write differs (hand-authored JSON vs. heuristic/LLM scoring).
"""

from __future__ import annotations

import argparse
import json
from glob import glob
from pathlib import Path
from typing import TypedDict

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.grammar import Grammar
from app.models.grammar_relation import (
    DIRECTIONAL_RELATION_TYPES,
    SYMMETRIC_RELATION_TYPES,
    GrammarRelation,
    RelationSource,
    RelationType,
)
from app.scripts.generate_relations import (
    PairKey,
    _canonicalize_symmetric,
    _delete_stale_heuristic_rows,
    _pair_key,
    _upsert_relation,
)
from app.scripts.seed_import_authored import compute_source_note_id

_DEFAULT_GLOB = "relations_curated_*.json"


class UnresolvedRef(TypedDict):
    edge_index: int
    side: str  # "a" | "b"
    reference: dict[str, object]


class ImportReport(TypedDict):
    edges_read: int
    resolved: int
    unresolved: list[UnresolvedRef]
    self_loops_rejected: int
    heuristic_rows_replaced: int
    llm_rows_replaced: int
    inserted: int
    updated: int
    count_by_relation_type: dict[str, int]
    purge_remaining_heuristic_ran: bool
    heuristic_rows_purged: int


@beartype
def default_seed_paths() -> list[Path]:
    # backend/app/scripts/import_curated_relations.py -> repo root is 3 parents up.
    repo_root = Path(__file__).resolve().parents[3]
    seed_dir = repo_root / "data" / "seed"
    return sorted(Path(p) for p in glob(str(seed_dir / _DEFAULT_GLOB)))


@beartype
def _resolve_reference(db: Session, ref: dict[str, object]) -> Grammar | None:
    """Resolve one `a`/`b` reference object to a `Grammar` row. Returns None (not a hard
    failure) if it resolves to zero or multiple rows — per ARCHITECTURE.md §V4.3, an
    unresolved reference is flagged in the report and the edge is skipped, consistent with
    this slice's "flag, don't block" posture (ADR-6/ADR-6b/ADR-21).
    """
    level = str(ref["level"])
    if "key" in ref:
        # {level, key} — N4/N2 authored items (and, in principle, any level authored in the
        # same schema): recompute ADR-21's hash and look up by source_note_id. Exact,
        # unambiguous, same mechanism seed_import_authored.py itself uses.
        source_note_id = compute_source_note_id(level, str(ref["key"]))
        return db.scalar(select(Grammar).where(Grammar.source_note_id == source_note_id))

    if "target_construction" in ref and ref["target_construction"]:
        rows = list(
            db.scalars(
                select(Grammar).where(
                    Grammar.level == level, Grammar.target_construction == str(ref["target_construction"])
                )
            )
        )
        return rows[0] if len(rows) == 1 else None

    if "expression_clean" in ref and ref["expression_clean"]:
        # Fallback for the 3 N3 rows with an empty target_construction (ADR-6b) — checked
        # second, only when target_construction is absent/empty from the reference object.
        rows = list(
            db.scalars(
                select(Grammar).where(
                    Grammar.level == level, Grammar.expression_clean == str(ref["expression_clean"])
                )
            )
        )
        return rows[0] if len(rows) == 1 else None

    return None


@beartype
def _direction_to_columns(
    relation_type: RelationType, a_id: str, b_id: str, direction: str | None
) -> tuple[str, str]:
    """Mirrors generate_relations.py::_apply_llm_results' direction handling — symmetric
    types canonicalize by sorted id, directional types respect `direction`
    ("a_to_b"|"b_to_a", default "a_to_b" including a missing/unexpected value)."""
    if relation_type in SYMMETRIC_RELATION_TYPES:
        return _canonicalize_symmetric(a_id, b_id)
    assert relation_type in DIRECTIONAL_RELATION_TYPES
    if direction == "b_to_a":
        return b_id, a_id
    return a_id, b_id


@beartype
def run_import(db: Session, paths: list[Path], *, purge_remaining_heuristic: bool = False) -> ImportReport:
    all_edges: list[dict[str, object]] = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        all_edges.extend(payload["edges"])

    unresolved: list[UnresolvedRef] = []
    self_loops_rejected = 0

    # Resolved edges, ready to persist: (grammar_id, related_grammar_id, relation_type,
    # strength, note).
    resolved_edges: list[tuple[str, str, RelationType, float, str | None]] = []

    for idx, edge in enumerate(all_edges):
        a_ref = edge["a"]
        b_ref = edge["b"]
        a_row = _resolve_reference(db, a_ref)
        b_row = _resolve_reference(db, b_ref)

        if a_row is None:
            unresolved.append(UnresolvedRef(edge_index=idx, side="a", reference=a_ref))
            continue
        if b_row is None:
            unresolved.append(UnresolvedRef(edge_index=idx, side="b", reference=b_ref))
            continue

        if a_row.id == b_row.id:
            self_loops_rejected += 1
            continue

        relation_type = RelationType(edge["relation_type"])
        direction = edge.get("direction")
        grammar_id, related_grammar_id = _direction_to_columns(
            relation_type, str(a_row.id), str(b_row.id), direction
        )
        strength = float(edge.get("strength", 1.0))
        note = edge.get("note")
        resolved_edges.append((grammar_id, related_grammar_id, relation_type, strength, note))

    pair_keys: set[PairKey] = {_pair_key(g, r) for g, r, _, _, _ in resolved_edges}

    # ADR-22: curated edges take precedence over BOTH heuristic and llm_classified rows for
    # any pair they cover — generalized from generate_relations.py's original
    # heuristic-only deletion.
    heuristic_before = {
        _pair_key(str(row.grammar_id), str(row.related_grammar_id))
        for row in db.scalars(select(GrammarRelation).where(GrammarRelation.source == RelationSource.HEURISTIC))
        if _pair_key(str(row.grammar_id), str(row.related_grammar_id)) in pair_keys
    }
    llm_before = {
        _pair_key(str(row.grammar_id), str(row.related_grammar_id))
        for row in db.scalars(
            select(GrammarRelation).where(GrammarRelation.source == RelationSource.LLM_CLASSIFIED)
        )
        if _pair_key(str(row.grammar_id), str(row.related_grammar_id)) in pair_keys
    }
    _delete_stale_heuristic_rows(
        db, pair_keys, sources=frozenset({RelationSource.HEURISTIC, RelationSource.LLM_CLASSIFIED})
    )
    db.flush()  # see generate_relations.py's own comment: ORM deletes must flush before Core upserts

    existing_manual_ids = {
        row.id
        for row in db.scalars(select(GrammarRelation).where(GrammarRelation.source == RelationSource.MANUAL))
    }

    inserted = 0
    updated = 0
    by_type: dict[str, int] = {}
    for grammar_id, related_grammar_id, relation_type, strength, note in resolved_edges:
        was_existing = bool(
            db.scalar(
                select(GrammarRelation.id).where(
                    GrammarRelation.grammar_id == grammar_id,
                    GrammarRelation.related_grammar_id == related_grammar_id,
                    GrammarRelation.relation_type == relation_type,
                )
            )
        )
        _upsert_relation(
            db,
            grammar_id=grammar_id,
            related_grammar_id=related_grammar_id,
            relation_type=relation_type,
            strength=strength,
            source=RelationSource.MANUAL,
            note=str(note) if note else None,
            prompt_version=None,
        )
        if was_existing:
            updated += 1
        else:
            inserted += 1
        by_type[relation_type.value] = by_type.get(relation_type.value, 0) + 1

    heuristic_rows_purged = 0
    if purge_remaining_heuristic:
        remaining = list(
            db.scalars(select(GrammarRelation).where(GrammarRelation.source == RelationSource.HEURISTIC))
        )
        for row in remaining:
            db.delete(row)
        heuristic_rows_purged = len(remaining)

    db.commit()

    return ImportReport(
        edges_read=len(all_edges),
        resolved=len(resolved_edges),
        unresolved=unresolved,
        self_loops_rejected=self_loops_rejected,
        heuristic_rows_replaced=len(heuristic_before),
        llm_rows_replaced=len(llm_before),
        inserted=inserted,
        updated=updated,
        count_by_relation_type=by_type,
        purge_remaining_heuristic_ran=purge_remaining_heuristic,
        heuristic_rows_purged=heuristic_rows_purged,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--purge-remaining-heuristic", action="store_true")
    parser.add_argument("files", nargs="*")
    args = parser.parse_args()

    paths = [Path(p) for p in args.files] if args.files else default_seed_paths()
    if not paths:
        raise FileNotFoundError("No curated-relations files found (default glob data/seed/relations_curated_*.json)")
    missing = [p for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Curated relations file(s) not found: {missing}")

    db = SessionLocal()
    try:
        report = run_import(db, paths, purge_remaining_heuristic=args.purge_remaining_heuristic)
    finally:
        db.close()

    report_path = Path(__file__).with_name("import_curated_relations_report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nReport written to {report_path}")


if __name__ == "__main__":
    main()
