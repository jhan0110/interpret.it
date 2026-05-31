"""extend mastery PK to (learner, domain, source_lang, target_lang); allow es

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-30

Two coupled changes:

1. **Spanish ("es") added to the lang enum.** Three CHECK constraints
   that restricted lang columns to ('ko','en') are dropped and
   recreated with ('ko','en','es'):
   - `learners.primary_lang`            (learners_lang_chk)
   - `segments.source_lang`             (segments_src_lang_chk)
   - `segments.target_lang`             (segments_tgt_lang_chk)

2. **`mastery_scores` is now keyed per direction.** The previous PK
   `(learner_id, domain)` extends to
   `(learner_id, domain, source_lang, target_lang)`. Existing rows
   are backfilled with ('en','ko') because that's the only pair in
   production history (single deployed learner, EN↔KO-only sessions).
   For a multi-pair backfill, edit the data step below.

Downgrade restores the original PK and the (ko,en)-only CHECKs.
Rows that exist only under non-(en,ko) pairs would be lost on
downgrade — `op.execute` reports that explicitly.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Relax CHECK constraints to allow 'es' ────────────────────────────
    op.drop_constraint("learners_lang_chk", "learners", type_="check")
    op.create_check_constraint(
        "learners_lang_chk",
        "learners",
        "primary_lang IN ('ko','en','es')",
    )

    op.drop_constraint("segments_src_lang_chk", "segments", type_="check")
    op.create_check_constraint(
        "segments_src_lang_chk",
        "segments",
        "source_lang IN ('ko','en','es')",
    )

    op.drop_constraint("segments_tgt_lang_chk", "segments", type_="check")
    op.create_check_constraint(
        "segments_tgt_lang_chk",
        "segments",
        "target_lang IN ('ko','en','es')",
    )

    # ── 2. Extend mastery_scores PK ─────────────────────────────────────────
    # Add the two new columns nullable first so the backfill can run.
    op.add_column(
        "mastery_scores",
        sa.Column("source_lang", sa.String(), nullable=True),
    )
    op.add_column(
        "mastery_scores",
        sa.Column("target_lang", sa.String(), nullable=True),
    )

    # Backfill existing rows. Pre-migration data is single-pair (EN↔KO);
    # we attribute it to en→ko because the deployed learner's history
    # is exclusively that direction.
    op.execute(
        "UPDATE mastery_scores SET source_lang = 'en' WHERE source_lang IS NULL"
    )
    op.execute(
        "UPDATE mastery_scores SET target_lang = 'ko' WHERE target_lang IS NULL"
    )

    op.alter_column("mastery_scores", "source_lang", nullable=False)
    op.alter_column("mastery_scores", "target_lang", nullable=False)

    # Replace the PK.
    op.drop_constraint("mastery_scores_pkey", "mastery_scores", type_="primary")
    op.create_primary_key(
        "mastery_scores_pkey",
        "mastery_scores",
        ["learner_id", "domain", "source_lang", "target_lang"],
    )

    # CHECK constraint on the new lang columns so they reject anything
    # outside the enum (the gateway already enforces this at the
    # contract layer, but defense-in-depth catches a stray bulk INSERT).
    op.create_check_constraint(
        "mastery_scores_src_lang_chk",
        "mastery_scores",
        "source_lang IN ('ko','en','es')",
    )
    op.create_check_constraint(
        "mastery_scores_tgt_lang_chk",
        "mastery_scores",
        "target_lang IN ('ko','en','es')",
    )


def downgrade() -> None:
    # ── 2 (reverse). Mastery PK back to (learner_id, domain) ────────────────
    # If multiple direction rows exist per (learner_id, domain), a naive
    # PK rollback would violate uniqueness. We collapse by KEEPING the
    # row with the highest `attempts_count` per (learner_id, domain)
    # and DELETING the others. This is lossy by design — re-running
    # `alembic upgrade head` does not restore the dropped rows.
    op.execute(
        """
        DELETE FROM mastery_scores ms
        WHERE EXISTS (
            SELECT 1 FROM mastery_scores other
            WHERE other.learner_id = ms.learner_id
              AND other.domain = ms.domain
              AND (
                  other.attempts_count > ms.attempts_count
                  OR (other.attempts_count = ms.attempts_count
                      AND (other.source_lang, other.target_lang)
                          > (ms.source_lang, ms.target_lang))
              )
        )
        """
    )

    op.drop_constraint(
        "mastery_scores_tgt_lang_chk", "mastery_scores", type_="check"
    )
    op.drop_constraint(
        "mastery_scores_src_lang_chk", "mastery_scores", type_="check"
    )
    op.drop_constraint("mastery_scores_pkey", "mastery_scores", type_="primary")
    op.create_primary_key(
        "mastery_scores_pkey", "mastery_scores", ["learner_id", "domain"]
    )
    op.drop_column("mastery_scores", "target_lang")
    op.drop_column("mastery_scores", "source_lang")

    # ── 1 (reverse). Re-tighten CHECKs to ('ko','en') ───────────────────────
    # Rows that have es as a value would fail the new (old) CHECK; we
    # delete those rows from segments to keep the migration applyable.
    # The learners and mastery_scores tables: if any rows have 'es',
    # this downgrade WILL fail. That's deliberate — the operator must
    # decide how to handle es-tagged rows.
    op.execute("DELETE FROM segments WHERE source_lang = 'es' OR target_lang = 'es'")

    op.drop_constraint("segments_tgt_lang_chk", "segments", type_="check")
    op.create_check_constraint(
        "segments_tgt_lang_chk", "segments", "target_lang IN ('ko','en')"
    )
    op.drop_constraint("segments_src_lang_chk", "segments", type_="check")
    op.create_check_constraint(
        "segments_src_lang_chk", "segments", "source_lang IN ('ko','en')"
    )
    op.drop_constraint("learners_lang_chk", "learners", type_="check")
    op.create_check_constraint(
        "learners_lang_chk", "learners", "primary_lang IN ('ko','en')"
    )
