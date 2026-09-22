"""initial schema: grammar, grammar_progress, question, question_attempt

Revision ID: 0001
Revises:
Create Date: 2026-09-22

See ARCHITECTURE.md §3 for the design rationale.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS pgcrypto')  # for gen_random_uuid()

    grammar_status = postgresql.ENUM("new", "learning", "review", "mastered", name="grammar_status")
    grammar_status.create(op.get_bind(), checkfirst=True)

    question_source = postgresql.ENUM("seed", "ai_generated", name="question_source")
    question_source.create(op.get_bind(), checkfirst=True)

    validation_status = postgresql.ENUM("pending", "valid", "rejected", name="validation_status")
    validation_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "grammar",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_note_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("expression_html", sa.Text(), nullable=False),
        sa.Column("expression_clean", sa.Text(), nullable=False),
        sa.Column("reading", sa.Text(), nullable=False),
        sa.Column("meaning_ru", sa.Text(), nullable=False),
        sa.Column("pattern_text", sa.Text(), nullable=False),
        sa.Column("formation_rules", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("level", sa.String(length=8), nullable=False, server_default="N3"),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("target_construction", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_grammar_level", "grammar", ["level"])
    op.create_index("ix_grammar_tags", "grammar", ["tags"], postgresql_using="gin")

    op.create_table(
        "grammar_progress",
        sa.Column("grammar_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grammar.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("status", grammar_status, nullable=False, server_default="new"),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reviewed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_review", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interval_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lapses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recall_score", sa.REAL(), nullable=False, server_default="0"),
        sa.Column("application_score", sa.REAL(), nullable=False, server_default="0"),
        sa.Column("discrimination_score", sa.REAL(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_progress_next_review", "grammar_progress", ["next_review"])
    op.create_index("ix_progress_status", "grammar_progress", ["status"])

    op.create_table(
        "question",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("grammar_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grammar.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_type", sa.Text(), nullable=False, server_default="fill_in_blank_4choice"),
        sa.Column("sentence_with_blank_html", sa.Text(), nullable=False),
        sa.Column("sentence_full_html", sa.Text(), nullable=False),
        sa.Column("options", postgresql.JSONB(), nullable=False),
        sa.Column("correct_option", sa.String(length=1), nullable=False),
        sa.Column("explanation_ru", sa.Text(), nullable=True),
        sa.Column("source", question_source, nullable=False),
        sa.Column("generation_model", sa.Text(), nullable=True),
        sa.Column("generation_prompt_version", sa.Text(), nullable=True),
        sa.Column("validation_status", validation_status, nullable=False, server_default="valid"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("dedup_hash", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_question_grammar", "question", ["grammar_id"])
    op.create_index("ix_question_shortage", "question", ["grammar_id", "validation_status", "used_count"])
    op.create_index(
        "uq_question_dedup",
        "question",
        ["grammar_id", "dedup_hash"],
        unique=True,
        postgresql_where=sa.text("dedup_hash IS NOT NULL"),
    )

    op.create_table(
        "question_attempt",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("question.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grammar_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("grammar.id", ondelete="CASCADE"), nullable=False),
        sa.Column("selected_option", sa.String(length=1), nullable=False),
        sa.Column("correct_option", sa.String(length=1), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error_type", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_attempt_grammar", "question_attempt", ["grammar_id"])
    op.create_index("ix_attempt_question", "question_attempt", ["question_id"])


def downgrade() -> None:
    op.drop_table("question_attempt")
    op.drop_table("question")
    op.drop_table("grammar_progress")
    op.drop_table("grammar")

    postgresql.ENUM(name="validation_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="question_source").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="grammar_status").drop(op.get_bind(), checkfirst=True)
