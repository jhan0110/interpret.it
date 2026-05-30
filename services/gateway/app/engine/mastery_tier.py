"""Tier-based mastery: high-water-mark rank derived from recent scores.

Five tiers above the default Initiate state, each gating two adjacent
levels of the internal 1-10 difficulty ladder. Promotion fires when the
last `PROMOTION_WINDOW` at-band attempts have a mean score >=
`PROMOTION_THRESHOLD`. Per user decision: no demotion — the tier is a
high-water mark.

Storage: `mastery_scores.tier` (smallint) + `recent_scores` (JSONB
list capped at ROLLING_WINDOW_CAP).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TypedDict


TIER_NAMES: tuple[str, ...] = (
    "Initiate",
    "Apprentice",
    "Journeyman",
    "Practitioner",
    "Expert",
    "Master",
)

MAX_TIER = len(TIER_NAMES) - 1  # 5
MAX_LEVEL = 10  # internal difficulty ladder upper bound

# Difficulty band per tier index (inclusive). tier 0 (Initiate) has no
# qualifying band — the picker uses the legacy mastery scalar there.
TIER_BANDS: dict[int, tuple[int, int]] = {
    0: (1, 2),   # not used for promotion checks; here for picker fallback
    1: (1, 2),   # Apprentice — promotion from Initiate
    2: (3, 4),   # Journeyman
    3: (5, 6),   # Practitioner
    4: (7, 8),   # Expert
    5: (9, 10),  # Master
}

PROMOTION_WINDOW = 5
PROMOTION_THRESHOLD = 0.80
ROLLING_WINDOW_CAP = 20


class ScoreEntry(TypedDict):
    level: int  # internal difficulty 1..10
    score: float  # 0..1
    ts: str  # ISO 8601


def tier_for_level(level: int) -> int:
    """Return the tier index whose band contains `level`. 1-2 -> 1, 3-4 -> 2,
    ..., 9-10 -> 5. Out-of-range inputs are clamped to [1, MAX_TIER]."""
    clamped = max(1, min(MAX_LEVEL, level))
    return (clamped + 1) // 2


def next_tier_band(current_tier: int) -> tuple[int, int]:
    """The band the learner must prove at to promote OUT of `current_tier`.

    At tier 0 (Initiate), the qualifying band is the Apprentice band (L1-2).
    At tier N, the qualifying band is tier N+1's band (we want to see the
    learner handle the *next* difficulty before promoting).
    """
    target = min(MAX_TIER, max(1, current_tier + 1)) if current_tier < MAX_TIER else MAX_TIER
    return TIER_BANDS[target]


def append_score(
    recent: list[ScoreEntry] | None,
    level: int,
    score: float,
    ts: datetime,
) -> list[ScoreEntry]:
    """Append a new score, cap at ROLLING_WINDOW_CAP, return the new list."""
    entry: ScoreEntry = {
        "level": int(level),
        "score": float(score),
        "ts": ts.isoformat(),
    }
    base = list(recent or [])
    base.append(entry)
    if len(base) > ROLLING_WINDOW_CAP:
        base = base[-ROLLING_WINDOW_CAP:]
    return base


def _in_band(entry: ScoreEntry, band: tuple[int, int]) -> bool:
    lo, hi = band
    return lo <= int(entry["level"]) <= hi


def evaluate_promotion(
    current_tier: int, recent: list[ScoreEntry] | None
) -> int:
    """Check if the learner deserves a promotion. Returns the new tier index.

    Cascades upward: if a learner's recent history qualifies them for two
    promotions in a row (rare but possible after a backfill), they jump
    accordingly. No demotion.
    """
    if current_tier >= MAX_TIER or not recent:
        return current_tier

    tier = current_tier
    while tier < MAX_TIER:
        band = next_tier_band(tier)
        in_band = [e for e in recent if _in_band(e, band)]
        if len(in_band) < PROMOTION_WINDOW:
            return tier
        window = in_band[-PROMOTION_WINDOW:]
        mean = sum(float(e["score"]) for e in window) / len(window)
        if mean < PROMOTION_THRESHOLD:
            return tier
        tier += 1
    return tier


@dataclass(frozen=True)
class TierProgress:
    tier: int
    tier_name: str
    next_tier_name: str | None
    in_band_count: int  # how many at-band attempts they have so far
    window_target: int  # PROMOTION_WINDOW
    current_mean: float  # mean of last `in_band_count` (or last WINDOW) at-band scores; 0 if none
    progress: float  # 0..1 toward promotion; saturates at 1.0


def progress_to_next(
    current_tier: int, recent: list[ScoreEntry] | None
) -> TierProgress:
    """Compute how close the learner is to their next promotion."""
    tier_name = TIER_NAMES[current_tier]
    if current_tier >= MAX_TIER:
        return TierProgress(
            tier=current_tier,
            tier_name=tier_name,
            next_tier_name=None,
            in_band_count=0,
            window_target=PROMOTION_WINDOW,
            current_mean=1.0,
            progress=1.0,
        )

    next_name = TIER_NAMES[current_tier + 1]
    band = next_tier_band(current_tier)
    in_band = [e for e in (recent or []) if _in_band(e, band)]
    in_band_count = len(in_band)
    window = in_band[-PROMOTION_WINDOW:] if in_band else []
    mean = (
        sum(float(e["score"]) for e in window) / len(window) if window else 0.0
    )
    # Two factors blend into the bar: how many at-band attempts have
    # been logged (need PROMOTION_WINDOW) and how close the mean is to
    # the threshold. We take the minimum so the bar never overstates.
    sample_progress = min(1.0, in_band_count / PROMOTION_WINDOW)
    score_progress = min(1.0, mean / PROMOTION_THRESHOLD) if mean > 0 else 0.0
    progress = min(sample_progress, score_progress)

    return TierProgress(
        tier=current_tier,
        tier_name=tier_name,
        next_tier_name=next_name,
        in_band_count=in_band_count,
        window_target=PROMOTION_WINDOW,
        current_mean=mean,
        progress=progress,
    )
