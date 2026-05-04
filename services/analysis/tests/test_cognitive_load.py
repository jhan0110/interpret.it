from __future__ import annotations

from app.prosody.cognitive_load import classify_cognitive_load


def test_zero_speech_is_overloaded() -> None:
    assert classify_cognitive_load(0, 0.0, 0, 0.0, 0.0) == "overloaded"


def test_clean_delivery_is_low() -> None:
    # 1 pause over 10s = pause_rate 0.1; 1 filler over 120 wpm = filler_rate 0.008; silence 0.05
    assert classify_cognitive_load(1, 10.0, 1, 120.0, 0.05) == "low"


def test_some_pauses_is_moderate() -> None:
    # pause_rate 0.8, filler_rate 0.08, silence 0.25 → moderate
    assert classify_cognitive_load(8, 10.0, 8, 100.0, 0.25) == "moderate"


def test_heavy_disfluency_is_high() -> None:
    # pause_rate 2.0, filler_rate 0.20, silence 0.45 → high
    assert classify_cognitive_load(20, 10.0, 20, 100.0, 0.45) == "high"


def test_extreme_silence_clamps_to_overloaded() -> None:
    assert classify_cognitive_load(2, 10.0, 2, 100.0, 0.70) == "overloaded"


def test_extreme_pauses_clamps_to_overloaded() -> None:
    assert classify_cognitive_load(35, 10.0, 1, 100.0, 0.10) == "overloaded"
