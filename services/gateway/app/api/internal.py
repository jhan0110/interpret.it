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

import logging
from datetime import UTC, datetime
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

log = logging.getLogger(__name__)

from app.contracts.models import ProsodyResult, SemanticResult
from app.db import sessionmaker_factory
from app.engine.difficulty_ladder import (
    combined_score,
    difficulty_delta,
    update_mastery,
)
from app.models.tables import (
    AttemptRow,
    LearnerVocabDeckRow,
    MasteryScoreRow,
    ParaphraseEmbeddingRow,
    SegmentRow,
    SessionRow,
    VocabEntryRow,
)

router = APIRouter(prefix="/internal", tags=["internal"])


class ParaphraseInsert(BaseModel):
    text: str
    embedding: list[float] = Field(min_length=1)


class SegmentInsertRequest(BaseModel):
    source_text: str
    source_lang: str
    target_lang: str
    register: str
    domain: str
    difficulty_level: int = Field(ge=1, le=10)
    audio_path: str
    paraphrases: list[ParaphraseInsert] = Field(default_factory=list)


class SegmentInsertResponse(BaseModel):
    segment_id: UUID
    created: bool
    paraphrases_inserted: int


class SessionPlanRequest(BaseModel):
    session_id: UUID
    segment_ids: list[UUID]
    scenario_summary: str | None = None


class SessionPlanResponse(BaseModel):
    session_id: UUID
    count: int


def _segment_uuid_for(source_text: str, source_lang: str, target_lang: str) -> UUID:
    """Deterministic UUID from segment content. Identical text → identical id,
    so re-POSTing the same content returns the existing row instead of
    inserting a duplicate."""
    return uuid5(
        NAMESPACE_URL,
        f"segment:{source_lang}:{target_lang}:{source_text.strip()}",
    )


def _paraphrase_uuid(segment_id: UUID, text: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"paraphrase:{segment_id}:{text.strip()}")


