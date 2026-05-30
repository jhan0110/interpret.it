from __future__ import annotations

from app.prosody.cognitive_load import classify_cognitive_load

# After the H7 fix, `filler_rate = filler_count / word_count` (unitless),
# not `filler_count / mean_wpm` (which was dimensionally wrong).
# When the new `word_count` keyword isn't supplied, the legacy path
# estimates it as `mean_wpm * speech_duration / 60`, so passing
# explicit `word_count` here keeps the tests deterministic.


def test_zero_speech_is_overloaded() -> None:
    assert classify_cognitive_load(0, 0.0, 0, 0.0, 0.0, word_count=0) == "overloaded"


def test_clean_delivery_is_low() -> None:
    # 1 pause / 10s = 0.1 pause_rate; 1 filler over 20 words = 0.05 ratio.
    # Wait — 1 filler / 20 words = 0.05, the low band needs < 0.04. Use a
    # cleaner profile: 1 pause, 1 filler over 30 words, low silence.
    assert (
        classify_cognitive_load(1, 10.0, 1, 180.0, 0.05, word_count=30) == "low"
    )


def test_some_pauses_is_moderate() -> None:
    # 8 pauses / 10s = 0.8 (< 1.2). 4 fillers / 50 words = 0.08 (< 0.10).
    # silence 0.25 (< 0.30) → moderate.
    assert (
        classify_cognitive_load(8, 10.0, 4, 300.0, 0.25, word_count=50) == "moderate"
    )


def test_heavy_disfluency_is_high() -> None:
    # 20 pauses / 10s = 2.0 (< 2.5), 5 fillers / 30 words = 0.167 (< 0.20),
    # silence 0.45 (< 0.50) → high.
    assert (
        classify_cognitive_load(20, 10.0, 5, 180.0, 0.45, word_count=30) == "high"
    )


def test_extreme_silence_clamps_to_overloaded() -> None:
    assert (
        classify_cognitive_load(2, 10.0, 2, 100.0, 0.70, word_count=20) == "overloaded"
    )


def test_extreme_pauses_clamps_to_overloaded() -> None:
    assert (
        classify_cognitive_load(35, 10.0, 1, 100.0, 0.10, word_count=20) == "overloaded"
    )
