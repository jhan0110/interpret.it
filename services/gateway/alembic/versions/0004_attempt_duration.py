"""attempt duration tracking

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-19

Adds `duration_ms` to the `attempts` table so the learner-overview
endpoint can sum total interpreted audio time per learner.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "attempts",
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("attempts", "duration_ms")
