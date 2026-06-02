"""allow zh (Chinese) in the lang CHECK constraints

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-01

Adds Chinese ("zh") to the five CHECK constraints that restrict lang
columns to ('ko','en','es'). Without this, inserting a zh segment
raises CheckViolationError on `segments_src_lang_chk` and the
generation job fails at the `/internal/segments` push (the LLM step
itself succeeds — the segment text is valid Chinese).

Constraints relaxed to ('ko','en','es','zh'):
  - learners.primary_lang           (learners_lang_chk)
  - segments.source_lang            (segments_src_lang_chk)
  - segments.target_lang            (segments_tgt_lang_chk)
  - mastery_scores.source_lang      (mastery_scores_src_lang_chk)
  - mastery_scores.target_lang      (mastery_scores_tgt_lang_chk)

These are defense-in-depth: the gateway already enforces the Lang enum
at the contract layer. Mirrors 0007 (which added 'es').

Downgrade re-tightens to ('ko','en','es'). Any zh-tagged segments are
deleted so the old CHECK applies; if learners/mastery_scores rows carry
'zh', the downgrade WILL fail — deliberate, so the operator decides how
to handle them.
"""

from __future__ import annotations

from alembic import op


revision: str = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None

_TABLES = (
    ("learners_lang_chk", "learners", "primary_lang"),
    ("segments_src_lang_chk", "segments", "source_lang"),
    ("segments_tgt_lang_chk", "segments", "target_lang"),
    ("mastery_scores_src_lang_chk", "mastery_scores", "source_lang"),
    ("mastery_scores_tgt_lang_chk", "mastery_scores", "target_lang"),
)


def upgrade() -> None:
    for name, table, column in _TABLES:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(
            name, table, f"{column} IN ('ko','en','es','zh')"
        )


def downgrade() -> None:
    # Drop zh-tagged segments so the re-tightened CHECK applies. Rows in
    # learners / mastery_scores carrying 'zh' will block the downgrade.
    op.execute("DELETE FROM segments WHERE source_lang = 'zh' OR target_lang = 'zh'")
    for name, table, column in _TABLES:
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(
            name, table, f"{column} IN ('ko','en','es')"
        )
