"""vocab deck tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-19

Adds three tables backing the vocabulary deck + spaced-repetition feature:
- `vocab_entries`      — global vocabulary pool (domain-tagged terms)
- `learner_topics`     — which domains each learner is actively studying
- `learner_vocab_deck` — per-learner SM-2 SRS state for each term
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "vocab_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("source_lang", sa.Text(), nullable=False),
        sa.Column("target_lang", sa.Text(), nullable=False),
        sa.Column("register", sa.Text(), nullable=False),
        sa.Column("origin", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_vocab_entries_domain_dir",
        "vocab_entries",
        ["domain", "source_lang", "target_lang"],
    )

    op.create_table(
        "learner_topics",
        sa.Column(
            "learner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("domain", sa.Text(), primary_key=True, nullable=False),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "learner_vocab_deck",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "learner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "vocab_entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("vocab_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ease_factor", sa.Float(), nullable=False, server_default="2.5"),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "next_review_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_grade", sa.Integer(), nullable=True),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("added_by", sa.Text(), nullable=False),
        sa.Column("gap_type", sa.Text(), nullable=True),
        sa.Column(
            "source_attempt_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attempts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("learner_id", "vocab_entry_id", name="uq_lvd_learner_entry"),
    )
    op.create_index(
        "ix_lvd_learner_due",
        "learner_vocab_deck",
        ["learner_id", "next_review_at"],
    )
    op.create_index(
        "ix_lvd_learner_entry",
        "learner_vocab_deck",
        ["learner_id", "vocab_entry_id"],
    )


def downgrade() -> None:
    op.drop_table("learner_vocab_deck")
    op.drop_table("learner_topics")
    op.drop_index("ix_vocab_entries_domain_dir", table_name="vocab_entries")
    op.drop_table("vocab_entries")
