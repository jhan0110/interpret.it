"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-14

Mirrors ARCHITECTURE.md §4. pgvector extension is required on the target DB.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = 1024


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "learners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.String(), nullable=False),
        sa.Column("primary_lang", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("primary_lang IN ('ko','en')", name="learners_lang_chk"),
    )

    op.create_table(
        "paraphrase_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paraphrase", sa.String(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_paraphrase_embeddings_segment", "paraphrase_embeddings", ["segment_id"])

    op.create_table(
        "segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_text", sa.String(), nullable=False),
        sa.Column("source_lang", sa.String(), nullable=False),
        sa.Column("target_lang", sa.String(), nullable=False),
        sa.Column("register", sa.String(), nullable=False),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("difficulty_level", sa.SmallInteger(), nullable=False),
        sa.Column("audio_path", sa.String(), nullable=False),
        sa.Column(
            "embedding_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("paraphrase_embeddings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_lang IN ('ko','en')", name="segments_src_lang_chk"),
        sa.CheckConstraint("target_lang IN ('ko','en')", name="segments_tgt_lang_chk"),
        sa.CheckConstraint("difficulty_level BETWEEN 1 AND 10", name="segments_difficulty_chk"),
    )
    op.create_index("ix_segments_domain_difficulty", "segments", ["domain", "difficulty_level"])
    op.create_index("ix_segments_langs", "segments", ["target_lang", "source_lang"])

    op.create_foreign_key(
        "paraphrase_embeddings_segment_fk",
        "paraphrase_embeddings",
        "segments",
        ["segment_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "learner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learners.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("state", sa.String(), nullable=False, server_default="idle"),
        sa.Column("domain", sa.String(), nullable=False),
        sa.Column("source_lang", sa.String(), nullable=False),
        sa.Column("target_lang", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("segment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "current_segment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("segments.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_sessions_learner_started", "sessions", ["learner_id", "started_at"])

    op.create_table(
        "attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "segment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("segments.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "learner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learners.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("audio_path", sa.String(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prosody_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("semantic_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_attempts_session_recorded", "attempts", ["session_id", "recorded_at"])
    op.create_index("ix_attempts_recency", "attempts", ["learner_id", "segment_id", "recorded_at"])

    op.create_table(
        "mastery_scores",
        sa.Column(
            "learner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("learners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("domain", sa.String(), primary_key=True),
        sa.Column("mastery", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("attempts_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("mastery BETWEEN 0 AND 1", name="mastery_scores_mastery_chk"),
    )

    op.execute(
        "CREATE INDEX ix_paraphrase_embeddings_cosine ON paraphrase_embeddings "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.drop_table("mastery_scores")
    op.drop_table("attempts")
    op.drop_index("ix_sessions_learner_started", table_name="sessions")
    op.drop_table("sessions")
    op.drop_constraint("paraphrase_embeddings_segment_fk", "paraphrase_embeddings", type_="foreignkey")
    op.drop_index("ix_segments_langs", table_name="segments")
    op.drop_index("ix_segments_domain_difficulty", table_name="segments")
    op.drop_table("segments")
    op.drop_index("ix_paraphrase_embeddings_segment", table_name="paraphrase_embeddings")
    op.drop_table("paraphrase_embeddings")
    op.drop_table("learners")
