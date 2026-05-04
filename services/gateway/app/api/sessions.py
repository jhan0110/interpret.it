"""REST routes for sessions + learners + mastery."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import func, select

from app.contracts.models import (
    CompleteSessionResponse,
    Learner,
    PostSessionRequest,
    Session,
)
from app.contracts.models import GetLearnerMasteryResponse, MasteryScore
from app.db import sessionmaker_factory
from app.models.tables import (
    AttemptRow,
    LearnerRow,
    MasteryScoreRow,
    SessionRow,
)
from app.session_manager import SessionNotFound, create_session

router = APIRouter()


def _row_to_session(row: SessionRow) -> Session:
    return Session.model_validate(
        {
            "id": row.id,
            "learner_id": row.learner_id,
            "state": row.state,
            "domain": row.domain,
            "target_lang": row.target_lang,
            "source_lang": row.source_lang,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "segment_count": row.segment_count,
            "current_segment_id": row.current_segment_id,
        }
    )


@router.post("/sessions", response_model=Session)
async def post_session(body: PostSessionRequest) -> Session:
    try:
        row = await create_session(
            learner_id=body.learner_id,
            domain=body.domain,
            source_lang=body.source_lang,
            target_lang=body.target_lang,
        )
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _row_to_session(row)


@router.get("/sessions/{session_id}", response_model=Session)
async def get_session(session_id: UUID) -> Session:
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (await db.execute(select(SessionRow).where(SessionRow.id == session_id))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="session not found")
        return _row_to_session(row)


@router.post("/sessions/{session_id}/complete", response_model=CompleteSessionResponse)
async def complete_session(session_id: UUID) -> CompleteSessionResponse:
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (await db.execute(select(SessionRow).where(SessionRow.id == session_id))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="session not found")
        attempts = (
            await db.execute(select(AttemptRow).where(AttemptRow.session_id == session_id))
        ).scalars().all()
        attempts_count = len(attempts)
        scores = [
            (a.semantic_result or {}).get("overall_score", 0.0)
            for a in attempts
            if a.semantic_result
        ]
        mean = sum(scores) / len(scores) if scores else 0.0

        if row.state != "complete":
            row.state = "complete"
            row.completed_at = func.now()
            await db.commit()
            await db.refresh(row)

    return CompleteSessionResponse(
        session=_row_to_session(row),
        attempts_count=attempts_count,
        mean_score=max(0.0, min(1.0, mean)),
        mastery_changes=[],
    )


@router.get("/learners/{learner_id}", response_model=Learner)
async def get_learner(learner_id: UUID) -> Learner:
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (await db.execute(select(LearnerRow).where(LearnerRow.id == learner_id))).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="learner not found")
        return Learner.model_validate(
            {
                "id": row.id,
                "display_name": row.display_name,
                "primary_lang": row.primary_lang,
                "created_at": row.created_at,
            }
        )


@router.get("/learners/{learner_id}/mastery", response_model=GetLearnerMasteryResponse)
async def get_learner_mastery(learner_id: UUID) -> GetLearnerMasteryResponse:
    sm = sessionmaker_factory()
    async with sm() as db:
        rows = (
            await db.execute(select(MasteryScoreRow).where(MasteryScoreRow.learner_id == learner_id))
        ).scalars().all()
        scores = [
            MasteryScore.model_validate(
                {
                    "learner_id": r.learner_id,
                    "domain": r.domain,
                    "mastery": r.mastery,
                    "attempts_count": r.attempts_count,
                    "last_attempt_at": r.last_attempt_at,
                    "updated_at": r.updated_at,
                }
            )
            for r in rows
        ]
    return GetLearnerMasteryResponse(learner_id=learner_id, scores=scores)
