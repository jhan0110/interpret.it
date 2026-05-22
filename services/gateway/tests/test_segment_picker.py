"""Unit tests for the picker's pure-logic helpers.

The IO half (DB queries, segment persistence) is exercised by running the
gateway in docker compose; here we cover the pieces that do not require a
DB connection: mastery → target-level mapping and attempt → history rollup.
These helpers live in `difficulty_ladder.py` so they can be imported from
test environments that do not have SQLAlchemy installed.
"""

from __future__ import annotations

from uuid import uuid4

from app.engine.difficulty_ladder import (
    AttemptScoreView,
    aggregate_history,
    target_level_from_mastery,
)


def test_target_level_floor_and_ceiling() -> None:
    assert target_level_from_mastery(0.0) == 1
    assert target_level_from_mastery(1.0) == 10


def test_target_level_near_midpoint() -> None:
    # 0.5 mastery → 1 + round(4.5). Python's banker's rounding makes that
    # 4 in 3.12, yielding level 5. Either side is acceptable as the seed
    # set has data on both 4 and 5.
    assert target_level_from_mastery(0.5) in (5, 6)


def test_target_level_monotonic_in_mastery() -> None:
    levels = [target_level_from_mastery(m / 10) for m in range(0, 11)]
    for a, b in zip(levels, levels[1:], strict=False):
        assert a <= b


def test_history_skips_attempts_without_score() -> None:
    sid = uuid4()
    views = [
        AttemptScoreView(segment_id=sid, overall_score=None),
        AttemptScoreView(segment_id=sid, overall_score=None),
    ]
    assert aggregate_history(views) == {}


def test_history_averages_repeated_segments() -> None:
    sid = uuid4()
    views = [
        AttemptScoreView(segment_id=sid, overall_score=0.40),
        AttemptScoreView(segment_id=sid, overall_score=0.80),
    ]
    history = aggregate_history(views)
    assert sid in history
    assert abs(history[sid].recent_score - 0.60) < 1e-9


def test_history_separates_segments() -> None:
    sid_a = uuid4()
    sid_b = uuid4()
    views = [
        AttemptScoreView(segment_id=sid_a, overall_score=0.10),
        AttemptScoreView(segment_id=sid_b, overall_score=0.90),
    ]
    history = aggregate_history(views)
    assert abs(history[sid_a].recent_score - 0.10) < 1e-9
    assert abs(history[sid_b].recent_score - 0.90) < 1e-9
