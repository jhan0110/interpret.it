"""User-facing difficulty (1–5) → internal ladder (1–10) mapping.

The internal 1–10 ladder is the source of truth (see ARCHITECTURE.md §6).
The operator never sees those numbers; they pick a 1–5 user level and
this module spreads the request across the matching internal band.
Overlap is intentional — adjacent user levels share segments so the
picker has room to maneuver via mastery.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

UserLevel = Literal[1, 2, 3, 4, 5]


@dataclass(frozen=True)
class LevelBand:
    user_level: UserLevel
    label: str
    internal_range: tuple[int, int]  # inclusive
    peak: int                          # weighted-sample peak inside the range
    description: str


LEVEL_BANDS: dict[UserLevel, LevelBand] = {
    1: LevelBand(
        user_level=1,
        label="Foundational",
        internal_range=(1, 3),
        peak=2,
        description="Short, slow, formal, common vocabulary.",
    ),
    2: LevelBand(
        user_level=2,
        label="Building",
        internal_range=(2, 5),
        peak=3,
        description="Slightly faster, some idiom.",
    ),
    3: LevelBand(
        user_level=3,
        label="Working",
        internal_range=(4, 7),
        peak=5,
        description="Conversational pace, mixed register.",
    ),
    4: LevelBand(
        user_level=4,
        label="Advanced",
        internal_range=(6, 9),
        peak=7,
        description="Fast, accented, technical jargon.",
    ),
    5: LevelBand(
        user_level=5,
        label="Expert",
        internal_range=(8, 10),
        peak=9,
        description="Maximum pace, heavy jargon, abrupt topic shifts.",
    ),
}


def internal_levels_for_user_level(user_level: UserLevel) -> list[int]:
    band = LEVEL_BANDS[user_level]
    lo, hi = band.internal_range
    return list(range(lo, hi + 1))


def sample_internal_levels(
    user_level: UserLevel, n: int, rng: "object | None" = None
) -> list[int]:
    """Generate `n` internal-level values, weighted toward the band's peak.

    Triangular-ish weighting: peak is 2× as likely as the range edges.
    """
    import random

    rng_ = rng if rng is not None else random
    band = LEVEL_BANDS[user_level]
    lo, hi = band.internal_range
    levels = list(range(lo, hi + 1))
    weights = [
        2.0 - abs(level - band.peak) / max(1, max(hi - band.peak, band.peak - lo))
        for level in levels
    ]
    return rng_.choices(levels, weights=weights, k=n)
