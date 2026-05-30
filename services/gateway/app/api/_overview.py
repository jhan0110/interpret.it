"""Helpers for the learner overview endpoint."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.models import MasteryScore
from app.engine.mastery_tier import progress_to_next
from app.models.tables import (
    AttemptRow,
    LearnerVocabDeckRow,
    MasteryScoreRow,
)


_STREAK_CAP_DAYS = 365


async def compute_streak(db: AsyncSession, learner_id: UUID) -> int:
    """Consecutive activity days ending today (or yesterday if no activity today).

    Activity = at least one AttemptRow.recorded_at on that UTC date OR
    at least one LearnerVocabDeckRow.last_reviewed_at on that UTC date.
    """
    # `func.date(<timestamptz>)` follows the session timezone. We
    # explicitly convert to UTC first so the streak bucket lines up
    # with the `datetime.now(UTC).date()` cursor below — otherwise
    # a Postgres `timezone` other than UTC silently shifts the
    # date boundary and streaks break around midnight.
    attempt_date_expr = func.date(func.timezone("UTC", AttemptRow.recorded_at))
    vocab_date_expr = func.date(
        func.timezone("UTC", LearnerVocabDeckRow.last_reviewed_at)
    )
    attempt_dates = (
        await db.execute(
            select(attempt_date_expr.distinct()).where(
                AttemptRow.learner_id == learner_id,
                AttemptRow.recorded_at.is_not(None),
            )
        )
    ).scalars().all()
    vocab_dates = (
        await db.execute(
            select(vocab_date_expr.distinct()).where(
                LearnerVocabDeckRow.learner_id == learner_id,
                LearnerVocabDeckRow.last_reviewed_at.is_not(None),
            )
        )
    ).scalars().all()

    active: set[date] = set()
    for d in list(attempt_dates) + list(vocab_dates):
        if isinstance(d, datetime):
            active.add(d.date())
        elif isinstance(d, date):
            active.add(d)

    if not active:
        return 0

    today = datetime.now(UTC).date()
    cursor = today if today in active else today - timedelta(days=1)
    streak = 0
    while cursor in active and streak < _STREAK_CAP_DAYS:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


async def load_mastery_scores(
    db: AsyncSession, learner_id: UUID
) -> list[MasteryScore]:
    rows = (
        await db.execute(
            select(MasteryScoreRow).where(MasteryScoreRow.learner_id == learner_id)
        )
    ).scalars().all()
    result: list[MasteryScore] = []
    for r in rows:
        tier_val = int(r.tier or 0)
        prog = progress_to_next(tier_val, r.recent_scores)
        result.append(
            MasteryScore.model_validate(
                {
                    "learner_id": r.learner_id,
                    "domain": r.domain,
                    "mastery": r.mastery,
                    "tier": tier_val,
                    "tier_name": prog.tier_name,
                    "next_tier_name": prog.next_tier_name,
                    "progress": prog.progress,
                    "attempts_count": r.attempts_count,
                    "last_attempt_at": r.last_attempt_at,
                    "updated_at": r.updated_at,
                }
            )
        )
    return result


async def sum_interpreted_seconds(db: AsyncSession, learner_id: UUID) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(AttemptRow.duration_ms), 0)).where(
            AttemptRow.learner_id == learner_id
        )
    )
    total_ms = int(result.scalar_one() or 0)
    return total_ms // 1000
