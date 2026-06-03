"""shared-pool reuse: generated_sets + learner_seen_sets

Revision ID: 0009
Revises: 0008
Create Date: 2026-06-02

Two additive tables that implement cross-learner reuse of generated
training scenarios (the "shared pool" CLAUDE.md describes but the code
never had):

- `generated_sets` — a complete cohesive scenario, keyed by
  `(prompt_template_hash, prompt_vars_hash)`. `id` is deterministic
  (`uuid5` of the sorted segment_ids), so re-recording the same set is
  idempotent.
- `learner_seen_sets` — ledger of sets a learner has been *served*,
  written in the same transaction that assigns the session plan. The
  pool query excludes these, so a learner is never served the same set
  twice.

Purely additive — no existing table or constraint changes, no new
required env var. Downgrade drops both tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0009"
down_revision: str | None = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "generated_sets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("prompt_template_hash", sa.String(), nullable=False),
        sa.Column("prompt_vars_hash", sa.String(), nullable=False),
        sa.Column("scenario_summary", sa.String(), nullable=True),
        sa.Column("segment_ids", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_generated_sets_keys",
        "generated_sets",
        ["prompt_template_hash", "prompt_vars_hash"],
    )

    op.create_table(
        "learner_seen_sets",
        sa.Column(
            "learner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "set_id", postgresql.UUID(as_uuid=True), primary_key=True
        ),
        sa.Column(
            "assigned_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("learner_seen_sets")
    op.drop_index("ix_generated_sets_keys", table_name="generated_sets")
    op.drop_table("generated_sets")
