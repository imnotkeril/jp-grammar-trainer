"""Relation population script: heuristic candidates -> optional LLM classification ->
`grammar_relation` rows. See ARCHITECTURE.md V2 slice ("V2.2 Relation population strategy",
ADR-12).

Run with:
    uv run python -m app.scripts.generate_relations

Pipeline:
  1. Heuristic candidate generation (pure Python, app/services/relation_heuristics.py) —
     scores every unordered pair of the ~205 grammar items on shared function-word stem,
     meaning_ru keyword overlap, and shared-kanji rarity; keeps the top ~6 candidates per
     item (≤ ~615 pairs total, far below the O(205²)=~21,000 all-pairs count).
  2. **No-API-key fallback (owner-gated, see below)**: `backend/.env` currently ships with
     both ANTHROPIC_API_KEY and OPENAI_API_KEY empty. This script MUST still produce a
     useful result in that state — it does NOT hard-fail or no-op. Instead, every heuristic
     candidate is written directly as a `grammar_relation` row with `source="heuristic"` and
     a `relation_type` inferred by simple rule (see `_fallback_relation_type` below):
       - pair shares an exact function-word/pattern stem (e.g. both contain "わけ")
         -> "similar_form"
       - otherwise, high meaning_ru keyword Jaccard overlap -> "similar_meaning"
       - otherwise -> "related" (the score already cleared MIN_CANDIDATE_SCORE, so it's not
         nothing, just not a stronger-typed signal)
     This is a heuristic-only classification, not a real semantic judgement — it exists so
     the graph/browse UI has *something* to render before an API key is ever configured.
  3. **LLM upgrade pass (when a key IS present)**: extends `LLMProvider` with
     `classify_relations` (app/services/generation/provider.py), batched ~40 pairs/call
     through the already-selected provider (app/services/generation/factory.py — reuses
     `LLM_PROVIDER`, no new provider-selection logic). Running this script again after a key
     is added upgrades/refines the earlier heuristic-only edges: any candidate pair
     previously written with `source="heuristic"` is deleted and replaced by the LLM's
     verdict (including removing the edge entirely if the LLM says "no meaningful
     relation") — see `_delete_stale_heuristic_rows` for the exact idempotency mechanism.
     Manually-curated rows (`source="manual"`, none exist yet on MVP/V2) are never touched.
  4. Persist via upsert on the `(grammar_id, related_grammar_id, relation_type)` unique
     constraint (0002 migration) — safe to re-run.
  5. Print/write a summary report (`generate_relations_report.json`, next to this script,
     mirroring `seed_import_report.json`'s pattern).

Owner-gated per ADR-12: this is a manual one-time/occasional script, not wired into any
request path or background job. Costs real API tokens once a key is configured — run
deliberately.
"""

from __future__ import annotations

import json
from pathlib import Path

from beartype import beartype
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models.grammar import Grammar
from app.models.grammar_relation import (
    DIRECTIONAL_RELATION_TYPES,
    SYMMETRIC_RELATION_TYPES,
    GrammarRelation,
    RelationSource,
    RelationType,
)
from app.services.generation.factory import get_provider
from app.services.generation.prompts import RELATION_PROMPT_VERSION
from app.services.generation.provider import LLMProvider, RelationCandidate
from app.services.relation_heuristics import Candidate, ScorableItem, top_candidates

_LLM_BATCH_SIZE = 40
_REPORT_PATH = Path(__file__).parent / "generate_relations_report.json"

PairKey = tuple[str, str]  # sorted (str(uuid), str(uuid))


@beartype
def _fallback_relation_type(candidate: Candidate) -> RelationType:
    """No-API-key fallback rule (see module docstring point 2)."""
    if candidate.shared_stem is not None:
        return RelationType.SIMILAR_FORM
    if candidate.meaning_jaccard >= 0.3:
        return RelationType.SIMILAR_MEANING
    return RelationType.RELATED


@beartype
def _pair_key(a_id: str, b_id: str) -> PairKey:
    lo, hi = sorted((a_id, b_id))
    return (lo, hi)


@beartype
def _canonicalize_symmetric(a_id: str, b_id: str) -> tuple[str, str]:
    """Symmetric types: lexicographically-smaller id goes in grammar_id (ADR-11)."""
    lo, hi = sorted((a_id, b_id))
    return lo, hi


