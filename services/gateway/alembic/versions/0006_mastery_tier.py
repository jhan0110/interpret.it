"""mastery tier + rolling score window

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-28

Adds level-based mastery tiers to `mastery_scores`:

- `tier` (smallint, default 0): the learner's high-water-mark tier in
  this domain. 0=Initiate, 1=Apprentice, 2=Journeyman, 3=Practitioner,
  4=Expert, 5=Master. Mapped to internal difficulty 1-10 in pairs
  (tier 1 = L1-2, tier 2 = L3-4, ...).
- `recent_scores` (JSONB, nullable): append-only rolling window of the
  most recent ~20 attempts in this domain, used to evaluate promotion
  without re-querying the full attempts table on every close. Shape:
  `[{"level": int, "score": float, "ts": iso8601}, ...]`.

The existing `mastery` EMA scalar is preserved as a fallback for the
segment picker when tier=0.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mastery_scores",
        sa.Column(
            "tier",
            sa.SmallInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "mastery_scores",
        sa.Column("recent_scores", JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("mastery_scores", "recent_scores")
    op.drop_column("mastery_scores", "tier")
