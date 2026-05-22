"""Duration band → target spoken-audio seconds.

The LLM is given the target seconds plus an approximate word count for a
conversational pace; the TTS layer post-validates the actual audio length
and retries the prompt once if it's >25% off.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DurationBand = Literal["short", "medium", "long"]


@dataclass(frozen=True)
class DurationSpec:
    band: DurationBand
    target_seconds: int
    approx_words: int  # at ~140 wpm conversational
    description: str


DURATION_BANDS: dict[DurationBand, DurationSpec] = {
    "short": DurationSpec(
        band="short",
        target_seconds=10,
        approx_words=22,
        description="Short — about 10 seconds of speech.",
    ),
    "medium": DurationSpec(
        band="medium",
        target_seconds=20,
        approx_words=45,
        description="Medium — about 20 seconds of speech.",
    ),
    "long": DurationSpec(
        band="long",
        target_seconds=40,
        approx_words=90,
        description="Long — about 40 seconds of speech.",
    ),
}

DURATION_TOLERANCE = 0.25  # retry generation if measured duration differs by more
