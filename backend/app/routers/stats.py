from __future__ import annotations

from beartype import beartype
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.stats import StatsOut
from app.services.review import compute_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsOut)
@beartype
def get_stats(
    db: Session = Depends(get_db),
    level: str | None = Query(default=None, description="exact match against grammar.level (N3|N4|N2)"),
) -> StatsOut:
    """GET /stats — dashboard aggregates. See ARCHITECTURE.md §8/§9 task 2.6, SPEC.md §27/§8,
    V4 slice §V4.4/ADR-23. `level` optional — omitted returns combined stats across all
    levels (unchanged existing behavior)."""
    stats = compute_stats(db, level=level)
    return StatsOut(
        due_count=stats.due_count,
        new_count=stats.new_count,
        learning_count=stats.learning_count,
        review_count=stats.review_count,
        mastered_count=stats.mastered_count,
        recall_pct=stats.recall_pct,
        application_avg=stats.application_avg,
        discrimination_avg=stats.discrimination_avg,
        total_items=stats.total_items,
    )
