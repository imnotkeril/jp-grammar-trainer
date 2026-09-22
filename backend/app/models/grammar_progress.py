from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import REAL, DateTime, Enum, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.grammar import Grammar


class GrammarStatus(str, enum.Enum):
    NEW = "new"
    LEARNING = "learning"
    REVIEW = "review"
    MASTERED = "mastered"


class GrammarProgress(Base):
    """Per-item SRS state. One row per grammar item (no multi-user on MVP).

    See ARCHITECTURE.md §3 (schema) and §6 (SRS algorithm).
    """

    __tablename__ = "grammar_progress"

    grammar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grammar.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[GrammarStatus] = mapped_column(
        Enum(GrammarStatus, name="grammar_status"), nullable=False, default=GrammarStatus.NEW
    )
    first_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reviewed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_review: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    interval_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lapses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recall_score: Mapped[float] = mapped_column(REAL, nullable=False, default=0.0)
    application_score: Mapped[float] = mapped_column(REAL, nullable=False, default=0.0)
    discrimination_score: Mapped[float] = mapped_column(REAL, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    grammar: Mapped["Grammar"] = relationship(back_populates="progress")  # noqa: F821
