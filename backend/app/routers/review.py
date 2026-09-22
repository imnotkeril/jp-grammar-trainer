from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.review import AnswerRequest, AnswerResponse, SessionRequest, SessionResponse

router = APIRouter(prefix="/review", tags=["review"])

# TODO(backend-dev, ARCHITECTURE.md Phase 2, tasks 2.4-2.5): implement due-item selection
# (overdue-first, then new, respecting `size`), shortage-triggered background generation
# (app.services.generation.trigger), and the SRS write-back via app.services.srs.schedule_next.
# Wiring for distractors.pick_distractors() into freshly generated `question.options` also
# belongs here (see the TODO in app/services/generation/trigger.py).


@router.post("/session", response_model=SessionResponse)
async def start_session(
    request: SessionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
) -> SessionResponse:
    raise NotImplementedError("POST /review/session — see ARCHITECTURE.md §8, Phase 2 task 2.4")


@router.post("/answer", response_model=AnswerResponse)
async def submit_answer(
    request: AnswerRequest,
    db: Session = Depends(get_db),
) -> AnswerResponse:
    raise NotImplementedError("POST /review/answer — see ARCHITECTURE.md §8, Phase 2 task 2.5")
