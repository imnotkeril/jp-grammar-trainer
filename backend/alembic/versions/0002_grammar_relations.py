"""grammar_relation: explicit relations between grammar items (V2 Grammar Graph slice)

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-23

See ARCHITECTURE.md "V2 Slice: Grammar Graph & Browse" section for the design rationale
(directionality convention, relation_type semantics, why grammar_id/related_grammar_id
ordering matters for symmetric types).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None

RELATION_TYPES = (
    "similar_meaning",
    "similar_form",
    "commonly_confused",
    "opposite",
    "prerequisite",
    "advanced_version",
    "related",
)

RELATION_SOURCES = ("heuristic", "llm_classified", "manual")


def upgrade() -> None:
    relation_type = postgresql.ENUM(*RELATION_TYPES, name="grammar_relation_type", create_type=False)
    relation_type.create(op.get_bind(), checkfirst=True)

    relation_source = postgresql.ENUM(*RELATION_SOURCES, name="grammar_relation_source", create_type=False)
    relation_source.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "grammar_relation",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "grammar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("grammar.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "related_grammar_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("grammar.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", relation_type, nullable=False),
        sa.Column("strength", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("source", relation_source, nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("grammar_id <> related_grammar_id", name="ck_grammar_relation_no_self_loop"),
    )
    op.create_index("ix_grammar_relation_grammar_id", "grammar_relation", ["grammar_id"])
    op.create_index("ix_grammar_relation_related_grammar_id", "grammar_relation", ["related_grammar_id"])
    # One edge per (ordered pair, type). Symmetric types (similar_meaning, similar_form,
    # commonly_confused, opposite, related) are stored ONCE with grammar_id < related_grammar_id
    # (enforced by the population script, not the DB — see ADR-11); directional types
    # (prerequisite, advanced_version) use grammar_id as the "from" side and can legitimately
    # have both (A,B,prerequisite) and (B,A,advanced_version) as distinct rows, so the unique
    # constraint is per (ordered pair, relation_type), not per unordered pair.
    op.create_unique_constraint(
        "uq_grammar_relation_edge",
        "grammar_relation",
        ["grammar_id", "related_grammar_id", "relation_type"],
    )


def downgrade() -> None:
    op.drop_table("grammar_relation")
    postgresql.ENUM(name="grammar_relation_source").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="grammar_relation_type").drop(op.get_bind(), checkfirst=True)
