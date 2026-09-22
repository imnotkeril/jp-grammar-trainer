from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.stats import StatsOut

router = APIRouter(prefix="/stats", tags=["stats"])

# TODO(backend-dev, ARCHITECTURE.md Phase 2, task 2.6): aggregate grammar_progress by
# status + rolling recall_score average, due_count = count(next_review <= now()).


@router.get("", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)) -> StatsOut:
    raise NotImplementedError("GET /stats — see ARCHITECTURE.md §8, Phase 2 task 2.6")
