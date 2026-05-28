"""Tests for the per-learner daily attempt quota."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

from app import attempt_quota


@pytest.fixture
def fake_redis():
    """Yield a mock Redis client wired into attempt_quota._redis."""
    fake = AsyncMock()
    fake.close = AsyncMock()
    with patch.object(attempt_quota, "_redis", return_value=fake):
        yield fake


@pytest.mark.asyncio
async def test_consume_under_cap_returns_count(fake_redis, monkeypatch):
    monkeypatch.setenv("ATTEMPT_QUOTA_DAILY", "5")
    fake_redis.incr.return_value = 3
    learner = uuid4()

    new_count = await attempt_quota.consume_attempt_quota(learner)

    assert new_count == 3
    fake_redis.incr.assert_awaited_once()
    fake_redis.expire.assert_not_awaited()


@pytest.mark.asyncio
async def test_consume_first_hit_sets_ttl(fake_redis, monkeypatch):
    monkeypatch.setenv("ATTEMPT_QUOTA_DAILY", "5")
    fake_redis.incr.return_value = 1

    await attempt_quota.consume_attempt_quota(uuid4())

    fake_redis.expire.assert_awaited_once()
    # second positional arg is the TTL in seconds; should be >= 24h
    args, _ = fake_redis.expire.call_args
    assert args[1] >= 24 * 60 * 60


@pytest.mark.asyncio
async def test_consume_over_cap_raises(fake_redis, monkeypatch):
    monkeypatch.setenv("ATTEMPT_QUOTA_DAILY", "5")
    fake_redis.incr.return_value = 6

    with pytest.raises(attempt_quota.AttemptQuotaExceeded):
        await attempt_quota.consume_attempt_quota(uuid4())


@pytest.mark.asyncio
async def test_dev_learner_has_elevated_cap(fake_redis, monkeypatch):
    monkeypatch.setenv("ATTEMPT_QUOTA_DAILY", "5")
    # Bump to 200 — within dev learner's 1000 cap but well over the 5 default.
    fake_redis.incr.return_value = 200
    dev_learner = UUID("00000000-0000-0000-0000-000000000001")

    new_count = await attempt_quota.consume_attempt_quota(dev_learner)

    assert new_count == 200


@pytest.mark.asyncio
async def test_remaining_attempts(fake_redis, monkeypatch):
    monkeypatch.setenv("ATTEMPT_QUOTA_DAILY", "10")
    fake_redis.get.return_value = "3"

    remaining = await attempt_quota.remaining_attempts(uuid4())

    assert remaining == 7


@pytest.mark.asyncio
async def test_remaining_attempts_floors_at_zero(fake_redis, monkeypatch):
    monkeypatch.setenv("ATTEMPT_QUOTA_DAILY", "5")
    fake_redis.get.return_value = "999"  # somehow over-incremented

    remaining = await attempt_quota.remaining_attempts(uuid4())

    assert remaining == 0


def test_daily_cap_default():
    assert attempt_quota.daily_cap() >= 1


def test_daily_cap_env_override(monkeypatch):
    monkeypatch.setenv("ATTEMPT_QUOTA_DAILY", "42")
    assert attempt_quota.daily_cap() == 42


def test_daily_cap_bad_env_falls_back(monkeypatch):
    monkeypatch.setenv("ATTEMPT_QUOTA_DAILY", "not-a-number")
    assert attempt_quota.daily_cap() == attempt_quota.DEFAULT_DAILY_CAP
