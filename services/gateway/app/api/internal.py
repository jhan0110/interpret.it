"""Internal RPC: analysis workers POST results here.

Analysis never writes the DB directly. When a worker finishes a prosody
or semantic job, it POSTs the result JSON to the gateway, which:

1. Persists into `attempts.prosody_result` / `attempts.semantic_result`.
2. Updates session state when both pipelines are closed.
3. Emits the matching `ProsodyResult` / `SemanticResult` and (when both
   close) the `MasteryUpdate` to the WS connection.

For Phase 2 we persist + record. Live WS fan-out is wired in
`session_socket.py` via a pub/sub layer in a follow-up. This endpoint
returns 202 on accept.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.contracts.models import ProsodyResult, SemanticResult
from app.db import sessionmaker_factory
from app.engine.difficulty_ladder import (
    combined_score,
    difficulty_delta,
    update_mastery,
)
from app.models.tables import AttemptRow, MasteryScoreRow, SessionRow

router = APIRouter(prefix="/internal", tags=["internal"])


async def _close_if_ready(attempt_id: UUID) -> None:
    """Promote attempt → closed_at + update mastery when both results land."""
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (
            await db.execute(select(AttemptRow).where(AttemptRow.id == attempt_id))
        ).scalar_one_or_none()
        if row is None or row.prosody_result is None or row.semantic_result is None:
            return
        if row.closed_at is not None:
            return

        sem_score = float(row.semantic_result.get("overall_score", 0.0))
        load = row.prosody_result.get("cognitive_load_estimate", "moderate")
        score = combined_score(sem_score, load)

        session_row = (
            await db.execute(select(SessionRow).where(SessionRow.id == row.session_id))
        ).scalar_one_or_none()
        if session_row is None:
            return
        domain = session_row.domain

        ms = (
            await db.execute(
                select(MasteryScoreRow).where(
                    MasteryScoreRow.learner_id == row.learner_id,
                    MasteryScoreRow.domain == domain,
                )
            )
        ).scalar_one_or_none()
        if ms is None:
            ms = MasteryScoreRow(
                learner_id=row.learner_id,
                domain=domain,
                mastery=0.5,
                attempts_count=0,
                last_attempt_at=datetime.now(UTC),
            )
            db.add(ms)
        old = float(ms.mastery)
        new = update_mastery(old, ms.attempts_count, score)
        ms.mastery = new
        ms.attempts_count += 1
        ms.last_attempt_at = datetime.now(UTC)
        _ = difficulty_delta(old, new)  # consumed when picking the next segment

        row.closed_at = datetime.now(UTC)
        await db.commit()


@router.post("/prosody_result")
async def prosody_result(result: ProsodyResult) -> dict:
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (
            await db.execute(select(AttemptRow).where(AttemptRow.id == result.attempt_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="attempt not found")
        row.prosody_result = result.model_dump(mode="json")
        await db.commit()
    await _close_if_ready(result.attempt_id)
    return {"accepted": True}


@router.post("/semantic_result")
async def semantic_result(result: SemanticResult) -> dict:
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (
            await db.execute(select(AttemptRow).where(AttemptRow.id == result.attempt_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="attempt not found")
        row.semantic_result = result.model_dump(mode="json")
        await db.commit()
    await _close_if_ready(result.attempt_id)
    return {"accepted": True}
