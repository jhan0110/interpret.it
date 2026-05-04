"""
Heuristic cognitive load classifier.

Maps (pause_rate, filler_rate, silence_ratio) → CognitiveLoad band.

Band thresholds (tunable — document changes in git commit message):

  low:        pause_rate < 0.5 AND filler_rate < 0.05 AND silence_ratio < 0.15
  moderate:   pause_rate < 1.2 AND filler_rate < 0.12 AND silence_ratio < 0.30
  high:       pause_rate < 2.5 AND filler_rate < 0.25 AND silence_ratio < 0.50
  overloaded: everything above those bounds

  pause_rate  = pauses per second of speech duration
  filler_rate = filler_count / mean_wpm (fillers per word-per-minute unit)
  silence_ratio = fraction of total duration that is silence [0,1]

All three inputs must exceed the band upper bound to escalate to the next band.
If any single metric is critically high (pause_rate ≥ 3.0 OR silence_ratio ≥ 0.60),
we clamp to "overloaded" immediately.
"""

from __future__ import annotations

from typing import Literal

CognitiveLoad = Literal["low", "moderate", "high", "overloaded"]


def classify_cognitive_load(
    pause_count: int,
    speech_duration_s: float,
    filler_count: int,
    mean_wpm: float,
    silence_ratio: float,
) -> CognitiveLoad:
    if speech_duration_s <= 0:
        return "overloaded"

    pause_rate = pause_count / speech_duration_s
    filler_rate = filler_count / max(mean_wpm, 1.0)

    # Hard clamps for extreme single metrics
    if pause_rate >= 3.0 or silence_ratio >= 0.60:
        return "overloaded"

    if pause_rate < 0.5 and filler_rate < 0.05 and silence_ratio < 0.15:
        return "low"
    if pause_rate < 1.2 and filler_rate < 0.12 and silence_ratio < 0.30:
        return "moderate"
    if pause_rate < 2.5 and filler_rate < 0.25 and silence_ratio < 0.50:
        return "high"
    return "overloaded"
