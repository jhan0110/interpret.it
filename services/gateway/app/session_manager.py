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
    MasteryScoreRow,
    ParaphraseEmbeddingRow,
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


async def advance_segment(session_id: UUID, segment_id: UUID) -> "SessionSnapshot":
    """Pin segment_id on the session row and bump segment_count."""
    sessionmaker = sessionmaker_factory()
    async with sessionmaker() as db:
        row = await _session_row(db, session_id)
        row.current_segment_id = segment_id
        row.segment_count += 1
        await db.commit()
    return await snapshot(session_id)


async def pick_segment(
    session_id: UUID,
    domain: str,
    learner_id: UUID,
) -> SegmentRow | None:
    """Ladder-aware segment selector implementing ARCHITECTURE.md §6.

    Determines target difficulty from the learner's mastery score, then
    applies: recency exclusion → semantic novelty filter → mastery-weighted
    sampling.  Falls back gracefully when embeddings are absent (newly seeded
    segments or before the embedding pipeline has run).
    """
    from app.engine.difficulty_ladder import (
        CandidateSegment,
        LearnerHistoryItem,
        combined_score as _combined_score,
        select_next_segment,
    )

    sm = sessionmaker_factory()
    async with sm() as db:
        # 1. Derive target difficulty from current mastery (0 → level 1, 1 → level 10).
        ms_row = (
            await db.execute(
                select(MasteryScoreRow).where(
                    MasteryScoreRow.learner_id == learner_id,
                    MasteryScoreRow.domain == domain,
                )
            )
        ).scalar_one_or_none()
        mastery = float(ms_row.mastery) if ms_row is not None else 0.5
        target = max(1, min(10, round(mastery * 9) + 1))

        # 2. Candidate segments at target ± 1 in the same domain.
        lo = max(1, target - 1)
        hi = min(10, target + 1)
        candidate_rows: list[SegmentRow] = list(
            (
                await db.execute(
                    select(SegmentRow).where(
                        SegmentRow.domain == domain,
                        SegmentRow.difficulty_level.between(lo, hi),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not candidate_rows:
            return None

        # 3. Recent segment IDs from this session (recency exclusion).
        recent_rows = (
            await db.execute(
                select(AttemptRow.segment_id, AttemptRow.recorded_at)
                .where(AttemptRow.session_id == session_id)
                .order_by(AttemptRow.recorded_at.desc())
                .limit(24)
            )
        ).all()
        recent_segment_ids = {r.segment_id for r in recent_rows}

        # 4. Learner's closed attempt history → rolling score per segment.
        history_rows = (
            await db.execute(
                select(
                    AttemptRow.segment_id,
                    AttemptRow.semantic_result,
                    AttemptRow.prosody_result,
                ).where(
                    AttemptRow.learner_id == learner_id,
                    AttemptRow.closed_at.isnot(None),
                )
            )
        ).all()
        seg_scores: dict[UUID, list[float]] = {}
        for r in history_rows:
            sem = (
                float(r.semantic_result.get("overall_score", 0.5))
                if r.semantic_result
                else None
            )
            load = (
                r.prosody_result.get("cognitive_load_estimate")
                if r.prosody_result
                else None
            )
            seg_scores.setdefault(r.segment_id, []).append(_combined_score(sem, load))

        history: dict[UUID, LearnerHistoryItem] = {
            sid: LearnerHistoryItem(
                segment_id=sid,
                recent_score=sum(scores) / len(scores),
                last_seen_embedding=None,
            )
            for sid, scores in seg_scores.items()
        }

        # 5. Fetch embeddings for candidates (may be empty before pipeline runs).
        candidate_ids = [r.id for r in candidate_rows]
        emb_rows = (
            await db.execute(
                select(ParaphraseEmbeddingRow).where(
                    ParaphraseEmbeddingRow.segment_id.in_(candidate_ids)
                )
            )
        ).scalars().all()
        seg_embeddings: dict[UUID, list[float]] = {}
        for e in emb_rows:
            if e.segment_id not in seg_embeddings:
                seg_embeddings[e.segment_id] = list(e.embedding)

        # Embeddings of the last 5 seen segments for the novelty filter.
        recent_embeddings: list[list[float]] = []
        seen_emb: set[UUID] = set()
        for r in recent_rows[:5]:
            if r.segment_id in seen_emb:
                continue
            seen_emb.add(r.segment_id)
            if r.segment_id in seg_embeddings:
                recent_embeddings.append(seg_embeddings[r.segment_id])

        # 6. Build CandidateSegment objects and run the pure-logic selector.
        candidates = [
            CandidateSegment(
                id=r.id,
                difficulty_level=r.difficulty_level,
                domain=r.domain,
                register=r.register,
                source_lang=r.source_lang,
                target_lang=r.target_lang,
                embedding=seg_embeddings.get(r.id),
            )
            for r in candidate_rows
        ]
        chosen = select_next_segment(
            candidates=candidates,
            recent_segment_ids=recent_segment_ids,
            recent_embeddings=recent_embeddings,
            history=history,
        )
        if chosen is None:
            return None
        return next(r for r in candidate_rows if r.id == chosen.id)


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
