"""SQLAlchemy 2.x models matching ARCHITECTURE.md §4."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from pgvector.sqlalchemy import Vector

try:
    from pgvector.sqlalchemy import Vector  # noqa: F811
except ImportError:  # pragma: no cover - test envs without pgvector
    Vector = None  # type: ignore[assignment,misc]


EMBEDDING_DIM = 1024


def _uuid_pk() -> Mapped[UUID]:
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)


def _ts(default_now: bool = False, nullable: bool = False) -> Mapped[datetime]:
    kwargs: dict = {"nullable": nullable}
    if default_now:
        kwargs["server_default"] = func.now()
    return mapped_column(DateTime(timezone=True), **kwargs)


class LearnerRow(Base):
    __tablename__ = "learners"

    id: Mapped[UUID] = _uuid_pk()
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    primary_lang: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _ts(default_now=True)

    __table_args__ = (
        CheckConstraint("primary_lang IN ('ko','en')", name="learners_lang_chk"),
    )


class SegmentRow(Base):
    __tablename__ = "segments"

    id: Mapped[UUID] = _uuid_pk()
    source_text: Mapped[str] = mapped_column(String, nullable=False)
    source_lang: Mapped[str] = mapped_column(String, nullable=False)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    register: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    difficulty_level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    audio_path: Mapped[str] = mapped_column(String, nullable=False)
    embedding_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("paraphrase_embeddings.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = _ts(default_now=True)

    __table_args__ = (
        CheckConstraint("source_lang IN ('ko','en')", name="segments_src_lang_chk"),
        CheckConstraint("target_lang IN ('ko','en')", name="segments_tgt_lang_chk"),
        CheckConstraint(
            "difficulty_level BETWEEN 1 AND 10", name="segments_difficulty_chk"
        ),
        Index("ix_segments_domain_difficulty", "domain", "difficulty_level"),
        Index("ix_segments_langs", "target_lang", "source_lang"),
    )


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[UUID] = _uuid_pk()
    learner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("learners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    state: Mapped[str] = mapped_column(String, nullable=False, default="idle")
    mode: Mapped[str] = mapped_column(
        String, nullable=False, default="interpretation", server_default="interpretation"
    )
    domain: Mapped[str] = mapped_column(String, nullable=False)
    source_lang: Mapped[str] = mapped_column(String, nullable=False)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = _ts(default_now=True)
    completed_at: Mapped[datetime | None] = _ts(nullable=True)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    replays_budget: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    current_segment_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("segments.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Pre-generated 10-pack for "daily training session" sessions. When set,
    # the picker walks these in order rather than querying the ladder.
    # Stored as a JSON array of UUID strings (e.g. ["uuid-1", "uuid-2"]).
    # Typed as list[str] so callers must defensively parse via UUID(...).
    planned_segment_ids: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    generation_params: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    generation_state: Mapped[str] = mapped_column(
        String, nullable=False, default="none"
    )

    learner: Mapped[LearnerRow] = relationship(lazy="joined")

    __table_args__ = (Index("ix_sessions_learner_started", "learner_id", "started_at"),)


class AttemptRow(Base):
    __tablename__ = "attempts"

    id: Mapped[UUID] = _uuid_pk()
    session_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    segment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("segments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    learner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("learners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    audio_path: Mapped[str] = mapped_column(String, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recorded_at: Mapped[datetime] = _ts()
    prosody_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    semantic_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    replayed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    closed_at: Mapped[datetime | None] = _ts(nullable=True)

    __table_args__ = (
        Index("ix_attempts_session_recorded", "session_id", "recorded_at"),
        Index(
            "ix_attempts_recency",
            "learner_id",
            "segment_id",
            "recorded_at",
        ),
    )


class MasteryScoreRow(Base):
    __tablename__ = "mastery_scores"

    learner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("learners.id", ondelete="CASCADE"),
        primary_key=True,
    )
    domain: Mapped[str] = mapped_column(String, primary_key=True)
    # Direction-specific PK extension (see migration 0007). Mastery on
    # en→ko is independent from ko→en because interpretation skill is
    # asymmetric in practice. Frontend groups by unordered pair for
    # display but the row is still keyed by direction.
    source_lang: Mapped[str] = mapped_column(String, primary_key=True)
    target_lang: Mapped[str] = mapped_column(String, primary_key=True)
    mastery: Mapped[float] = mapped_column(nullable=False, default=0.5)
    tier: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0, server_default="0"
    )
    recent_scores: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    attempts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempt_at: Mapped[datetime] = _ts()
    updated_at: Mapped[datetime] = _ts(default_now=True)

    __table_args__ = (
        CheckConstraint("mastery BETWEEN 0 AND 1", name="mastery_scores_mastery_chk"),
        CheckConstraint(
            "source_lang IN ('ko','en','es')", name="mastery_scores_src_lang_chk"
        ),
        CheckConstraint(
            "target_lang IN ('ko','en','es')", name="mastery_scores_tgt_lang_chk"
        ),
    )


class VocabEntryRow(Base):
    __tablename__ = "vocab_entries"

    id: Mapped[UUID] = _uuid_pk()
    term: Mapped[str] = mapped_column(String, nullable=False)
    definition: Mapped[str] = mapped_column(String, nullable=False)
    domain: Mapped[str] = mapped_column(String, nullable=False)
    source_lang: Mapped[str] = mapped_column(String, nullable=False)
    target_lang: Mapped[str] = mapped_column(String, nullable=False)
    register: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _ts(default_now=True)

    __table_args__ = (
        Index("ix_vocab_entries_domain_dir", "domain", "source_lang", "target_lang"),
    )


class LearnerTopicRow(Base):
    __tablename__ = "learner_topics"

    learner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("learners.id", ondelete="CASCADE"),
        primary_key=True,
    )
    domain: Mapped[str] = mapped_column(String, primary_key=True)
    added_at: Mapped[datetime] = _ts(default_now=True)


class LearnerVocabDeckRow(Base):
    __tablename__ = "learner_vocab_deck"

    id: Mapped[UUID] = _uuid_pk()
    learner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("learners.id", ondelete="CASCADE"),
        nullable=False,
    )
    vocab_entry_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("vocab_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    interval_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    ease_factor: Mapped[float] = mapped_column(nullable=False, default=2.5)
    repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_review_at: Mapped[datetime] = _ts(default_now=True)
    last_grade: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_reviewed_at: Mapped[datetime | None] = _ts(nullable=True)
    added_by: Mapped[str] = mapped_column(String, nullable=False)
    gap_type: Mapped[str | None] = mapped_column(String, nullable=True)
    source_attempt_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = _ts(default_now=True)
    updated_at: Mapped[datetime] = _ts(default_now=True)

    __table_args__ = (
        Index("ix_lvd_learner_due", "learner_id", "next_review_at"),
        Index("ix_lvd_learner_entry", "learner_id", "vocab_entry_id"),
    )


class ParaphraseEmbeddingRow(Base):
    __tablename__ = "paraphrase_embeddings"

    id: Mapped[UUID] = _uuid_pk()
    segment_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("segments.id", ondelete="CASCADE"),
        nullable=False,
    )
    paraphrase: Mapped[str] = mapped_column(String, nullable=False)
    # pgvector column; when Vector is unavailable (e.g. SQLite tests), this is
    # patched out in the test fixtures.
    if Vector is not None:
        embedding: Mapped[list[float]] = mapped_column(
            Vector(EMBEDDING_DIM), nullable=False
        )
    else:  # pragma: no cover
        embedding: Mapped[list[float]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _ts(default_now=True)

    __table_args__ = (Index("ix_paraphrase_embeddings_segment", "segment_id"),)


class GeneratedSetRow(Base):
    """A complete generated scenario, keyed for cross-learner reuse.

    `id` is deterministic — `uuid5` of the sorted segment_ids — so
    re-recording the identical set is idempotent. The pool key is
    `(prompt_template_hash, prompt_vars_hash)`; `template_hash` already
    encodes the prompt text, every rendered variable, and `n`, so any
    prompt edit or param change yields a fresh pool automatically.
    """

    __tablename__ = "generated_sets"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    prompt_template_hash: Mapped[str] = mapped_column(String, nullable=False)
    prompt_vars_hash: Mapped[str] = mapped_column(String, nullable=False)
    scenario_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    # Ordered list of segment-id strings — the cohesive scenario.
    segment_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _ts(default_now=True)

    __table_args__ = (
        Index("ix_generated_sets_keys", "prompt_template_hash", "prompt_vars_hash"),
    )


class LearnerSeenSetRow(Base):
    """Ledger of generated sets a learner has been *served* (assigned).

    Written in the same transaction that sets `planned_segment_ids`, so a
    learner is never assigned the same set twice — assignment, not attempt,
    marks a set seen (a network drop before the first attempt does not
    re-expose it).
    """

    __tablename__ = "learner_seen_sets"

    learner_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("learners.id", ondelete="CASCADE"),
        primary_key=True,
    )
    set_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    assigned_at: Mapped[datetime] = _ts(default_now=True)
