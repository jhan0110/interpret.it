"""Simplified SM-2 spaced-repetition algorithm."""

from __future__ import annotations


def sm2_update(
    grade: int,
    repetitions: int,
    ease_factor: float,
    interval_days: int,
) -> tuple[int, float, int]:
    """Return (new_interval_days, new_ease_factor, new_repetitions).

    grade 0-2: failure — reset to interval=1, repetitions=0
    grade 3-5: success — advance interval per SM-2 formula
    ease_factor is clamped at the 1.3 lower bound only; reference SM-2
    has no upper bound, and capping at 2.5 prevented the reward signal
    from accumulating on streaks of grade-5 reviews.
    """
    if grade < 3:
        return 1, max(1.3, ease_factor - 0.2), 0

    new_ef = max(1.3, ease_factor + 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
    new_reps = repetitions + 1

    if new_reps == 1:
        new_interval = 1
    elif new_reps == 2:
        new_interval = 6
    else:
        new_interval = round(interval_days * new_ef)

    return new_interval, new_ef, new_reps
