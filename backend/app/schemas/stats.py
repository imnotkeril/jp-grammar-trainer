from __future__ import annotations

from pydantic import BaseModel


class StatsOut(BaseModel):
    due_count: int
    new_count: int
    learning_count: int
    review_count: int
    mastered_count: int
    recall_pct: float
    application_avg: float
    discrimination_avg: float
