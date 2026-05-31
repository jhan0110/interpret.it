"""Seed vocabulary for a learner's topic.

Optimised to issue at most three queries per topic (was N+1 across ~30
seed items, ~360 round trips per signup). Race-safe under concurrent
calls thanks to `ON CONFLICT DO NOTHING` — a duplicate signup or a
double-clicked Add Topic button no longer raises IntegrityError.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import LearnerTopicRow, LearnerVocabDeckRow, VocabEntryRow
from app.vocab.seeds import seed_set_for_direction, seed_uuid


async def seed_topic_for_learner(
    db: AsyncSession,
    learner_id: UUID,
    domain: str,
    source_lang: str = "en",
    target_lang: str = "ko",
) -> int:
    """Idempotently seed vocab_entries + learner_vocab_deck for a domain.

    Returns the count of NEW deck rows added (0 if the domain was
    already seeded for this learner). When the requested direction has
    no seed set (e.g. ko→es today), only the learner_topic row is
    recorded — vocab will accumulate via extraction.
    """
    seed_dict, needs_swap = seed_set_for_direction(source_lang, target_lang)
    seeds = seed_dict.get(domain, [])
    if not seeds:
        # Even when the seed pool is empty, the learner_topic row should
        # be recorded so the home hub knows about the chosen domain.
        await _topic_upsert(db, learner_id, domain)
        await db.commit()
        return 0

    # If the canonical seed set is reversed relative to the requested
    # direction, swap term ↔ definition for each entry so `term` is in
    # the learner's source language. `seed_uuid` is computed on the
    # POST-SWAP `term` so the UUID is stable per direction.
    if needs_swap:
        seeds = [
            {
                "term": item["definition"],
                "definition": item["term"],
                "register": item["register"],
            }
            for item in seeds
        ]

    # Build (entry_id, item) pairs once.
    entries = [(seed_uuid(domain, source_lang, item["term"]), item) for item in seeds]
    entry_ids = [eid for eid, _ in entries]

    # ── single round-trip per relation to learn what's already there ──
    existing_entry_ids = set(
        (
            await db.execute(
                select(VocabEntryRow.id).where(VocabEntryRow.id.in_(entry_ids))
            )
        )
        .scalars()
        .all()
    )
    existing_deck_entry_ids = set(
        (
            await db.execute(
                select(LearnerVocabDeckRow.vocab_entry_id).where(
                    LearnerVocabDeckRow.learner_id == learner_id,
                    LearnerVocabDeckRow.vocab_entry_id.in_(entry_ids),
                )
            )
        )
        .scalars()
        .all()
    )

    # ── inserts via ON CONFLICT for race-safety with concurrent calls ──
    entry_rows = [
        {
            "id": eid,
            "term": item["term"],
            "definition": item["definition"],
            "domain": domain,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "register": item["register"],
            "origin": "seed",
        }
        for eid, item in entries
        if eid not in existing_entry_ids
    ]
    if entry_rows:
        await db.execute(
            pg_insert(VocabEntryRow).values(entry_rows).on_conflict_do_nothing(
                index_elements=[VocabEntryRow.id]
            )
        )

    deck_rows = [
        {
            "id": uuid4(),
            "learner_id": learner_id,
            "vocab_entry_id": eid,
            "added_by": "topic_seed",
            "next_review_at": datetime.now(UTC),
        }
        for eid, _ in entries
        if eid not in existing_deck_entry_ids
    ]
    added = len(deck_rows)
    if deck_rows:
        await db.execute(
            pg_insert(LearnerVocabDeckRow).values(deck_rows).on_conflict_do_nothing(
                index_elements=[
                    LearnerVocabDeckRow.learner_id,
                    LearnerVocabDeckRow.vocab_entry_id,
                ]
            )
        )

    await _topic_upsert(db, learner_id, domain)
    await db.commit()
    return added


async def _topic_upsert(db: AsyncSession, learner_id: UUID, domain: str) -> None:
    """Insert the learner-topic row, ignoring duplicates."""
    stmt = (
        pg_insert(LearnerTopicRow)
        .values(learner_id=learner_id, domain=domain)
        .on_conflict_do_nothing(
            index_elements=[LearnerTopicRow.learner_id, LearnerTopicRow.domain]
        )
    )
    await db.execute(stmt)
