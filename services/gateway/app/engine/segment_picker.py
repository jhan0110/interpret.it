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
    """Return one representative embedding per segment.

    Multiple paraphrases per segment may exist; we deterministically
    pick the earliest one (`ORDER BY segment_id, created_at`) so the
    novelty filter doesn't flip-flop between calls.
    """
    if not segment_ids:
        return {}
    # SQLAlchemy's DISTINCT ON is dialect-specific; build it via
    # `.distinct(column)` which Postgres maps to DISTINCT ON.
    stmt = (
        select(ParaphraseEmbeddingRow)
        .where(ParaphraseEmbeddingRow.segment_id.in_(segment_ids))
        .order_by(
            ParaphraseEmbeddingRow.segment_id,
            ParaphraseEmbeddingRow.created_at,
        )
        .distinct(ParaphraseEmbeddingRow.segment_id)
    )
    rows = (await db.execute(stmt)).scalars().all()
    out: dict[UUID, list[float]] = {}
    for r in rows:
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
    # Only fetch the segment_id column — full AttemptRow is overkill here
    # and adds a few KB per existing attempt.
    attempted_ids = set(
        (
            await db.execute(
                select(AttemptRow.segment_id).where(
                    AttemptRow.session_id == session_row.id
                )
            )
        )
        .scalars()
        .all()
    )
    for sid_str in plan:
        try:
            sid = UUID(sid_str) if isinstance(sid_str, str) else sid_str
        except (TypeError, ValueError):
            # A bad UUID in `planned_segment_ids` is data corruption,
            # not "plan exhausted" — log and skip so the next entry has
            # a chance, but loudly enough that ops can investigate.
            import logging

            logging.getLogger(__name__).warning(
                "planned_segment_ids: malformed UUID %r in session %s",
                sid_str,
                session_row.id,
            )
            continue
        if sid in attempted_ids:
            continue
        row = (
            await db.execute(select(SegmentRow).where(SegmentRow.id == sid))
        ).scalar_one_or_none()
        if row is None:
            import logging

            logging.getLogger(__name__).warning(
                "planned_segment_ids: missing segment %s in session %s — skipping",
                sid,
                session_row.id,
            )
            continue
        # Only persist `current_segment_id` here. `segment_count` is
        # bumped by `persist_attempt` once the learner has actually
        # produced an attempt — that way a network blip between
        # `segment.play` emission and `audio.submit` doesn't silently
        # consume a plan slot.
        session_row.current_segment_id = row.id
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

    # Planned session whose generation hasn't completed yet. Don't fall
    # through to the ladder picker — the ladder would search seed segments,
    # often find nothing in the requested domain, and surface a
    # "no candidate" error that's actually "not ready yet, try again in a
    # few seconds." Returning None here triggers the WS layer to send a
    # specific error code the frontend can interpret as "wait."
    if session_row.generation_params is not None and session_row.generation_state != "ready":
        return None

    mastery_row = (
        await db.execute(
            select(MasteryScoreRow).where(
                MasteryScoreRow.learner_id == session_row.learner_id,
                MasteryScoreRow.domain == session_row.domain,
                MasteryScoreRow.source_lang == session_row.source_lang,
                MasteryScoreRow.target_lang == session_row.target_lang,
            )
        )
    ).scalar_one_or_none()
    mastery = float(mastery_row.mastery) if mastery_row is not None else DEFAULT_MASTERY
    tier = int(mastery_row.tier) if mastery_row is not None else 0
    # Tier > 0 anchors the picker on the qualifying band for the NEXT tier
    # (so a Journeyman gets Practitioner-band segments — the picker is
    # always nudging the learner toward the threshold of their next rank).
    # At tier 0 we fall back to the legacy mastery scalar.
    if tier > 0:
        from app.engine.mastery_tier import MAX_TIER, next_tier_band

        if tier >= MAX_TIER:
            band = next_tier_band(tier - 1)
        else:
            band = next_tier_band(tier)
        target = (band[0] + band[1]) // 2
    else:
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

    # Cascade walks outward symmetrically: target first, then ±1, ±2, ...
    # Any level outside [1, 10] is silently skipped. For an edge target
    # (e.g. 1 or 10) this devolves to a one-sided walk, which is fine.
    def _cascade(t: int) -> list[int]:
        seen: list[int] = []

        def _push(lvl: int) -> None:
            if 1 <= lvl <= 10 and lvl not in seen:
                seen.append(lvl)

        _push(t)
        for delta in range(1, 10):
            _push(t - delta)
            _push(t + delta)
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

    # See `_pick_from_plan`: `segment_count` is bumped on attempt
    # persistence, not at pick time, so a WS-level failure between
    # the pick and the `segment.play` frame doesn't silently consume
    # a session slot.
    session_row.current_segment_id = chosen.id
    await db.commit()
    await db.refresh(chosen)
    return PickedSegment(segment=chosen, difficulty_level=chosen_level)
