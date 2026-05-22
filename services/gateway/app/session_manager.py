"""Session persistence + state mutation helpers.

The gateway is the single writer to the DB (per CLAUDE.md). This module
wraps the SQLAlchemy operations that the WS handler and REST endpoints
both need; everything else goes through it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import sessionmaker_factory
from app.models.tables import (
    AttemptRow,
    LearnerRow,
    SegmentRow,
    SessionRow,
)


class SessionNotFound(Exception):
    pass


@dataclass
class SessionSnapshot:
    session_id: UUID
    learner_id: UUID
    state: str
    domain: str
    source_lang: str
    target_lang: str
    current_segment_id: UUID | None
    current_source_text: str
    current_register: str
    current_difficulty: int
    segment_count: int
    planned_count: int


async def _session_row(session: AsyncSession, sid: UUID) -> SessionRow:
    row = (await session.execute(select(SessionRow).where(SessionRow.id == sid))).scalar_one_or_none()
    if row is None:
        raise SessionNotFound(str(sid))
    return row


async def snapshot(session_id: UUID) -> SessionSnapshot:
    sessionmaker = sessionmaker_factory()
    async with sessionmaker() as db:
        row = await _session_row(db, session_id)
        seg_text = ""
        seg_register = "informal"
        seg_difficulty = 1
        if row.current_segment_id is not None:
            seg = (
                await db.execute(select(SegmentRow).where(SegmentRow.id == row.current_segment_id))
            ).scalar_one_or_none()
            if seg is not None:
                seg_text = seg.source_text
                seg_register = seg.register
                seg_difficulty = seg.difficulty_level

        return SessionSnapshot(
            session_id=row.id,
            learner_id=row.learner_id,
            state=row.state,
            domain=row.domain,
            source_lang=row.source_lang,
            target_lang=row.target_lang,
            current_segment_id=row.current_segment_id,
            current_source_text=seg_text,
            current_register=seg_register,
            current_difficulty=seg_difficulty,
            segment_count=row.segment_count,
            planned_count=len(row.planned_segment_ids or []),
        )


async def set_state(session_id: UUID, new_state: str) -> None:
    sessionmaker = sessionmaker_factory()
    async with sessionmaker() as db:
        row = await _session_row(db, session_id)
        row.state = new_state
        if new_state == "complete":
            row.completed_at = datetime.now(UTC)
        await db.commit()


async def create_session(
    learner_id: UUID,
    domain: str,
    source_lang: str,
    target_lang: str,
    generation_params: dict | None = None,
) -> SessionRow:
    sessionmaker = sessionmaker_factory()
    async with sessionmaker() as db:
        learner = (
            await db.execute(select(LearnerRow).where(LearnerRow.id == learner_id))
        ).scalar_one_or_none()
        if learner is None:
            raise SessionNotFound(f"learner {learner_id} not found")
        row = SessionRow(
            id=uuid4(),
            learner_id=learner_id,
            state="idle",
            domain=domain,
            source_lang=source_lang,
            target_lang=target_lang,
            segment_count=0,
            generation_params=generation_params,
            generation_state="pending" if generation_params else "none",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row


async def persist_attempt(
    *,
    session_id: UUID,
    attempt_id: UUID,
    segment_id: UUID,
    audio_path: str,
    recorded_at: datetime,
    duration_ms: int = 0,
) -> SessionSnapshot:
    sessionmaker = sessionmaker_factory()
    async with sessionmaker() as db:
        row = await _session_row(db, session_id)
        attempt = AttemptRow(
            id=attempt_id,
            session_id=session_id,
            segment_id=segment_id,
            learner_id=row.learner_id,
            audio_path=audio_path,
            duration_ms=duration_ms,
            recorded_at=recorded_at,
        )
        db.add(attempt)
        await db.commit()
    return await snapshot(session_id)