@beartype
def _delete_stale_heuristic_rows(
    db: Session,
    pair_keys: set[PairKey],
    sources: frozenset[RelationSource] = frozenset({RelationSource.HEURISTIC}),
) -> int:
    """Delete any existing row (whose `source` is in `sources`) whose unordered
    (grammar_id, related_grammar_id) pair is in `pair_keys` — the pragmatic idempotency
    mechanism for the LLM-upgrade pass (module docstring point 3): a rerun with a real API
    key should replace the earlier heuristic guess (whatever relation_type it picked) with
    the LLM's verdict, rather than leaving a stale heuristic row alongside a differently-typed
    LLM row.

    `sources` defaults to `{heuristic}` only (the original call site's behavior, unchanged).
    `import_curated_relations.py` (ARCHITECTURE.md V4.3, ADR-22) passes
    `{heuristic, llm_classified}` so a curated (`manual`) edge supersedes *either* kind of
    automated guess for a pair it covers — `manual` rows themselves are never matched by this
    function regardless of `sources`, since a curated edge should never be silently deleted by
    a later curated import touching the same pair (that path goes through the normal upsert
    instead).
    """
    existing = list(db.scalars(select(GrammarRelation).where(GrammarRelation.source.in_(sources))))
    to_delete = [
        row
        for row in existing
        if _pair_key(str(row.grammar_id), str(row.related_grammar_id)) in pair_keys
    ]
    for row in to_delete:
        db.delete(row)
    return len(to_delete)


@beartype
def _upsert_relation(
    db: Session,
    *,
    grammar_id: str,
    related_grammar_id: str,
    relation_type: RelationType,
    strength: float,
    source: RelationSource,
    note: str | None,
    prompt_version: str | None,
) -> None:
    stmt = pg_insert(GrammarRelation).values(
        grammar_id=grammar_id,
        related_grammar_id=related_grammar_id,
        relation_type=relation_type.value,
        strength=max(0.0, min(1.0, strength)),
        source=source.value,
        note=note,
        prompt_version=prompt_version,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_grammar_relation_edge",
        set_={
            "strength": stmt.excluded.strength,
            "source": stmt.excluded.source,
            "note": stmt.excluded.note,
            "prompt_version": stmt.excluded.prompt_version,
        },
    )
    db.execute(stmt)


@beartype
def _has_configured_key() -> bool:
    """Whether the currently-selected LLM_PROVIDER has its API key set. Mirrors
    factory.get_provider()'s selection so this script's "do we have a key" check and the
    actual adapter construction never disagree.
    """
    if settings.llm_provider == "anthropic":
        return bool(settings.anthropic_api_key)
    if settings.llm_provider == "openai":
        return bool(settings.openai_api_key)
    return False


