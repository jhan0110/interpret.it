"""End-to-end attempt flow at the pure-logic level.

Drives the state machine + difficulty ladder through three attempts
(weak → moderate → strong learner) without touching DB / Redis / MinIO.
This is the integration backbone that the live infra wires up; if this
breaks, the live system breaks.
"""

from __future__ import annotations

import random
from uuid import uuid4

from app.engine.difficulty_ladder import (
    CandidateSegment,
    LearnerHistoryItem,
    combined_score,
    difficulty_delta,
    select_next_segment,
    target_level,
    update_mastery,
)
from app.engine.state_machine import next_state


def _drive_attempt(
    starting_state: str = "idle",
) -> list[tuple[str, str]]:
    """Drive one attempt's worth of transitions; returns (trigger, to) pairs."""
    s = starting_state
    out: list[tuple[str, str]] = []
    sequence = [
        "segment.request",
        "playback.finished",
        "audio.submit",
        "analysis.partial",
        "analysis.complete",
    ]
    for trigger in sequence:
        r = next_state(s, trigger)  # type: ignore[arg-type]
        out.append((trigger, r.to_state))
        s = r.to_state
    return out


def test_one_attempt_runs_through_all_states() -> None:
    pairs = _drive_attempt()
    assert pairs == [
        ("segment.request", "listening"),
        ("playback.finished", "recording"),
        ("audio.submit", "analyzing"),
        ("analysis.partial", "analyzing"),
        ("analysis.complete", "feedback"),
    ]


def test_three_attempt_ladder_progression() -> None:
    """A learner who improves should climb the ladder.

    Starting mastery 0.5; semantic scores 0.6, 0.85, 0.95 with low load each.
    After ~2 strong attempts we expect a +1 delta.
    """
    mastery = 0.5
    attempts = 0
    deltas: list[int] = []
    scores_in = [0.60, 0.85, 0.95]

    for sem in scores_in:
        score = combined_score(sem, "low")
        old = mastery
        mastery = update_mastery(old, attempts, score)
        deltas.append(difficulty_delta(old, mastery))
        attempts += 1

    assert mastery > 0.85
    assert deltas[-1] == +1


def test_struggling_learner_drops_difficulty() -> None:
    mastery = 0.5
    attempts = 0
    deltas: list[int] = []
    for sem in [0.30, 0.20, 0.10]:
        score = combined_score(sem, "high")
        old = mastery
        mastery = update_mastery(old, attempts, score)
        deltas.append(difficulty_delta(old, mastery))
        attempts += 1

    assert mastery < 0.50
    assert deltas[-1] == -1


def test_segment_selection_after_ladder_step() -> None:
    """Verify the selector picks a level-6 segment when a learner moves 5→6."""
    rng = random.Random(0)
    current_level = 5
    new_level = target_level(current_level, +1)
    assert new_level == 6

    pool = [
        CandidateSegment(uuid4(), 6, "logistics", "informal", "ko", "en", None) for _ in range(5)
    ]
    history: dict = {}
    chosen = select_next_segment(
        candidates=pool,
        recent_segment_ids=set(),
        recent_embeddings=[],
        history=history,
        rng=rng,
    )
    assert chosen is not None
    assert chosen.difficulty_level == 6


def test_neutral_contribution_when_one_path_missing() -> None:
    """When only prosody arrives (semantic timed out), score blends with
    a 0.5 neutral semantic — matches §6.1 fallback rule."""
    score = combined_score(None, "low")
    # 0.7 * 0.5 (neutral) + 0.3 * 1.0 = 0.65
    assert abs(score - 0.65) < 1e-9


def test_ladder_anti_fluke_above_level_8() -> None:
    """Above level 8 promotion needs ≥3 attempts at level w/ mean ≥0.75."""
    from app.engine.difficulty_ladder import can_promote_above_8
    assert not can_promote_above_8(attempts_at_level=2, mean_score_at_level=0.9)
    assert can_promote_above_8(attempts_at_level=3, mean_score_at_level=0.80)
