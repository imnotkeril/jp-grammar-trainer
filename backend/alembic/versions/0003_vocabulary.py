"""vocabulary + user_vocabulary: N3 word/kanji tracking for adaptive furigana (V3 slice)

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-23

See ARCHITECTURE.md "V3 Slice: Adaptive Practice & Vocabulary" section, V3.1, for the design
rationale (why entry_type has only two values, why surface_form is matched EXACTLY against
<ruby> base spans rather than via substring/tokenization, and the known/streak semantics).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

VOCABULARY_ENTRY_TYPES = ("word", "kanji")


def upgrade() -> None:
    entry_type = postgresql.ENUM(*VOCABULARY_ENTRY_TYPES, name="vocabulary_entry_type", create_type=False)
    entry_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "vocabulary",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("surface_form", sa.Text(), nullable=False),
        sa.Column("entry_type", entry_type, nullable=False, server_default="word"),
        sa.Column("reading", sa.Text(), nullable=False),
        sa.Column("meaning_ru", sa.Text(), nullable=False),
        sa.Column("example_sentence_jp", sa.Text(), nullable=True),
        sa.Column("example_sentence_reading", sa.Text(), nullable=True),
        sa.Column("example_sentence_ru", sa.Text(), nullable=True),
        sa.Column("jlpt_level", sa.String(length=8), nullable=False, server_default="N3"),
        # Raw CSV category tag for words (e.g. "N3::Education") or packed on/kun readings for
        # kanji rows — free-form audit/debug field, not queried on a hot path. See V3.2.
        sa.Column("source_tag", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vocabulary_surface_form", "vocabulary", ["surface_form"])
    # A word and a kanji entry can legitimately share a surface_form (e.g. a single-kanji
    # word like 実 that is ALSO listed as a kanji-deck entry) — entry_type disambiguates them
    # as distinct rows rather than colliding, per V3.1/V3.2.
    op.create_unique_constraint(
        "uq_vocabulary_surface_entry_type", "vocabulary", ["surface_form", "entry_type"]
    )

    op.create_table(
        "user_vocabulary",
        sa.Column(
            "vocabulary_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vocabulary.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("correct_exposures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("incorrect_exposures", sa.Integer(), nullable=False, server_default="0"),
        # Consecutive-correct streak, reset to 0 on any incorrect exposure — drives
        # known_since per V3.1's "known after N correct exposures, un-known on relapse" rule.
        # correct_exposures/incorrect_exposures are kept too, as raw lifetime counters for
        # any future stats view (mirrors grammar_progress's repetitions vs. lapses split).
        sa.Column("correct_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("known_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_exposed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("user_vocabulary")
    op.drop_table("vocabulary")
    postgresql.ENUM(name="vocabulary_entry_type").drop(op.get_bind(), checkfirst=True)
