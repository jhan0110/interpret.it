"""Per-learner per-day attempt quota, backed by Redis.

Key: `attempt_quota:<learner_id>:<YYYY-MM-DD UTC>`. Atomic INCR with 24h TTL.
Default cap is 100; override via `ATTEMPT_QUOTA_DAILY` env. Enforced at the
gateway's `audio.submit` boundary BEFORE MinIO upload / DB write / analysis
enqueue, so an exhausted learner does not waste storage or spend.

Mirrors the shape of `quota.py` (generation quota) but tracks a different
counter — generation gates session creation; this gates recording attempts.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis


DEFAULT_DAILY_CAP = 100

# Per-learner overrides. Dev learner gets a high cap so demos / smoke tests
# can churn many attempts without bumping into the wall.
PER_LEARNER_CAPS: dict[UUID, int] = {
    UUID("00000000-0000-0000-0000-000000000001"): 1000,
}


class AttemptQuotaExceeded(Exception):
    """Raised when the learner's daily attempt cap would be exceeded."""


def _redis() -> Redis:
    return Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


def _today_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _quota_key(learner_id: UUID) -> str:
    return f"attempt_quota:{learner_id}:{_today_key()}"


def daily_cap() -> int:
    try:
        return int(os.getenv("ATTEMPT_QUOTA_DAILY", str(DEFAULT_DAILY_CAP)))
    except ValueError:
        return DEFAULT_DAILY_CAP


async def consume_attempt_quota(learner_id: UUID) -> int:
    """Increment the learner's daily attempt counter and enforce the cap.

    Raises `AttemptQuotaExceeded` if the post-increment count would exceed the
    cap. Returns the new count on success. There is no `force` bypass — unlike
    generation, attempts are a per-user volume control with no operator-side
    override.
    """
    cap = PER_LEARNER_CAPS.get(learner_id, daily_cap())
    r = _redis()
    try:
        key = _quota_key(learner_id)
        new_count = await r.incr(key)
        if new_count == 1:
            await r.expire(key, 60 * 60 * 25)
        if new_count > cap:
            raise AttemptQuotaExceeded(
                f"learner {learner_id} has used {new_count - 1}/{cap} attempts today"
            )
        return new_count
    finally:
        await r.close()


async def remaining_attempts(learner_id: UUID) -> int:
    """Return the remaining-attempt count for `learner_id` today.

    Read-only; does not increment. Useful for surfacing the budget in the UI.
    """
    cap = PER_LEARNER_CAPS.get(learner_id, daily_cap())
    r = _redis()
    try:
        used_raw = await r.get(_quota_key(learner_id))
        used = int(used_raw) if used_raw is not None else 0
        return max(0, cap - used)
    finally:
        await r.close()
