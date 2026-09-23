from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class VocabularyEntryType(str, enum.Enum):
    WORD = "word"
    KANJI = "kanji"


class Vocabulary(Base):
    """One N3 word or kanji entry, seeded from the owner's Anki-export CSVs.

    See ARCHITECTURE.md "V3 Slice: Adaptive Practice & Vocabulary", V3.1 for schema rationale
    (why entry_type has only two values, why surface_form is matched EXACTLY against <ruby>
    base spans rather than via substring/tokenization — ADR-15).

    IMPORTANT: like Question.source/validation_status and GrammarRelation.relation_type/source
    (app/models/question.py, app/models/grammar_relation.py), the native Postgres enum column
    below MUST use values_callable=lambda enum_cls: [e.value for e in enum_cls] — without it,
    SQLAlchemy persists the Python member NAME ("WORD") instead of the enum VALUE ("word"),
    which silently breaks on a real DB roundtrip against the migration's native
    `vocabulary_entry_type` enum. This exact gotcha has bitten this project twice already.
    """

    __tablename__ = "vocabulary"
    __table_args__ = (
        UniqueConstraint("surface_form", "entry_type", name="uq_vocabulary_surface_entry_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    surface_form: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    entry_type: Mapped[VocabularyEntryType] = mapped_column(
        Enum(
            VocabularyEntryType,
            name="vocabulary_entry_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=VocabularyEntryType.WORD,
    )
    reading: Mapped[str] = mapped_column(Text, nullable=False)
    meaning_ru: Mapped[str] = mapped_column(Text, nullable=False)
    example_sentence_jp: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_sentence_reading: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_sentence_ru: Mapped[str | None] = mapped_column(Text, nullable=True)
    jlpt_level: Mapped[str] = mapped_column(String(8), nullable=False, default="N3")
    source_tag: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserVocabulary(Base):
    """Per-word exposure/retention state, lazily created on first exposure (V3.1: no
    owner_id per ADR-3; not pre-populated for all vocabulary rows — most never get exposed
    at N3-only review volume).
    """

    __tablename__ = "user_vocabulary"

    vocabulary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("vocabulary.id", ondelete="CASCADE"), primary_key=True
    )
    correct_exposures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    incorrect_exposures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    known_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_exposed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
