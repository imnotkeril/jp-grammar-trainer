from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, Float, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.grammar import Grammar


class RelationType(str, enum.Enum):
    """See ARCHITECTURE.md V2 slice, ADR-11 for directionality semantics per type."""

    SIMILAR_MEANING = "similar_meaning"
    SIMILAR_FORM = "similar_form"
    COMMONLY_CONFUSED = "commonly_confused"
    OPPOSITE = "opposite"
    PREREQUISITE = "prerequisite"
    ADVANCED_VERSION = "advanced_version"
    RELATED = "related"


# Symmetric types: meaning is identical regardless of which column holds which id. The
# population script always canonicalizes these so grammar_id < related_grammar_id (ADR-11).
SYMMETRIC_RELATION_TYPES: frozenset[RelationType] = frozenset(
    {
        RelationType.SIMILAR_MEANING,
        RelationType.SIMILAR_FORM,
        RelationType.COMMONLY_CONFUSED,
        RelationType.OPPOSITE,
        RelationType.RELATED,
    }
)

# Directional types: grammar_id is "from"/base, related_grammar_id is "to"/target (ADR-11).
DIRECTIONAL_RELATION_TYPES: frozenset[RelationType] = frozenset(
    {RelationType.PREREQUISITE, RelationType.ADVANCED_VERSION}
)


class RelationSource(str, enum.Enum):
    HEURISTIC = "heuristic"
    LLM_CLASSIFIED = "llm_classified"
    MANUAL = "manual"


class GrammarRelation(Base):
    """An explicit typed edge between two grammar items. See ARCHITECTURE.md V2 slice
    ("V2.1 GrammarRelation model + migration") for schema rationale and directionality.

    IMPORTANT: like Question.source/validation_status (app/models/question.py), the native
    Postgres enum columns below MUST use values_callable=lambda enum_cls: [e.value for e in
    enum_cls] — without it, SQLAlchemy persists the Python member NAME (e.g. "SIMILAR_MEANING")
    instead of the enum VALUE (e.g. "similar_meaning"), which silently breaks on a real DB
    roundtrip against the migration's native `grammar_relation_type`/`grammar_relation_source`
    enums (this exact gotcha was caught by a prior reviewer on the MVP's Question model).
    """

    __tablename__ = "grammar_relation"
    __table_args__ = (
        CheckConstraint("grammar_id <> related_grammar_id", name="ck_grammar_relation_no_self_loop"),
        UniqueConstraint(
            "grammar_id", "related_grammar_id", "relation_type", name="uq_grammar_relation_edge"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grammar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grammar.id", ondelete="CASCADE"), nullable=False, index=True
    )
    related_grammar_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("grammar.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[RelationType] = mapped_column(
        Enum(
            RelationType,
            name="grammar_relation_type",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    source: Mapped[RelationSource] = mapped_column(
        Enum(
            RelationSource,
            name="grammar_relation_source",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
    )
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    grammar: Mapped["Grammar"] = relationship(  # noqa: F821
        foreign_keys=[grammar_id], back_populates="relations_from"
    )
    related_grammar: Mapped["Grammar"] = relationship(  # noqa: F821
        foreign_keys=[related_grammar_id], back_populates="relations_to"
    )
