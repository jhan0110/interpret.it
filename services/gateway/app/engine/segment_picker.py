"""DB-side glue for the difficulty-ladder selector.

`select_next_segment()` in `difficulty_ladder.py` is pure logic — it operates
on already-fetched candidate lists. This module is the IO half: turn a
session_id into a concrete `SegmentRow`, persist `current_segment_id`, and
return the row plus the difficulty level used.

Cascade on miss: try the target difficulty first; if no candidate survives
the recency + novelty filters, widen the band by ±1, then ±2.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.difficulty_ladder import (
    AttemptScoreView,
    CandidateSegment,
    LearnerHistoryItem,
    aggregate_history,
    select_next_segment,
    target_level_from_mastery,
)
from app.models.tables import (
    AttemptRow,
    MasteryScoreRow,
    ParaphraseEmbeddingRow,
    SegmentRow,
    SessionRow,
)

RECENT_ATTEMPT_WINDOW = 5
DEFAULT_MASTERY = 0.5


@dataclass(frozen=True)
class PickedSegment:
    segment: SegmentRow
    difficulty_level: int


def _to_candidate(row: SegmentRow, embedding: list[float] | None) -> CandidateSegment:
    return CandidateSegment(
        id=row.id,
        difficulty_level=row.difficulty_level,
        domain=row.domain,
        register=row.register,
        source_lang=row.source_lang,
        target_lang=row.target_lang,
        embedding=embedding,
    )


async def _recent_attempts(
    db: AsyncSession, learner_id: UUID, limit: int
) -> list[AttemptRow]:
    rows = (
        await db.execute(
            select(AttemptRow)
            .where(AttemptRow.learner_id == learner_id)
            .order_by(AttemptRow.recorded_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


def _attempts_to_views(attempts: list[AttemptRow]) -> list[AttemptScoreView]:
    views: list[AttemptScoreView] = []
    for a in attempts:
        score: float | None = None
        if a.semantic_result is not None:
            raw = a.semantic_result.get("overall_score")
            score = float(raw) if raw is not None else None
        views.append(AttemptScoreView(segment_id=a.segment_id, overall_score=score))
    return views


async def _candidate_rows(
    db: AsyncSession,
    *,
    domain: str,
    difficulty_level: int,
    source_lang: str,
    target_lang: str,
) -> list[SegmentRow]:
    stmt = select(SegmentRow).where(
        SegmentRow.domain == domain,
        SegmentRow.difficulty_level == difficulty_level,
        SegmentRow.source_lang == source_lang,
        SegmentRow.target_lang == target_lang,
    )
    return list((await db.execute(stmt)).scalars().all())


async def _embeddings_for_segments(
    db: AsyncSession, segment_ids: list[UUID]
) -> dict[UUID, list[float]]:
    if not segment_ids:
        return {}
    rows = (
        await db.execute(
            select(ParaphraseEmbeddingRow).where(
                ParaphraseEmbeddingRow.segment_id.in_(segment_ids)
            )
        )
    ).scalars().all()
    out: dict[UUID, list[float]] = {}
    for r in rows:
        # Multiple paraphrases per segment may exist; the novelty check
        # only needs one representative vector, so last-write-wins is fine.
        out[r.segment_id] = list(r.embedding) if r.embedding is not None else []
    return out


async def _pick_at_level(
    db: AsyncSession,
    *,
    session_row: SessionRow,
    level: int,
    recent_segment_ids: set[UUID],
    recent_embeddings: list[list[float]],
    history: dict[UUID, LearnerHistoryItem],
) -> SegmentRow | None:
    rows = await _candidate_rows(
        db,
        domain=session_row.domain,
        difficulty_level=level,
        source_lang=session_row.source_lang,
        target_lang=session_row.target_lang,
    )
    if not rows:
        return None
    embeddings = await _embeddings_for_segments(db, [r.id for r in rows])
    candidates = [_to_candidate(r, embeddings.get(r.id)) for r in rows]
    picked = select_next_segment(
        candidates=candidates,
        recent_segment_ids=recent_segment_ids,
        recent_embeddings=recent_embeddings,
        history=history,
    )
    if picked is None:
        return None
    return next(r for r in rows if r.id == picked.id)


async def _pick_from_plan(
    db: AsyncSession, session_row: SessionRow
) -> PickedSegment | None:
    """Walk `session.planned_segment_ids` in order; return the next unattempted.

    For daily-training-session sessions the operator chose 10 phrases up
    front (the pre-generation flow) — we walk them deterministically
    rather than going through the ladder picker.
    """
    plan = session_row.planned_segment_ids
    if not plan:
        return None
    attempted = {
        a.segment_id
        for a in (
            await db.execute(
                select(AttemptRow).where(
                    AttemptRow.session_id == session_row.id
                )
            )
        ).scalars().all()
    }
    for sid_str in plan:
        try:
            sid = UUID(sid_str) if isinstance(sid_str, str) else sid_str
        except (TypeError, ValueError):
            continue
        if sid in attempted:
            continue
        row = (
            await db.execute(select(SegmentRow).where(SegmentRow.id == sid))
        ).scalar_one_or_none()
        if row is None:
            continue
        session_row.current_segment_id = row.id
        session_row.segment_count = (session_row.segment_count or 0) + 1
        await db.commit()
        await db.refresh(row)
        return PickedSegment(segment=row, difficulty_level=row.difficulty_level)
    return None


async def pick_segment_for_session(
    db: AsyncSession, session_id: UUID
) -> PickedSegment | None:
    """Pick the next segment for a session and persist `current_segment_id`.

    For pre-generated daily-training sessions, walks `planned_segment_ids`
    in order. Otherwise queries the ladder using mastery + recency.
    Returns None when nothing survives.
    """
    session_row = (
        await db.execute(select(SessionRow).where(SessionRow.id == session_id))
    ).scalar_one_or_none()
    if session_row is None:
        return None

    # A planned (daily-training) session is strictly bounded by its plan:
    # once the plan is exhausted we return None rather than falling through
    # to the open-ended ladder picker.
    if session_row.planned_segment_ids:
        return await _pick_from_plan(db, session_row)

    mastery_row = (
        await db.execute(
            select(MasteryScoreRow).where(
                MasteryScoreRow.learner_id == session_row.learner_id,
                MasteryScoreRow.domain == session_row.domain,
            )
        )
    ).scalar_one_or_none()
    mastery = float(mastery_row.mastery) if mastery_row is not None else DEFAULT_MASTERY
    target = target_level_from_mastery(mastery)

    recent = await _recent_attempts(
        db, session_row.learner_id, RECENT_ATTEMPT_WINDOW
    )
    recent_segment_ids = {a.segment_id for a in recent}
    recent_embeddings_map = await _embeddings_for_segments(
        db, list(recent_segment_ids)
    )
    recent_embeddings = [v for v in recent_embeddings_map.values() if v]
    history = aggregate_history(_attempts_to_views(recent))

    # Cascade walks outward from the target across the full 1..10 ladder so
    # a small seed (or a learner whose target sits at an empty level) can
    # still find something. If everything is excluded by recency, retry
    # once with recency relaxed — better to repeat than to dead-end.
    def _cascade(t: int) -> list[int]:
        seen: list[int] = []
        for delta in range(0, 10):
            for sign in (0,) if delta == 0 else (-1, +1):
                lvl = t + sign * delta
                if 1 <= lvl <= 10 and lvl not in seen:
                    seen.append(lvl)
        return seen

    chosen: SegmentRow | None = None
    chosen_level: int = target
    for recency_set in (recent_segment_ids, set()):
        for level in _cascade(target):
            chosen = await _pick_at_level(
                db,
                session_row=session_row,
                level=level,
                recent_segment_ids=recency_set,
                recent_embeddings=recent_embeddings,
                history=history,
            )
            if chosen is not None:
                chosen_level = level
                break
        if chosen is not None:
            break

    if chosen is None:
        return None

    session_row.current_segment_id = chosen.id
    session_row.segment_count = (session_row.segment_count or 0) + 1
    await db.commit()
    await db.refresh(chosen)
    return PickedSegment(segment=chosen, difficulty_level=chosen_level)