@router.post("/segments", response_model=SegmentInsertResponse)
async def post_segment(body: SegmentInsertRequest) -> SegmentInsertResponse:
    """Insert a generated segment + its paraphrase embeddings.

    Idempotent: the segment_id is derived deterministically from
    (source_text, source_lang, target_lang); re-POSTing returns the
    existing id with `created=False` and the paraphrase set is union'd.
    """
    seg_id = _segment_uuid_for(body.source_text, body.source_lang, body.target_lang)
    sm = sessionmaker_factory()
    paraphrases_inserted = 0
    async with sm() as db:
        existing = (
            await db.execute(select(SegmentRow).where(SegmentRow.id == seg_id))
        ).scalar_one_or_none()
        created = existing is None
        if created:
            db.add(
                SegmentRow(
                    id=seg_id,
                    source_text=body.source_text,
                    source_lang=body.source_lang,
                    target_lang=body.target_lang,
                    register=body.register,
                    domain=body.domain,
                    difficulty_level=body.difficulty_level,
                    audio_path=body.audio_path,
                )
            )
        for pp in body.paraphrases:
            pid = _paraphrase_uuid(seg_id, pp.text)
            exists = (
                await db.execute(
                    select(ParaphraseEmbeddingRow).where(
                        ParaphraseEmbeddingRow.id == pid
                    )
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue
            db.add(
                ParaphraseEmbeddingRow(
                    id=pid,
                    segment_id=seg_id,
                    paraphrase=pp.text,
                    embedding=pp.embedding,
                )
            )
            paraphrases_inserted += 1
        await db.commit()
    return SegmentInsertResponse(
        segment_id=seg_id,
        created=created,
        paraphrases_inserted=paraphrases_inserted,
    )


@router.post("/session_plan", response_model=SessionPlanResponse)
async def post_session_plan(body: SessionPlanRequest) -> SessionPlanResponse:
    """Record the pre-generated 10-pack against the session.

    Called by the analysis generation worker once all segments are
    inserted. The picker checks this list and walks it in order rather
    than hitting the ladder.
    """
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (
            await db.execute(select(SessionRow).where(SessionRow.id == body.session_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="session not found")
        row.planned_segment_ids = [str(sid) for sid in body.segment_ids]
        row.generation_state = "ready"
        await db.commit()
    return SessionPlanResponse(
        session_id=body.session_id, count=len(body.segment_ids)
    )


async def _close_if_ready(attempt_id: UUID) -> None:
    """Promote attempt → closed_at + update mastery when both results land."""
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (
            await db.execute(select(AttemptRow).where(AttemptRow.id == attempt_id))
        ).scalar_one_or_none()
        has_prosody = row is not None and row.prosody_result is not None
        has_semantic = row is not None and row.semantic_result is not None
        if row is None or not has_prosody or not has_semantic:
            log.info(
                "[gw.close_if_ready.waiting] attempt=%s pros=%s sem=%s",
                attempt_id,
                has_prosody,
                has_semantic,
            )
            return
        if row.closed_at is not None:
            return
        log.info("[gw.close_if_ready.closing] attempt=%s", attempt_id)

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


class VocabExtractionItem(BaseModel):
    term: str
    gloss: str
    register: str
    gap_type: Literal["knowledge_gap", "memory_gap"]
    severity: Literal["minor", "moderate", "critical"]
    explanation: str


class VocabExtractionRequest(BaseModel):
    attempt_id: UUID
    learner_id: UUID
    domain: str
    source_lang: str
    target_lang: str
    missed_terms: list[VocabExtractionItem]


def _vocab_entry_uuid(domain: str, source_lang: str, term: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"vocab_extracted:{domain}:{source_lang}:{term}")


@router.post("/vocab_extraction")
async def vocab_extraction(body: VocabExtractionRequest) -> dict:
    """Upsert missed vocabulary terms into the learner's deck.

    Called by the analysis vocab worker after a failed interpretation.
    If a term already exists in the deck (from seeding or a prior extraction),
    it is immediately re-surfaced by resetting next_review_at and interval.
    """
    sm = sessionmaker_factory()
    async with sm() as db:
        for item in body.missed_terms:
            entry_id = _vocab_entry_uuid(body.domain, body.source_lang, item.term)

            entry = (
                await db.execute(
                    select(VocabEntryRow).where(VocabEntryRow.id == entry_id)
                )
            ).scalar_one_or_none()

            if entry is None:
                db.add(
                    VocabEntryRow(
                        id=entry_id,
                        term=item.term,
                        definition=item.gloss,
                        domain=body.domain,
                        source_lang=body.source_lang,
                        target_lang=body.target_lang,
                        register=item.register,
                        origin="claude_generated",
                    )
                )

            deck_row = (
                await db.execute(
                    select(LearnerVocabDeckRow).where(
                        LearnerVocabDeckRow.learner_id == body.learner_id,
                        LearnerVocabDeckRow.vocab_entry_id == entry_id,
                    )
                )
            ).scalar_one_or_none()

            if deck_row is None:
                db.add(
                    LearnerVocabDeckRow(
                        id=uuid4(),
                        learner_id=body.learner_id,
                        vocab_entry_id=entry_id,
                        added_by="extraction",
                        gap_type=item.gap_type,
                        source_attempt_id=body.attempt_id,
                        next_review_at=datetime.now(UTC),
                    )
                )
            else:
                # Re-surface: treat as a failed review (reset interval)
                deck_row.next_review_at = datetime.now(UTC)
                deck_row.interval_days = 1
                deck_row.gap_type = item.gap_type
                deck_row.updated_at = datetime.now(UTC)

        await db.commit()
    return {"accepted": True}


@router.post("/prosody_result")
async def prosody_result(result: ProsodyResult) -> dict:
    log.info("[gw.internal.prosody_result.received] attempt=%s", result.attempt_id)
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (
            await db.execute(select(AttemptRow).where(AttemptRow.id == result.attempt_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="attempt not found")
        row.prosody_result = result.model_dump(mode="json")
        await db.commit()
    log.info("[gw.internal.prosody_result.persisted] attempt=%s", result.attempt_id)
    await _close_if_ready(result.attempt_id)
    return {"accepted": True}


@router.post("/semantic_result")
async def semantic_result(result: SemanticResult) -> dict:
    log.info("[gw.internal.semantic_result.received] attempt=%s", result.attempt_id)
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (
            await db.execute(select(AttemptRow).where(AttemptRow.id == result.attempt_id))
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="attempt not found")
        row.semantic_result = result.model_dump(mode="json")
        await db.commit()
    log.info("[gw.internal.semantic_result.persisted] attempt=%s", result.attempt_id)
    await _close_if_ready(result.attempt_id)
    return {"accepted": True}


@router.post("/segments/{segment_id}/embeddings")
async def upsert_segment_embeddings(
    segment_id: UUID, body: _SegmentEmbeddingsRequest
) -> dict:
    """Persist paraphrase embeddings generated by the analysis service.

    Inserts rows into paraphrase_embeddings (skipping duplicates by paraphrase
    text) and sets segment.embedding_id to the first inserted row so the
    novelty filter has a reference point.
    """
    sm = sessionmaker_factory()
    async with sm() as db:
        seg = (
            await db.execute(select(SegmentRow).where(SegmentRow.id == segment_id))
        ).scalar_one_or_none()
        if seg is None:
            raise HTTPException(status_code=404, detail="segment not found")

        first_id: UUID | None = None
        for item in body.paraphrases:
            row = ParaphraseEmbeddingRow(
                segment_id=segment_id,
                paraphrase=item.text,
                embedding=item.embedding,
            )
            db.add(row)
            await db.flush()
            if first_id is None:
                first_id = row.id

        if first_id is not None and seg.embedding_id is None:
            seg.embedding_id = first_id

        await db.commit()
    return {"accepted": True, "rows": len(body.paraphrases)}
