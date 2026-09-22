from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, BigInteger, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.grammar_progress import GrammarProgress
    from app.models.question import Question


class Grammar(Base):
    """A single N3 grammar construction, seeded from the owner's Anki export.

    See ARCHITECTURE.md §3 (schema) and §4 (seed import mapping).
    """

    __tablename__ = "grammar"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_note_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    expression_html: Mapped[str] = mapped_column(Text, nullable=False)
    expression_clean: Mapped[str] = mapped_column(Text, nullable=False)
    reading: Mapped[str] = mapped_column(Text, nullable=False)
    meaning_ru: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_text: Mapped[str] = mapped_column(Text, nullable=False)
    formation_rules: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False, default=list)
    level: Mapped[str] = mapped_column(String(8), nullable=False, default="N3")
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    target_construction: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    progress: Mapped["GrammarProgress"] = relationship(  # noqa: F821
        back_populates="grammar", uselist=False, cascade="all, delete-orphan"
    )
    questions: Mapped[list["Question"]] = relationship(  # noqa: F821
        back_populates="grammar", cascade="all, delete-orphan"
    )
