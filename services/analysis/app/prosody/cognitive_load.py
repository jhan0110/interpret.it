"""
Heuristic cognitive load classifier.

Maps (pause_rate, filler_rate, silence_ratio) → CognitiveLoad band.

Band thresholds (tunable — document changes in git commit message):

  low:        pause_rate < 0.5 AND filler_rate < 0.04 AND silence_ratio < 0.15
  moderate:   pause_rate < 1.2 AND filler_rate < 0.10 AND silence_ratio < 0.30
  high:       pause_rate < 2.5 AND filler_rate < 0.20 AND silence_ratio < 0.50
  overloaded: everything above those bounds

  pause_rate     = pauses per second of *speech* (not total) duration
  filler_rate    = filler_count / word_count — a unitless fraction of
                   words that the lexicon flagged as disfluencies
  silence_ratio  = fraction of total duration that is silence [0,1]

All three inputs must exceed the band upper bound to escalate to the
next band. If any single metric is critically high (pause_rate ≥ 3.0
OR silence_ratio ≥ 0.60), we clamp to "overloaded" immediately.

History note: an earlier filler_rate definition divided by `mean_wpm`,
which made the unit `fillers·min/word` rather than a rate. The
calibrated thresholds were unstable as a result — a fast speaker with
many fillers and a slow speaker with the same proportion of fillers
got wildly different classifications. The current definition is
unitless and rebased.
"""

from __future__ import annotations

from typing import Literal

CognitiveLoad = Literal["low", "moderate", "high", "overloaded"]


def classify_cognitive_load(
    pause_count: int,
    speech_duration_s: float,
    filler_count: int,
    mean_wpm: float,  # kept for backward compatibility (unused in the rate calc)
    silence_ratio: float,
    *,
    word_count: int | None = None,
) -> CognitiveLoad:
    if speech_duration_s <= 0:
        return "overloaded"

    pause_rate = pause_count / speech_duration_s
    # New: filler_rate is a unitless fraction (filler_count / word_count).
    # When word_count isn't supplied (legacy callers), fall back to
    # estimating words from mean_wpm × speech_duration, which is
    # imperfect but better than the dimensional mess of the old formula.
    if word_count is None:
        word_count = max(1, int(round(mean_wpm * speech_duration_s / 60.0)))
    filler_rate = filler_count / max(word_count, 1)

    # Hard clamps for extreme single metrics
    if pause_rate >= 3.0 or silence_ratio >= 0.60:
        return "overloaded"

    if pause_rate < 0.5 and filler_rate < 0.04 and silence_ratio < 0.15:
        return "low"
    if pause_rate < 1.2 and filler_rate < 0.10 and silence_ratio < 0.30:
        return "moderate"
    if pause_rate < 2.5 and filler_rate < 0.20 and silence_ratio < 0.50:
        return "high"
    return "overloaded"