@beartype
def _batched(items: list[Candidate], size: int) -> list[list[Candidate]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


async def _run_llm_pass(
    provider: LLMProvider,
    candidates: list[Candidate],
    grammar_by_id: dict[str, Grammar],
) -> list[dict[str, object]]:
    """Classify every candidate via the LLM, batched. Returns raw classification dicts
    (already merged with the candidate metadata needed to canonicalize + persist)."""
    results: list[dict[str, object]] = []
    for batch in _batched(candidates, _LLM_BATCH_SIZE):
        rel_candidates = [
            RelationCandidate(
                grammar_a_id=c.item_a_id,
                grammar_a_text=(
                    f"{grammar_by_id[c.item_a_id].target_construction} — "
                    f"{grammar_by_id[c.item_a_id].pattern_text[:200]}"
                ),
                grammar_a_meaning=grammar_by_id[c.item_a_id].meaning_ru,
                grammar_b_id=c.item_b_id,
                grammar_b_text=(
                    f"{grammar_by_id[c.item_b_id].target_construction} — "
                    f"{grammar_by_id[c.item_b_id].pattern_text[:200]}"
                ),
                grammar_b_meaning=grammar_by_id[c.item_b_id].meaning_ru,
            )
            for c in batch
        ]
        classifications = await provider.classify_relations(rel_candidates)
        for classification in classifications:
            results.append(
                {
                    "grammar_a_id": classification.grammar_a_id,
                    "grammar_b_id": classification.grammar_b_id,
                    "relation_type": classification.relation_type,
                    "direction": classification.direction,
                    "strength": classification.strength,
                    "note": classification.note,
                }
            )
    return results


@beartype
def _apply_llm_results(
    db: Session, results: list[dict[str, object]]
) -> tuple[int, int, dict[str, int]]:
    """Persist LLM classification results. Returns (classified_count, none_count, by_type)."""
    classified = 0
    none_count = 0
    by_type: dict[str, int] = {}
    for r in results:
        relation_type_raw = r["relation_type"]
        if relation_type_raw is None:
            none_count += 1
            continue
        try:
            relation_type = RelationType(relation_type_raw)
        except ValueError:
            none_count += 1  # model returned something outside the enum -> treat as "none"
            continue

        a_id = str(r["grammar_a_id"])
        b_id = str(r["grammar_b_id"])
        direction = r.get("direction")

        if relation_type in SYMMETRIC_RELATION_TYPES:
            grammar_id, related_grammar_id = _canonicalize_symmetric(a_id, b_id)
        else:
            assert relation_type in DIRECTIONAL_RELATION_TYPES
            if direction == "b_to_a":
                grammar_id, related_grammar_id = b_id, a_id
            else:
                # default a_to_b, including a missing/unexpected direction value
                grammar_id, related_grammar_id = a_id, b_id

        _upsert_relation(
            db,
            grammar_id=grammar_id,
            related_grammar_id=related_grammar_id,
            relation_type=relation_type,
            strength=float(r["strength"]),  # type: ignore[arg-type]
            source=RelationSource.LLM_CLASSIFIED,
            note=str(r["note"]) if r.get("note") else None,
            prompt_version=RELATION_PROMPT_VERSION,
        )
        classified += 1
        by_type[relation_type.value] = by_type.get(relation_type.value, 0) + 1
    return classified, none_count, by_type


@beartype
def _apply_heuristic_fallback(db: Session, candidates: list[Candidate]) -> dict[str, int]:
    by_type: dict[str, int] = {}
    for c in candidates:
        relation_type = _fallback_relation_type(c)
        grammar_id, related_grammar_id = _canonicalize_symmetric(c.item_a_id, c.item_b_id)
        _upsert_relation(
            db,
            grammar_id=grammar_id,
            related_grammar_id=related_grammar_id,
            relation_type=relation_type,
            strength=min(1.0, c.score / 5.0),  # rough normalization; heuristic scores are unbounded
            source=RelationSource.HEURISTIC,
            note=(
                f"heuristic fallback (no LLM key configured): "
                f"shared_stem={c.shared_stem!r}, meaning_jaccard={c.meaning_jaccard:.2f}"
            ),
            prompt_version=None,
        )
        by_type[relation_type.value] = by_type.get(relation_type.value, 0) + 1
    return by_type


@beartype
async def run(db: Session) -> dict[str, object]:
    grammar_rows = list(db.scalars(select(Grammar)))
    grammar_by_id = {str(g.id): g for g in grammar_rows}
    items = [
        ScorableItem(
            item_id=str(g.id),
            target_construction=g.target_construction,
            meaning_ru=g.meaning_ru,
            expression_clean=g.expression_clean,
        )
        for g in grammar_rows
    ]

    candidates = top_candidates(items)
    pair_keys = {_pair_key(c.item_a_id, c.item_b_id) for c in candidates}

    deleted = _delete_stale_heuristic_rows(db, pair_keys)
    # Flush the pending ORM deletes NOW, before any raw INSERT ... ON CONFLICT below: those
    # inserts execute immediately against the DB (Core-level db.execute), while ORM
    # `db.delete(row)` calls are lazy until the next flush/commit. Without this flush, a
    # pending delete for a row we're about to upsert would otherwise fire at commit time
    # AFTER the upsert, silently deleting the row we just wrote (this exact ordering bug
    # was caught by test_run_is_idempotent_on_rerun during development).
    db.flush()

    has_key = _has_configured_key()
    by_type: dict[str, int]
    none_count = 0
    classified_count = 0
    mode: str

    if has_key:
        mode = "llm_classified"
        provider = get_provider()
        results = await _run_llm_pass(provider, candidates, grammar_by_id)
        classified_count, none_count, by_type = _apply_llm_results(db, results)
    else:
        mode = "heuristic_fallback"
        by_type = _apply_heuristic_fallback(db, candidates)
        classified_count = len(candidates)

    db.commit()

    # Items with zero relations after this pass (ARCHITECTURE.md V2.2 step 5 / V2.6 open item).
    all_edges = list(db.scalars(select(GrammarRelation)))
    touched_ids = {str(e.grammar_id) for e in all_edges} | {str(e.related_grammar_id) for e in all_edges}
    zero_relation_ids = [gid for gid in grammar_by_id if gid not in touched_ids]

    report = {
        "mode": mode,
        "total_grammar_items": len(items),
        "candidate_count": len(candidates),
        "stale_heuristic_rows_replaced": deleted,
        "classified_count": classified_count,
        "none_count": none_count,
        "count_by_relation_type": by_type,
        "items_with_zero_relations": zero_relation_ids,
        "items_with_zero_relations_count": len(zero_relation_ids),
    }
    return report


@beartype
def main() -> None:
    import asyncio

    db = SessionLocal()
    try:
        report = asyncio.run(run(db))
    finally:
        db.close()

    _REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nReport written to {_REPORT_PATH}")


if __name__ == "__main__":
    main()
