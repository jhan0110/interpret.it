from __future__ import annotations

import random
from uuid import uuid4

from app.engine.difficulty_ladder import (
    CandidateSegment,
    LearnerHistoryItem,
    can_promote_above_8,
    combined_score,
    difficulty_delta,
    select_next_segment,
    target_level,
    update_mastery,
)


def test_combined_score_blends_70_30() -> None:
    # semantic 1.0, prosody low (1.0) → 1.0
    assert combined_score(1.0, "low") == 1.0
    # semantic 0.0, prosody overloaded (0.10) → 0.03
    assert abs(combined_score(0.0, "overloaded") - 0.03) < 1e-9


def test_combined_score_missing_components_neutral() -> None:
    # only semantic — prosody defaults to 0.5
    s = combined_score(1.0, None)
    assert abs(s - (0.7 * 1.0 + 0.3 * 0.5)) < 1e-9


def test_update_mastery_decaying_alpha() -> None:
    # First attempt: α = 1/(1+0) = 1.0 capped at 1.0, so new ≈ score
    assert update_mastery(0.5, 0, 1.0) == 1.0
    # After 100 attempts, α floors at 0.15
    new = update_mastery(0.5, 100, 1.0)
    assert abs(new - (0.5 + 0.15 * 0.5)) < 1e-9


def test_update_mastery_clamps_unit_interval() -> None:
    assert update_mastery(0.99, 100, 1.0) <= 1.0
    assert update_mastery(0.01, 100, 0.0) >= 0.0


def test_difficulty_delta_promotion() -> None:
    assert difficulty_delta(0.7, 0.85) == +1


def test_difficulty_delta_demotion() -> None:
    assert difficulty_delta(0.6, 0.4) == -1


def test_difficulty_delta_holds() -> None:
    assert difficulty_delta(0.5, 0.6) == 0  # rising but below 0.80
    assert difficulty_delta(0.6, 0.55) == 0  # falling but ≥ 0.50


def test_target_level_clamps() -> None:
    assert target_level(10, +1) == 10
    assert target_level(1, -1) == 1
    assert target_level(5, +1) == 6


def test_select_next_segment_excludes_recent() -> None:
    sid_a = uuid4()
    sid_b = uuid4()
    candidates = [
        CandidateSegment(sid_a, 5, "logistics", "informal", "ko", "en", None),
        CandidateSegment(sid_b, 5, "logistics", "informal", "ko", "en", None),
    ]
    rng = random.Random(0)
    chosen = select_next_segment(candidates, recent_segment_ids={sid_a}, recent_embeddings=[], history={}, rng=rng)
    assert chosen is not None
    assert chosen.id == sid_b


def test_select_next_segment_drops_similar_embeddings() -> None:
    sid_a = uuid4()
    sid_b = uuid4()
    candidates = [
        CandidateSegment(sid_a, 5, "d", "informal", "ko", "en", [1.0, 0.0]),
        CandidateSegment(sid_b, 5, "d", "informal", "ko", "en", [0.0, 1.0]),
    ]
    rng = random.Random(0)
    # recent vector identical to sid_a's embedding
    chosen = select_next_segment(
        candidates,
        recent_segment_ids=set(),
        recent_embeddings=[[1.0, 0.0]],
        history={},
        rng=rng,
    )
    assert chosen is not None
    assert chosen.id == sid_b


def test_select_next_segment_empty_pool() -> None:
    sid_a = uuid4()
    candidates = [CandidateSegment(sid_a, 5, "d", "informal", "ko", "en", None)]
    rng = random.Random(0)
    assert (
        select_next_segment(candidates, recent_segment_ids={sid_a}, recent_embeddings=[], history={}, rng=rng)
        is None
    )


def test_select_biases_toward_weaker_segments() -> None:
    sid_strong = uuid4()
    sid_weak = uuid4()
    candidates = [
        CandidateSegment(sid_strong, 5, "d", "informal", "ko", "en", None),
        CandidateSegment(sid_weak, 5, "d", "informal", "ko", "en", None),
    ]
    history = {
        sid_strong: LearnerHistoryItem(sid_strong, 0.95, None),
        sid_weak: LearnerHistoryItem(sid_weak, 0.10, None),
    }
    counts = {sid_strong: 0, sid_weak: 0}
    rng = random.Random(42)
    for _ in range(500):
        chosen = select_next_segment(candidates, set(), [], history, rng=rng)
        assert chosen is not None
        counts[chosen.id] += 1
    assert counts[sid_weak] > counts[sid_strong] * 2


def test_promotion_above_8_requires_anti_fluke() -> None:
    assert not can_promote_above_8(2, 0.9)
    assert not can_promote_above_8(5, 0.7)
    assert can_promote_above_8(3, 0.75)
