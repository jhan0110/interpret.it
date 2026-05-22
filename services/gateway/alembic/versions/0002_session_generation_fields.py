"""session generation fields

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-16

Adds the columns that back the daily-training-session generation flow:
- `sessions.planned_segment_ids` — JSONB list of UUID strings; when set,
  the picker walks these in order rather than querying the ladder.
- `sessions.generation_params` — JSONB blob of the operator-supplied
  generation parameters (topics, user_level, duration, current_context)
  so the cache key + audit trail are persisted.
- `sessions.generation_state` — string enum ('none', 'pending', 'ready',
  'failed') for the frontend to render progress.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "planned_segment_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "generation_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "generation_state",
            sa.String(),
            nullable=False,
            server_default="none",
        ),
    )


def downgrade() -> None:
    op.drop_column("sessions", "generation_state")
    op.drop_column("sessions", "generation_params")
    op.drop_column("sessions", "planned_segment_ids")
