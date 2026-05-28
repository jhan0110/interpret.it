"""Global daily API-spend ceiling, backed by Redis.

A coarse but reliable kill-switch against runaway external-API spend.
Every paid call site (Claude via OpenRouter, OpenAI/ElevenLabs TTS)
records its *estimated* cost in tenths-of-a-cent units (millicents) on
a single per-UTC-day counter. Once the total crosses `MAX_DAILY_USD`,
subsequent callers see ``is_over_ceiling()`` return True and fall back
to mock mode for the rest of the day.

Key: ``spend:<YYYY-MM-DD UTC>``. Atomic INCRBY with 25h TTL.

Estimates are intentionally rough — they exist to prevent a 100x
runaway, not to bill anyone. Tune via the ``EST_COST_*`` env vars if a
provider's real cost shifts.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

import redis

log = logging.getLogger(__name__)


# Default per-call cost estimates in MILLICENTS (1 cent = 1000 millicents).
# Calibrated for current OpenRouter + Groq pricing as of 2026-05-28.
_DEFAULTS_MILLICENTS = {
    "claude_eval":           1000,   # ~$0.010 per evaluation (Sonnet, ~2k input + ~1k output)
    "claude_reference":      500,    # ~$0.005 per reference generation
    "claude_keypoints":      500,    # ~$0.005 per memorization key-point extraction
    "claude_generation":     2000,   # ~$0.020 per 10-phrase content generation
    "claude_vocab_extract":  500,    # ~$0.005 per vocab extraction
    "tts_openai_segment":    500,    # ~$0.005 per ~20s gpt-audio-mini clip
    "tts_openai_feedback":   200,    # ~$0.002 per ~3s feedback clip
    "tts_elevenlabs_segment": 1000,  # ~$0.010 per ~20s flash_v2_5 clip
    "tts_elevenlabs_feedback": 400,  # ~$0.004 per ~3s feedback clip
}

DEFAULT_MAX_DAILY_USD = 5.0


class SpendCeilingReached(Exception):
    """Raised by call sites that want to surface the ceiling as an error
    rather than silently falling back to mock. Most call sites prefer
    the silent-fallback pattern (see ``is_over_ceiling``)."""


def _redis() -> redis.Redis:
    return redis.Redis.from_url(
        os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        decode_responses=True,
    )


def _today_key() -> str:
    return f"spend:{datetime.now(UTC).strftime('%Y-%m-%d')}"


def _ceiling_millicents() -> int:
    try:
        usd = float(os.environ.get("MAX_DAILY_USD", str(DEFAULT_MAX_DAILY_USD)))
    except ValueError:
        usd = DEFAULT_MAX_DAILY_USD
    return int(usd * 100 * 1000)  # USD -> cents -> millicents


def _cost_millicents(call_kind: str) -> int:
    env_key = f"EST_COST_{call_kind.upper()}"
    override = os.environ.get(env_key)
    if override is not None:
        try:
            return int(override)
        except ValueError:
            pass
    return _DEFAULTS_MILLICENTS.get(call_kind, 0)


def record_spend(call_kind: str) -> int:
    """Record one call of ``call_kind`` and return the new running total
    in millicents. Atomic via Redis INCRBY; sets a 25h TTL on first hit
    of the day so the counter rolls over.
    """
    delta = _cost_millicents(call_kind)
    if delta <= 0:
        return _current_total()
    r = _redis()
    try:
        key = _today_key()
        new_total = r.incrby(key, delta)
        if new_total == delta:
            r.expire(key, 60 * 60 * 25)
        return int(new_total)
    finally:
        r.close()


def _current_total() -> int:
    r = _redis()
    try:
        raw = r.get(_today_key())
        return int(raw) if raw is not None else 0
    finally:
        r.close()


def is_over_ceiling() -> bool:
    """Return True if today's recorded spend meets or exceeds the ceiling.

    Call sites that produce expensive external traffic should check this
    before issuing the call and fall back to mock mode when True.
    """
    ceiling = _ceiling_millicents()
    if ceiling <= 0:
        return False
    return _current_total() >= ceiling


def report() -> dict:
    """Snapshot for logs / health endpoints. Read-only."""
    total = _current_total()
    ceiling = _ceiling_millicents()
    return {
        "spent_usd": round(total / 100_000, 4),
        "ceiling_usd": round(ceiling / 100_000, 2),
        "over_ceiling": ceiling > 0 and total >= ceiling,
        "date_utc": datetime.now(UTC).strftime("%Y-%m-%d"),
    }
