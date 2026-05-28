"""Tests for the daily spend ceiling counter."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app import spend


@pytest.fixture
def fake_redis():
    fake = MagicMock()
    fake.close = MagicMock()
    with patch.object(spend, "_redis", return_value=fake):
        yield fake


def test_record_known_kind_increments(fake_redis, monkeypatch):
    monkeypatch.setenv("MAX_DAILY_USD", "5")
    fake_redis.incrby.return_value = 1000  # 1 cent in millicents

    total = spend.record_spend("claude_eval")

    assert total == 1000
    fake_redis.incrby.assert_called_once()
    args, _ = fake_redis.incrby.call_args
    assert args[1] == spend._DEFAULTS_MILLICENTS["claude_eval"]


def test_record_first_hit_sets_ttl(fake_redis):
    # incrby returns delta (i.e. counter equals delta) on first hit
    fake_redis.incrby.return_value = spend._DEFAULTS_MILLICENTS["claude_eval"]

    spend.record_spend("claude_eval")

    fake_redis.expire.assert_called_once()
    args, _ = fake_redis.expire.call_args
    assert args[1] >= 24 * 60 * 60


def test_record_unknown_kind_zero_delta(fake_redis):
    fake_redis.get.return_value = "0"

    total = spend.record_spend("not_a_real_kind")

    assert total == 0
    fake_redis.incrby.assert_not_called()


def test_record_env_override(fake_redis, monkeypatch):
    monkeypatch.setenv("EST_COST_CLAUDE_EVAL", "9999")
    fake_redis.incrby.return_value = 9999

    spend.record_spend("claude_eval")

    args, _ = fake_redis.incrby.call_args
    assert args[1] == 9999


def test_is_over_ceiling_false_when_under(fake_redis, monkeypatch):
    monkeypatch.setenv("MAX_DAILY_USD", "5")
    fake_redis.get.return_value = "100000"  # $1 of spend in millicents

    assert spend.is_over_ceiling() is False


def test_is_over_ceiling_true_when_at_or_over(fake_redis, monkeypatch):
    monkeypatch.setenv("MAX_DAILY_USD", "1")
    # 1 USD = 100 cents = 100_000 millicents
    fake_redis.get.return_value = "100000"

    assert spend.is_over_ceiling() is True


def test_is_over_ceiling_false_when_ceiling_disabled(fake_redis, monkeypatch):
    monkeypatch.setenv("MAX_DAILY_USD", "0")
    fake_redis.get.return_value = "999999999"

    assert spend.is_over_ceiling() is False


def test_report_shape(fake_redis, monkeypatch):
    monkeypatch.setenv("MAX_DAILY_USD", "5")
    fake_redis.get.return_value = "250000"  # $2.50 in millicents

    snap = spend.report()

    assert snap["spent_usd"] == pytest.approx(2.5)
    assert snap["ceiling_usd"] == 5.0
    assert snap["over_ceiling"] is False
    assert "date_utc" in snap
