"""Tests for the tier-based mastery progression."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.engine.mastery_tier import (
    MAX_TIER,
    PROMOTION_THRESHOLD,
    PROMOTION_WINDOW,
    ROLLING_WINDOW_CAP,
    TIER_BANDS,
    TIER_NAMES,
    append_score,
    evaluate_promotion,
    next_tier_band,
    progress_to_next,
    tier_for_level,
)


def _entries(level_score_pairs: list[tuple[int, float]]) -> list[dict]:
    """Build a recent_scores list with timestamps spaced one minute apart."""
    base = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)
    out = []
    for i, (lvl, sc) in enumerate(level_score_pairs):
        out.append({"level": lvl, "score": sc, "ts": (base + timedelta(minutes=i)).isoformat()})
    return out


def test_tier_for_level_bands():
    assert tier_for_level(1) == 1
    assert tier_for_level(2) == 1
    assert tier_for_level(3) == 2
    assert tier_for_level(4) == 2
    assert tier_for_level(5) == 3
    assert tier_for_level(8) == 4
    assert tier_for_level(9) == 5
    assert tier_for_level(10) == 5


def test_next_tier_band_for_initiate():
    assert next_tier_band(0) == TIER_BANDS[1]  # Apprentice band


def test_next_tier_band_for_journeyman():
    assert next_tier_band(2) == TIER_BANDS[3]  # Practitioner band


def test_promotion_holds_when_below_window():
    # Only 3 attempts at-band — not enough yet
    recent = _entries([(1, 0.9), (2, 0.9), (1, 0.9)])
    assert evaluate_promotion(0, recent) == 0


def test_promotion_holds_when_mean_below_threshold():
    # 5 in-band but mean < 0.80
    recent = _entries([(1, 0.7), (2, 0.7), (1, 0.8), (2, 0.7), (1, 0.7)])
    assert evaluate_promotion(0, recent) == 0


def test_promotion_fires_at_threshold():
    recent = _entries([(1, 0.85), (2, 0.85), (1, 0.85), (2, 0.85), (1, 0.85)])
    assert evaluate_promotion(0, recent) == 1


def test_promotion_only_counts_at_band_attempts():
    # 5 attempts but they're at L5-6 (Practitioner band) — not Apprentice band
    recent = _entries([(5, 0.95)] * 5)
    assert evaluate_promotion(0, recent) == 0


def test_promotion_cascades_two_tiers_at_once():
    # 5 at L3-4 with high scores qualifies Initiate -> Apprentice -> Journeyman?
    # No — Apprentice promotion needs L1-2 attempts. So from Initiate this only
    # promotes IF there are also 5 at L1-2 qualifying. Verify cascade behaviour
    # with a richer history.
    recent = _entries(
        [(1, 0.9), (2, 0.9), (1, 0.9), (2, 0.9), (1, 0.9)]  # Apprentice qualified
        + [(3, 0.9), (4, 0.9), (3, 0.9), (4, 0.9), (3, 0.9)]  # Journeyman qualified
    )
    assert evaluate_promotion(0, recent) == 2  # Initiate -> Journeyman in one step


def test_promotion_caps_at_master():
    # 5 high scores at L9-10 from Expert tier promotes to Master, doesn't go further.
    recent = _entries([(9, 0.95), (10, 0.95), (9, 0.95), (10, 0.95), (9, 0.95)])
    assert evaluate_promotion(4, recent) == MAX_TIER
    # Already at Master — stays at Master regardless.
    assert evaluate_promotion(MAX_TIER, recent) == MAX_TIER


def test_promotion_uses_only_last_window():
    # Older bad scores at-band shouldn't drag down the recent window.
    recent = _entries(
        [(1, 0.3), (2, 0.3), (1, 0.3)]  # old low scores
        + [(1, 0.9), (2, 0.9), (1, 0.9), (2, 0.9), (1, 0.9)]  # last 5 great
    )
    assert evaluate_promotion(0, recent) == 1


def test_no_demotion_with_recent_bad_scores():
    # Already at Practitioner with recent bad scores — must NOT demote
    # (high-water-mark policy).
    recent = _entries([(3, 0.2), (4, 0.2), (3, 0.2), (4, 0.2), (3, 0.2)])
    assert evaluate_promotion(3, recent) == 3


def test_append_score_caps_rolling_window():
    recent: list[dict] = []
    for i in range(ROLLING_WINDOW_CAP + 5):
        recent = append_score(recent, level=1, score=0.5, ts=datetime(2026, 5, 28, tzinfo=UTC))
    assert len(recent) == ROLLING_WINDOW_CAP


def test_append_score_appends_in_order():
    base = datetime(2026, 5, 28, tzinfo=UTC)
    recent = append_score(None, level=1, score=0.5, ts=base)
    recent = append_score(recent, level=2, score=0.6, ts=base + timedelta(minutes=1))
    assert len(recent) == 2
    assert recent[0]["level"] == 1
    assert recent[1]["level"] == 2


def test_progress_zero_for_no_at_band_attempts():
    p = progress_to_next(0, [])
    assert p.progress == 0.0
    assert p.tier_name == "Initiate"
    assert p.next_tier_name == "Apprentice"


def test_progress_partial_when_under_window():
    # 2 of 5 needed, scores at threshold
    recent = _entries([(1, 0.85), (2, 0.85)])
    p = progress_to_next(0, recent)
    assert 0 < p.progress < 1
    # sample_progress = 2/5 = 0.4; score_progress = 0.85/0.80 = 1.0; min = 0.4
    assert p.progress == 0.4


def test_progress_full_at_promotion_moment():
    recent = _entries([(1, 0.85), (2, 0.85), (1, 0.85), (2, 0.85), (1, 0.85)])
    p = progress_to_next(0, recent)
    assert p.progress == 1.0


def test_progress_at_master_is_full():
    p = progress_to_next(MAX_TIER, _entries([(10, 0.9)]))
    assert p.progress == 1.0
    assert p.next_tier_name is None


def test_constants_sanity():
    assert PROMOTION_WINDOW == 5
    assert PROMOTION_THRESHOLD == 0.80
    assert TIER_NAMES[0] == "Initiate"
    assert TIER_NAMES[MAX_TIER] == "Master"
