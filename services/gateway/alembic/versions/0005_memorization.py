"""memorization mode + replay budget

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-22

Adds the columns needed for Memorization Practice sessions:

- `sessions.mode` — 'interpretation' | 'memorization', defaults to
  'interpretation' so every existing row keeps today's behavior.
- `sessions.replays_budget` — initial replay allowance (default 5).
  Only meaningful for memorization sessions; harmless on interpretation.
- `attempts.replayed` — whether the learner used a replay on this segment.
  Memorization sessions cap this at 1 replay per segment and (budget) per
  session; the remaining budget is derived as
  ``replays_budget - count(attempts.replayed=true)`` so no second counter
  is needed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "mode",
            sa.String(length=32),
            nullable=False,
            server_default="interpretation",
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "replays_budget",
            sa.SmallInteger(),
            nullable=False,
            server_default="5",
        ),
    )
    op.add_column(
        "attempts",
        sa.Column(
            "replayed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("attempts", "replayed")
    op.drop_column("sessions", "replays_budget")
    op.drop_column("sessions", "mode")
