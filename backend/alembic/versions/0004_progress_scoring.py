"""question.has_confusion_distractor + grammar_progress score neutral defaults

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-27

Fixes a real bug: grammar_progress.application_score/discrimination_score were read (by
select_weak_progress's "Weak Points" ranking and GET /stats's application_avg/discrimination_avg)
but never written anywhere, so every row stayed at their old 0.0 default forever. This migration
does two things needed for services/review.py's new real scoring logic:

1. Adds `question.has_confusion_distractor` (bool, default False) — set once at
   generation/seed time (see distractors.py / generation/trigger.py) to record whether at
   least one of a question's served distractors came from a real curated
   commonly_confused/similar_form grammar_relation edge, rather than the uniform-random
   fallback pool. This is the signal apply_answer uses to decide whether an attempt is
   "informative" for discrimination_score. Existing rows (all seeded/generated before this
   field existed) default to False — conservative, no confusion signal is assumed
   retroactively for historical questions; only newly generated/seeded questions get an
   accurate value going forward.

2. Changes application_score/discrimination_score's default from 0.0 to 0.5 (and backfills
   every existing row to 0.5), per ARCHITECTURE.md idea-doc §28: since neither field was ever
   written before now, every existing 0.0 is bug-noise, not a real "always wrong" signal — safe
   to reset uniformly. 0.5 is the new "no informative attempts yet" neutral baseline; real
   values only move away from it once apply_answer's rolling_accuracy EMA sees an actual
   informative attempt (an AI-generated question for application_score, a
   confusion-distractor question for discrimination_score). See grammar_progress.py and
   services/review.py::apply_answer for the read side of this.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: Sequence[str] | str | None = None
depends_on: Sequence[str] | str | None = None


def upgrade() -> None:
    op.add_column(
        "question",
        sa.Column("has_confusion_distractor", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.alter_column("grammar_progress", "application_score", server_default="0.5")
    op.alter_column("grammar_progress", "discrimination_score", server_default="0.5")
    # Backfill: every existing row's application_score/discrimination_score is bug-noise
    # (never written, still at the old 0.0 default) — reset to the new 0.5 neutral baseline
    # rather than leaving them looking like a confirmed 0.0 "always wrong" signal.
    op.execute("UPDATE grammar_progress SET application_score = 0.5, discrimination_score = 0.5")


def downgrade() -> None:
    op.execute("UPDATE grammar_progress SET application_score = 0.0, discrimination_score = 0.0")
    op.alter_column("grammar_progress", "application_score", server_default="0")
    op.alter_column("grammar_progress", "discrimination_score", server_default="0")

    op.drop_column("question", "has_confusion_distractor")
