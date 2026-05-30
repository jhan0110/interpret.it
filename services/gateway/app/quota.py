"""Per-learner per-day generation-request quota, backed by Redis.

Key: `gen_quota:<learner_id>:<YYYY-MM-DD UTC>`. Atomic INCR with 24h TTL.
Default cap is 2; override via `GEN_QUOTA_DAILY` env. Operator-only
bypass via `?force=1` on the session-create endpoint (enforced upstream).

Like attempt_quota, this rolls the counter back on rejection so a
rate-limited learner doesn't end up over-counted for the rest of the
UTC day.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis


DEFAULT_DAILY_CAP = 2


def _dev_learner_id() -> UUID | None:
    raw = os.getenv(
        "GEN_QUOTA_DEV_LEARNER", "00000000-0000-0000-0000-000000000001"
    )
    if not raw:
        return None
    try:
        return UUID(raw)
    except ValueError:
        return None


def _per_learner_caps() -> dict[UUID, int]:
    dev = _dev_learner_id()
    return {dev: 100} if dev is not None else {}


class QuotaExceeded(Exception):
    pass


_client: Redis | None = None
_client_lock = asyncio.Lock()


async def _redis() -> Redis:
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
    return f"gen_quota:{learner_id}:{_today_key()}"


def daily_cap() -> int:
    try:
        return int(os.getenv("GEN_QUOTA_DAILY", str(DEFAULT_DAILY_CAP)))
    except ValueError:
        return DEFAULT_DAILY_CAP


async def consume_quota(learner_id: UUID, *, force: bool = False) -> int:
    """Increment the learner's daily generation counter.

    Raises `QuotaExceeded` if the post-increment count would exceed the
    cap and rolls the counter back. `force=True` bypasses the check but
    still increments (audit-trail honesty).
    """
    cap = _per_learner_caps().get(learner_id, daily_cap())
    r = await _redis()
    key = _quota_key(learner_id)
    new_count = await r.incr(key)
    if new_count == 1:
        await r.expire(key, 60 * 60 * 25)  # 25h gives slack across DST
    if not force and new_count > cap:
        await r.decr(key)
        raise QuotaExceeded(
            f"learner {learner_id} has used {cap}/{cap} generations today"
        )
    return new_count
