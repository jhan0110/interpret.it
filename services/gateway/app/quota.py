"""Per-learner per-day generation-request quota, backed by Redis.

Key: `gen_quota:<learner_id>:<YYYY-MM-DD UTC>`. Atomic INCR with 24h TTL.
Default cap is 2; override via `GEN_QUOTA_DAILY` env. Operator-only
bypass via `?force=1` on the session-create endpoint (enforced upstream).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis


DEFAULT_DAILY_CAP = 2

# Per-learner overrides. Dev learner gets 100/day for testing.
PER_LEARNER_CAPS: dict[UUID, int] = {
    UUID("00000000-0000-0000-0000-000000000001"): 100,
}


class QuotaExceeded(Exception):
    pass


def _redis() -> Redis:
    return Redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


def _today_key() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _quota_key(learner_id: UUID) -> str:
    return f"gen_quota:{learner_id}:{_today_key()}"


def daily_cap() -> int:
    try:
        return int(os.getenv("GEN_QUOTA_DAILY", str(DEFAULT_DAILY_CAP)))
    except ValueError:
        return DEFAULT_DAILY_CAP


async def consume_quota(learner_id: UUID, *, force: bool = False) -> int:
    """Increment the learner's daily generation counter.

    Raises `QuotaExceeded` if the post-increment count would exceed the cap.
    Returns the new count on success. `force=True` bypasses the check but
    still increments (so the audit trail is honest).
    """
    cap = PER_LEARNER_CAPS.get(learner_id, daily_cap())
    r = _redis()
    try:
        key = _quota_key(learner_id)
        new_count = await r.incr(key)
        if new_count == 1:
            # First hit of the day — set TTL so the key auto-expires.
            await r.expire(key, 60 * 60 * 25)  # 25h gives slack across DST
        if not force and new_count > cap:
            raise QuotaExceeded(
                f"learner {learner_id} has used {new_count - 1}/{cap} generations today"
            )
        return new_count
    finally:
        await r.close()
