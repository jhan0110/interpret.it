"""Seed vocabulary for a learner's topic."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import LearnerTopicRow, LearnerVocabDeckRow, VocabEntryRow
from app.vocab.seeds import TOPIC_SEEDS, seed_uuid


async def seed_topic_for_learner(
    db: AsyncSession,
    learner_id: UUID,
    domain: str,
    source_lang: str = "en",
    target_lang: str = "ko",
) -> int:
    """Idempotently seed vocab_entries + learner_vocab_deck for a domain.

    Returns the count of new deck rows added (0 if domain already seeded).
    """
    seeds = TOPIC_SEEDS.get(domain, [])
    added = 0

    for item in seeds:
        entry_id = seed_uuid(domain, source_lang, item["term"])

        exists = (
            await db.execute(select(VocabEntryRow).where(VocabEntryRow.id == entry_id))
        ).scalar_one_or_none()

        if exists is None:
            db.add(
                VocabEntryRow(
                    id=entry_id,
                    term=item["term"],
                    definition=item["definition"],
                    domain=domain,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    register=item["register"],
                    origin="seed",
                )
            )

        deck_exists = (
            await db.execute(
                select(LearnerVocabDeckRow).where(
                    LearnerVocabDeckRow.learner_id == learner_id,
                    LearnerVocabDeckRow.vocab_entry_id == entry_id,
                )
            )
        ).scalar_one_or_none()

        if deck_exists is None:
            db.add(
                LearnerVocabDeckRow(
                    id=uuid4(),
                    learner_id=learner_id,
                    vocab_entry_id=entry_id,
                    added_by="topic_seed",
                    next_review_at=datetime.now(UTC),
                )
            )
            added += 1

    topic_exists = (
        await db.execute(
            select(LearnerTopicRow).where(
                LearnerTopicRow.learner_id == learner_id,
                LearnerTopicRow.domain == domain,
            )
        )
    ).scalar_one_or_none()

    if topic_exists is None:
        db.add(LearnerTopicRow(learner_id=learner_id, domain=domain))

    await db.commit()
    return added
