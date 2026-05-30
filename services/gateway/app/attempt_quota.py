"""Per-learner per-day attempt quota, backed by Redis.

Key: `attempt_quota:<learner_id>:<YYYY-MM-DD UTC>`. Atomic INCR with 24h TTL.
Default cap is 100; override via `ATTEMPT_QUOTA_DAILY` env. Enforced at the
gateway's `audio.submit` boundary BEFORE MinIO upload / DB write / analysis
enqueue, so an exhausted learner does not waste storage or spend.

Mirrors the shape of `quota.py` (generation quota) but tracks a different
counter — generation gates session creation; this gates recording attempts.

Implementation notes:
- Earlier versions INCR'd unconditionally then raised on overflow; the
  failed increment persisted in Redis, so `remaining_attempts` reported
  an ever-growing deficit. We now DECR back on overflow.
- The Redis client is module-level cached. Re-opening a connection per
  call was costing ~milliseconds on the hot path.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis


DEFAULT_DAILY_CAP = 100

# Per-learner overrides. Dev learner gets a high cap so demos / smoke tests
# can churn many attempts without bumping into the wall. Override via
# `ATTEMPT_QUOTA_DEV_LEARNER` env if the dev UUID should change.
def _dev_learner_id() -> UUID | None:
    raw = os.getenv(
        "ATTEMPT_QUOTA_DEV_LEARNER", "00000000-0000-0000-0000-000000000001"
    )
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _per_learner_caps() -> dict[UUID, int]:
    dev = _dev_learner_id()
    if dev is None:
        return {}
    return {dev: 1000}


class AttemptQuotaExceeded(Exception):
    """Raised when the learner's daily attempt cap would be exceeded."""


_client: Redis | None = None
_client_lock = asyncio.Lock()


async def _redis() -> Redis:
    """Return a module-level Redis client, creating one on first call.

    Each Redis() instance carries its own connection pool, so caching
    one keeps the pool warm across requests. The asyncio.Lock guards
    initialisation; the pool itself is concurrency-safe.
    """
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is None:
            _client = Redis.from_url(
                os.getenv("REDIS_URL", "redis://localhost:6379/0"),
                decode_responses=True,
            )
    return _client


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

    Raises `AttemptQuotaExceeded` if the post-increment count would
    exceed the cap, and DECRs the counter back so the user isn't
    perma-penalised for tripping the rate-limit.

    Returns the new count on success.
    """
    cap = _per_learner_caps().get(learner_id, daily_cap())
    r = await _redis()
    key = _quota_key(learner_id)
    new_count = await r.incr(key)
    if new_count == 1:
        await r.expire(key, 60 * 60 * 25)
    if new_count > cap:
        # Roll the counter back so a stream of rejected calls doesn't
        # leave the learner falsely "over-quota" for the rest of the
        # UTC day.
        await r.decr(key)
        raise AttemptQuotaExceeded(
            f"learner {learner_id} has used {cap}/{cap} attempts today"
        )
    return new_count


async def remaining_attempts(learner_id: UUID) -> int:
    """Return the remaining-attempt count for `learner_id` today.

    Read-only; does not increment. Useful for surfacing the budget in the UI.
    """
    cap = _per_learner_caps().get(learner_id, daily_cap())
    r = await _redis()
    used_raw = await r.get(_quota_key(learner_id))
    used = int(used_raw) if used_raw is not None else 0
    return max(0, cap - used)
