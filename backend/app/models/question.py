from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.grammar import Grammar


class QuestionSource(str, enum.Enum):
    SEED = "seed"
    AI_GENERATED = "ai_generated"


class ValidationStatus(str, enum.Enum):
    PENDING = "pending"
    VALID = "valid"
    REJECTED = "rejected"


class Question(Base):
    """A 4-choice fill-in-the-blank question for one grammar item.

    See ARCHITECTURE.md §3 (schema) and §7 (AI generation pipeline).
    """

    __tablename__ = "question"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grammar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grammar.id", ondelete="CASCADE"), nullable=False
    )
    question_type: Mapped[str] = mapped_column(String(64), nullable=False, default="fill_in_blank_4choice")
    sentence_with_blank_html: Mapped[str] = mapped_column(Text, nullable=False)
    sentence_full_html: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    correct_option: Mapped[str] = mapped_column(String(1), nullable=False)
    explanation_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[QuestionSource] = mapped_column(
        Enum(QuestionSource, name="question_source", values_callable=lambda enum_cls: [e.value for e in enum_cls]),
        nullable=False,
    )
    generation_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generation_prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    validation_status: Mapped[ValidationStatus] = mapped_column(
        Enum(
            ValidationStatus,
            name="validation_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=ValidationStatus.VALID,
    )
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dedup_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # True iff at least one of the 3 served distractors was drawn from the `preferred` pool
    # (a real commonly_confused/similar_form grammar_relation edge, see distractors.py /
    # generation/trigger.py) rather than the uniform-random fallback pool. Set once at
    # generation/seed time, never mutated after. Drives discrimination_score's EMA update in
    # services/review.py::apply_answer — see grammar_progress.py for the scoring rationale.
    has_confusion_distractor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    grammar: Mapped["Grammar"] = relationship(back_populates="questions")  # noqa: F821
