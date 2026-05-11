"""Seed the dev database with a test learner and a handful of segments.

Run via:

    docker compose run --rm gateway python -m scripts.seed

Idempotent: re-running it will not duplicate rows (uses fixed UUIDs).
Uploads a tiny placeholder blob to MinIO for each segment so `segment.play`
can mint a signed URL. Real audio assets can overwrite the same keys later.
"""

from __future__ import annotations

import asyncio
from uuid import UUID

from sqlalchemy import select

from app.db import sessionmaker_factory
from app.models.tables import LearnerRow, SegmentRow
from app.storage import _bucket, _client, ensure_bucket

# Fixed UUIDs so re-runs are idempotent and the operator dashboard can paste
# the learner_id verbatim.
LEARNER_ID = UUID("00000000-0000-0000-0000-000000000001")

SEGMENTS: list[dict] = [
    {
        "id": UUID("11111111-1111-1111-1111-000000000001"),
        "source_text": "We need to coordinate the delivery schedule with the supply battalion.",
        "source_lang": "en",
        "target_lang": "ko",
        "register": "formal-military",
        "domain": "logistics",
        "difficulty_level": 3,
    },
    {
        "id": UUID("11111111-1111-1111-1111-000000000002"),
        "source_text": "보급 대대와 배송 일정을 조율해야 합니다.",
        "source_lang": "ko",
        "target_lang": "en",
        "register": "formal-military",
        "domain": "logistics",
        "difficulty_level": 4,
    },
    {
        "id": UUID("11111111-1111-1111-1111-000000000003"),
        "source_text": "The convoy will depart at zero-six-hundred, weather permitting.",
        "source_lang": "en",
        "target_lang": "ko",
        "register": "formal-military",
        "domain": "logistics",
        "difficulty_level": 5,
    },
    {
        "id": UUID("11111111-1111-1111-1111-000000000004"),
        "source_text": "차량 행렬은 날씨가 허락한다면 0600시에 출발할 예정입니다.",
        "source_lang": "ko",
        "target_lang": "en",
        "register": "formal-military",
        "domain": "logistics",
        "difficulty_level": 6,
    },
    {
        "id": UUID("11111111-1111-1111-1111-000000000005"),
        "source_text": "Diplomatic relations between the two states have entered a new phase.",
        "source_lang": "en",
        "target_lang": "ko",
        "register": "formal-diplomatic",
        "domain": "diplomacy",
        "difficulty_level": 5,
    },
]


def _placeholder_blob() -> bytes:
    """Tiny WebM-ish placeholder. Enough that MinIO stores it and presigned
    URLs work; not a real playable file. Overwrite with real audio later."""
    ebml = bytes.fromhex("1a45dfa39f4286810142f7810142f2810442f3810842")
    return ebml + b"\x00" * 256


def segment_audio_key(segment_id: UUID) -> str:
    return f"segments/{segment_id}.webm"


def upload_placeholders() -> None:
    ensure_bucket()
    client = _client()
    bucket = _bucket()
    blob = _placeholder_blob()
    for seg in SEGMENTS:
        key = segment_audio_key(seg["id"])
        client.put_object(Bucket=bucket, Key=key, Body=blob, ContentType="audio/webm")
        print(f"  uploaded {key} ({len(blob)} bytes)")


async def upsert_rows() -> None:
    sm = sessionmaker_factory()
    async with sm() as db:
        existing = await db.execute(
            select(LearnerRow).where(LearnerRow.id == LEARNER_ID)
        )
        if existing.scalar_one_or_none() is None:
            db.add(
                LearnerRow(
                    id=LEARNER_ID,
                    display_name="Dev Learner",
                    primary_lang="ko",
                )
            )
            print(f"  inserted learner {LEARNER_ID}")
        else:
            print(f"  learner {LEARNER_ID} already exists")

        for seg in SEGMENTS:
            existing = await db.execute(
                select(SegmentRow).where(SegmentRow.id == seg["id"])
            )
            if existing.scalar_one_or_none() is None:
                db.add(
                    SegmentRow(
                        id=seg["id"],
                        source_text=seg["source_text"],
                        source_lang=seg["source_lang"],
                        target_lang=seg["target_lang"],
                        register=seg["register"],
                        domain=seg["domain"],
                        difficulty_level=seg["difficulty_level"],
                        audio_path=segment_audio_key(seg["id"]),
                    )
                )
                print(
                    f"  inserted segment {seg['id']} "
                    f"({seg['domain']}/L{seg['difficulty_level']})"
                )
            else:
                print(f"  segment {seg['id']} already exists")

        await db.commit()


async def main() -> None:
    print("Uploading placeholder audio to MinIO...")
    upload_placeholders()
    print("Upserting DB rows...")
    await upsert_rows()
    print()
    print("Done.")
    print(f"  learner_id: {LEARNER_ID}")
    print("  domains: logistics, diplomacy")
    print("  difficulty levels: 3, 4, 5, 6")


if __name__ == "__main__":
    asyncio.run(main())
