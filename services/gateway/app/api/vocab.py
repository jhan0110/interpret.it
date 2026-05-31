"""Vocabulary deck REST endpoints — learner-facing SRS management."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid5, NAMESPACE_URL, uuid4

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.sql import ColumnElement

from app.db import sessionmaker_factory
from app.models.tables import LearnerRow, LearnerTopicRow, LearnerVocabDeckRow, VocabEntryRow
from app.vocab.seeder import seed_topic_for_learner
from app.vocab.srs import sm2_update

router = APIRouter(prefix="/learners/{learner_id}/vocab", tags=["vocab"])

VALID_DOMAINS = {"logistics", "diplomacy", "intelligence", "operations", "medical", "cyber"}

# Alphabetically-normalised language pairs accepted by the `?pair=`
# filter. Kept in sync with frontend/components/LanguagePairSelector.tsx.
_VALID_PAIRS: dict[str, tuple[str, str]] = {
    "en-ko": ("en", "ko"),
    "en-es": ("en", "es"),
    "ko-es": ("ko", "es"),
}


def _pair_filter(pair: str | None) -> ColumnElement[bool] | None:
    """Translate `?pair=<en-ko|en-es|ko-es>` into a SQL predicate.

    Filter is unordered — both directions of the pair match (e.g.
    `en-es` matches `en→es` AND `es→en`). 400 on an unknown pair so
    operators see typos loudly. `None` returns None (no filtering).
    """
    if pair is None:
        return None
    pair = pair.lower()
    langs = _VALID_PAIRS.get(pair)
    if langs is None:
        raise HTTPException(
            status_code=400,
            detail=f"unknown pair {pair!r}; expected one of {list(_VALID_PAIRS)}",
        )
    a, b = langs
    return and_(
        VocabEntryRow.source_lang.in_(langs),
        VocabEntryRow.target_lang.in_(langs),
    )


class VocabCard(BaseModel):
    deck_id: UUID
    entry_id: UUID
    term: str
    definition: str
    domain: str
    source_lang: str
    target_lang: str
    register: str
    gap_type: str | None
    added_by: str
    next_review_at: datetime
    interval_days: int
    repetitions: int


class TopicItem(BaseModel):
    domain: str
    added_at: datetime


class AddTopicRequest(BaseModel):
    domain: str


class AddTopicResponse(BaseModel):
    domain: str
    added_count: int


class ReviewRequest(BaseModel):
    grade: int = Field(ge=0, le=5)


class VocabStats(BaseModel):
    total: int
    due_now: int
    knowledge_gaps: int
    memory_gaps: int
    by_domain: dict[str, int]


async def _require_learner(learner_id: UUID) -> None:
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (
            await db.execute(select(LearnerRow).where(LearnerRow.id == learner_id))
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="learner not found")


def _to_card(deck: LearnerVocabDeckRow, entry: VocabEntryRow) -> VocabCard:
    return VocabCard(
        deck_id=deck.id,
        entry_id=entry.id,
        term=entry.term,
        definition=entry.definition,
        domain=entry.domain,
        source_lang=entry.source_lang,
        target_lang=entry.target_lang,
        register=entry.register,
        gap_type=deck.gap_type,
        added_by=deck.added_by,
        next_review_at=deck.next_review_at,
        interval_days=deck.interval_days,
        repetitions=deck.repetitions,
    )


@router.post("/topics", response_model=AddTopicResponse)
async def add_topic(learner_id: UUID, body: AddTopicRequest) -> AddTopicResponse:
    if body.domain not in VALID_DOMAINS:
        raise HTTPException(status_code=422, detail=f"unknown domain: {body.domain}")
    await _require_learner(learner_id)
    sm = sessionmaker_factory()
    async with sm() as db:
        added = await seed_topic_for_learner(db, learner_id, body.domain)
    return AddTopicResponse(domain=body.domain, added_count=added)


@router.get("/topics", response_model=list[TopicItem])
async def list_topics(learner_id: UUID) -> list[TopicItem]:
    await _require_learner(learner_id)
    sm = sessionmaker_factory()
    async with sm() as db:
        rows = (
            await db.execute(
                select(LearnerTopicRow).where(LearnerTopicRow.learner_id == learner_id)
            )
        ).scalars().all()
    return [TopicItem(domain=r.domain, added_at=r.added_at) for r in rows]


@router.delete("/topics/{domain}", status_code=204)
async def remove_topic(learner_id: UUID, domain: str) -> None:
    await _require_learner(learner_id)
    sm = sessionmaker_factory()
    async with sm() as db:
        row = (
            await db.execute(
                select(LearnerTopicRow).where(
                    LearnerTopicRow.learner_id == learner_id,
                    LearnerTopicRow.domain == domain,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="topic not found")
        await db.delete(row)
        await db.commit()


@router.get("/due", response_model=list[VocabCard])
async def get_due_cards(
    learner_id: UUID,
    limit: int = 20,
    pair: str | None = Query(default=None, description="en-ko | en-es | ko-es"),
) -> list[VocabCard]:
    await _require_learner(learner_id)
    pair_clause = _pair_filter(pair)
    now = datetime.now(UTC)
    sm = sessionmaker_factory()
    async with sm() as db:
        stmt = (
            select(LearnerVocabDeckRow, VocabEntryRow)
            .join(VocabEntryRow, LearnerVocabDeckRow.vocab_entry_id == VocabEntryRow.id)
            .where(
                LearnerVocabDeckRow.learner_id == learner_id,
                LearnerVocabDeckRow.next_review_at <= now,
            )
            .order_by(LearnerVocabDeckRow.next_review_at.asc())
            .limit(limit)
        )
        if pair_clause is not None:
            stmt = stmt.where(pair_clause)
        rows = (await db.execute(stmt)).all()
    return [_to_card(deck, entry) for deck, entry in rows]


@router.post("/{deck_id}/review", response_model=VocabCard)
async def review_card(learner_id: UUID, deck_id: UUID, body: ReviewRequest) -> VocabCard:
    await _require_learner(learner_id)
    sm = sessionmaker_factory()
    async with sm() as db:
        deck = (
            await db.execute(
                select(LearnerVocabDeckRow).where(
                    LearnerVocabDeckRow.id == deck_id,
                    LearnerVocabDeckRow.learner_id == learner_id,
                )
            )
        ).scalar_one_or_none()
        if deck is None:
            raise HTTPException(status_code=404, detail="deck card not found")

        entry = (
            await db.execute(
                select(VocabEntryRow).where(VocabEntryRow.id == deck.vocab_entry_id)
            )
        ).scalar_one()

        new_interval, new_ef, new_reps = sm2_update(
            body.grade, deck.repetitions, deck.ease_factor, deck.interval_days
        )
        now = datetime.now(UTC)
        deck.interval_days = new_interval
        deck.ease_factor = new_ef
        deck.repetitions = new_reps
        deck.last_grade = body.grade
        deck.last_reviewed_at = now
        deck.next_review_at = now + timedelta(days=new_interval)
        deck.updated_at = now
        await db.commit()
        await db.refresh(deck)

    return _to_card(deck, entry)


@router.get("/stats", response_model=VocabStats)
async def get_stats(
    learner_id: UUID,
    pair: str | None = Query(default=None, description="en-ko | en-es | ko-es"),
) -> VocabStats:
    await _require_learner(learner_id)
    pair_clause = _pair_filter(pair)
    now = datetime.now(UTC)
    sm = sessionmaker_factory()
    async with sm() as db:
        stmt = (
            select(LearnerVocabDeckRow, VocabEntryRow)
            .join(VocabEntryRow, LearnerVocabDeckRow.vocab_entry_id == VocabEntryRow.id)
            .where(LearnerVocabDeckRow.learner_id == learner_id)
        )
        if pair_clause is not None:
            stmt = stmt.where(pair_clause)
        all_rows = (await db.execute(stmt)).all()

    total = len(all_rows)
    due_now = sum(1 for deck, _ in all_rows if deck.next_review_at <= now)
    knowledge_gaps = sum(1 for deck, _ in all_rows if deck.gap_type == "knowledge_gap")
    memory_gaps = sum(1 for deck, _ in all_rows if deck.gap_type == "memory_gap")

    by_domain: dict[str, int] = {}
    for _, entry in all_rows:
        by_domain[entry.domain] = by_domain.get(entry.domain, 0) + 1

    return VocabStats(
        total=total,
        due_now=due_now,
        knowledge_gaps=knowledge_gaps,
        memory_gaps=memory_gaps,
        by_domain=by_domain,
    )
