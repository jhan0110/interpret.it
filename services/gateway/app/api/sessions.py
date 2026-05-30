"""REST routes for sessions + learners + mastery."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, update

from pydantic import BaseModel

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
    SessionRow,
)
from app.queue import enqueue_generation
from app.quota import QuotaExceeded, consume_quota
from app.session_manager import SessionNotFound, create_session
from app.storage import signed_get_url
from app.ws_auth import mint_token

router = APIRouter()


def _row_to_session(row: SessionRow) -> Session:
    return Session.model_validate(
        {
            "id": row.id,
            "learner_id": row.learner_id,
            "mode": row.mode,
            "state": row.state,
            "domain": row.domain,
            "target_lang": row.target_lang,
            "source_lang": row.source_lang,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "segment_count": row.segment_count,
            "replays_budget": row.replays_budget,
            "current_segment_id": row.current_segment_id,
        }
    )


@router.post("/sessions", response_model=Session)
async def post_session(body: PostSessionRequest, force: bool = False) -> Session:
    gen_dict: dict | None = None
    if body.generation is not None:
        try:
            await consume_quota(body.learner_id, force=force)
        except QuotaExceeded as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        gen_dict = body.generation.model_dump(mode="json")
    try:
        row = await create_session(
            learner_id=body.learner_id,
            domain=body.domain,
            source_lang=body.source_lang,
            target_lang=body.target_lang,
            generation_params=gen_dict,
            mode=body.mode,
        )
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if gen_dict is not None:
        await enqueue_generation(
            session_id=row.id,
            learner_id=row.learner_id,
            domain=row.domain,
            source_lang=row.source_lang,
            target_lang=row.target_lang,
            generation_params=gen_dict,
        )
    return _row_to_session(row)


_AUDIO_URL_EXPIRES_S = 3600


class GetAttemptAudioUrlResponse(BaseModel):
    """Response for GET /sessions/{session_id}/attempts/{attempt_id}/audio_url.

    Mirrors REST.GetAttemptAudioUrlResponse in contracts/contracts.json.
    `audio_url` is a browser-reachable presigned MinIO GET URL valid for
    `expires_in_s` seconds. The URL is minted on each call — it is not
    cached. Clients should not store it beyond the expiry window.
    """

    audio_url: str
    expires_in_s: int


@router.get(
    "/sessions/{session_id}/attempts/{attempt_id}/audio_url",
    response_model=GetAttemptAudioUrlResponse,
)
async def get_attempt_audio_url(
    session_id: UUID, attempt_id: UUID
) -> GetAttemptAudioUrlResponse:
    """Mint a presigned MinIO GET URL for the recording of a single attempt.

    The attempt must belong to the given session; returns 404 if either the
    attempt is not found or the attempt has no audio_path stored yet.
    Read-only — does not modify the DB.
    """
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (
            await db.execute(
                select(AttemptRow).where(
                    AttemptRow.id == attempt_id,
                    AttemptRow.session_id == session_id,
                )
            )
        ).scalar_one_or_none()
    if row is None or not row.audio_path:
        raise HTTPException(status_code=404, detail="attempt audio not found")
    url = signed_get_url(row.audio_path, expires_in_s=_AUDIO_URL_EXPIRES_S)
    return GetAttemptAudioUrlResponse(audio_url=url, expires_in_s=_AUDIO_URL_EXPIRES_S)


@router.get("/sessions/{session_id}/attempts")
async def get_session_attempts(session_id: UUID) -> list[dict]:
    """Read-only: list attempts with their results for review.

    Returns minimal Attempt-like dicts; not in REST.* contract because
    review-page rendering predates that schema and we don't expose
    audio paths externally yet.
    """
    sm = sessionmaker_factory()
    async with sm() as db:
        rows = (
            await db.execute(
                select(AttemptRow).where(AttemptRow.session_id == session_id).order_by(AttemptRow.recorded_at)
            )
        ).scalars().all()
    return [
        {
            "id": str(r.id),
            "session_id": str(r.session_id),
            "segment_id": str(r.segment_id),
            "learner_id": str(r.learner_id),
            "audio_path": r.audio_path,
            "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            "prosody_result": r.prosody_result,
            "semantic_result": r.semantic_result,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        }
        for r in rows
    ]


@router.get("/sessions/{session_id}/summary", response_model=CompleteSessionResponse)
async def get_session_summary(session_id: UUID) -> CompleteSessionResponse:
    """Read-only summary — does NOT mutate state (unlike POST /complete)."""
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
    return CompleteSessionResponse(
        session=_row_to_session(row),
        attempts_count=attempts_count,
        mean_score=max(0.0, min(1.0, mean)),
        mastery_changes=[],
    )


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

        # Atomic complete: only one concurrent request actually flips
        # the state. The conditional UPDATE makes the read-modify-write
        # race-free without holding a row lock.
        if row.state != "complete":
            now = datetime.now(UTC)
            await db.execute(
                update(SessionRow)
                .where(SessionRow.id == session_id, SessionRow.state != "complete")
                .values(state="complete", completed_at=now)
            )
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


class SessionSummary(BaseModel):
    id: UUID
    domain: str
    started_at: datetime
    completed_at: datetime | None
    state: str
    attempts_count: int
    mean_score: float | None


@router.get("/learners/{learner_id}/sessions", response_model=list[SessionSummary])
async def list_learner_sessions(
    learner_id: UUID, limit: int = 5
) -> list[SessionSummary]:
    """List recent sessions for a learner with aggregate attempt info.

    Two queries total (was N+1): one for the sessions, one to pull
    every attempt for those sessions, then aggregate in Python.
    Computing the mean in SQL is doable but `overall_score` lives
    inside `attempts.semantic_result` JSONB — pulling rows once and
    folding in Python is more legible and still O(n).
    """
    sm = sessionmaker_factory()
    async with sm() as db:
        sessions = list(
            (
                await db.execute(
                    select(SessionRow)
                    .where(SessionRow.learner_id == learner_id)
                    .order_by(SessionRow.started_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        if not sessions:
            return []

        session_ids = [s.id for s in sessions]
        attempts = list(
            (
                await db.execute(
                    select(AttemptRow).where(AttemptRow.session_id.in_(session_ids))
                )
            )
            .scalars()
            .all()
        )

        # Index attempts by session_id for O(1) lookup during the fold.
        by_session: dict[UUID, list[AttemptRow]] = {sid: [] for sid in session_ids}
        for a in attempts:
            by_session.setdefault(a.session_id, []).append(a)

        out: list[SessionSummary] = []
        for s in sessions:
            atts = by_session.get(s.id, [])
            # `bool` is a subclass of `int` — exclude it explicitly so a
            # legacy `{"overall_score": True}` (which would be 1.0) can't
            # masquerade as a real score.
            scores = [
                (a.semantic_result or {}).get("overall_score")
                for a in atts
                if a.semantic_result is not None
            ]
            scores = [
                x for x in scores if isinstance(x, (int, float)) and not isinstance(x, bool)
            ]
            mean = sum(scores) / len(scores) if scores else None
            out.append(
                SessionSummary(
                    id=s.id,
                    domain=s.domain,
                    started_at=s.started_at,
                    completed_at=s.completed_at,
                    state=s.state,
                    attempts_count=len(atts),
                    mean_score=mean,
                )
            )
    return out


class WSTokenResponse(BaseModel):
    token: str
    expires_in_s: int


@router.get("/sessions/{session_id}/ws_token", response_model=WSTokenResponse)
async def get_ws_token(session_id: UUID) -> WSTokenResponse:
    """Mint a short-lived WS-auth token for the given session.

    The frontend hits this just before opening the WebSocket and
    appends `?token=<...>` to the URL. The token is bound to the
    session_id and expires after 5 minutes; new connections need a
    fresh mint.

    The endpoint sits behind the same basicauth as the other REST
    surfaces (see infra/Caddyfile). Anyone with the basicauth creds
    can mint tokens for any session — that matches the current threat
    model where basicauth gates *everything*.
    """
    sm = sessionmaker_factory()
    async with sm() as db:
        exists = (
            await db.execute(select(SessionRow.id).where(SessionRow.id == session_id))
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail="session not found")
    token, ttl = mint_token(session_id)
    return WSTokenResponse(token=token, expires_in_s=ttl)


@router.get("/learners/{learner_id}/mastery", response_model=GetLearnerMasteryResponse)
async def get_learner_mastery(learner_id: UUID) -> GetLearnerMasteryResponse:
    from app.api._overview import load_mastery_scores

    sm = sessionmaker_factory()
    async with sm() as db:
        scores = await load_mastery_scores(db, learner_id)
    return GetLearnerMasteryResponse(learner_id=learner_id, scores=scores)


class OverviewResponse(BaseModel):
    learner_id: UUID
    streak_days: int
    total_seconds_interpreted: int
    mastery_scores: list[MasteryScore]


@router.get("/learners/{learner_id}/overview", response_model=OverviewResponse)
async def get_learner_overview(learner_id: UUID) -> OverviewResponse:
    from app.api._overview import (
        compute_streak,
        load_mastery_scores,
        sum_interpreted_seconds,
    )

    sm = sessionmaker_factory()
    async with sm() as db:
        streak = await compute_streak(db, learner_id)
        seconds = await sum_interpreted_seconds(db, learner_id)
        scores = await load_mastery_scores(db, learner_id)
    return OverviewResponse(
        learner_id=learner_id,
        streak_days=streak,
        total_seconds_interpreted=seconds,
        mastery_scores=scores,
    )
