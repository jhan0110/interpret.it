"""Derive prosody metrics from ASR word-level timestamps.

Pure-Python replacement for the silero-vad + librosa pipeline. Uses the
word boundaries that the ASR (Groq Whisper or faster-whisper) already
emits, so it adds no audio decode, no model load, no extra dependency.

Loses pitch and energy features. Retains pause count, filler count,
pace (WPM), silence ratio, and the existing cognitive-load classifier.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from app.asr.transcribe import WordToken
from app.contracts.models import ProsodyResult
from app.prosody.cognitive_load import classify_cognitive_load
from app.prosody.filler_lexicon import FILLER_LEXICON

_PAUSE_MS = 300


def _count_fillers(words: list[WordToken], lang: str) -> int:
    lexicon = FILLER_LEXICON.get(lang, frozenset())
    if not lexicon or not words:
        return 0
    return sum(
        1 for w in words
        if w.word.strip().lower().strip(".,!?;:") in lexicon
    )


def compute_prosody_from_words(
    words: list[WordToken],
    audio_duration_s: float,
    lang: Literal["ko", "en", "es", "zh"],
    attempt_id: UUID,
    feedback_audio_path: str,
    started_at: datetime,
) -> ProsodyResult:
    """Build a ProsodyResult from ASR word timestamps. CPU-only, no I/O."""
    duration_ms = max(0.0, audio_duration_s * 1000.0)
    now = datetime.now(UTC)
    latency_ms = int((now - started_at).total_seconds() * 1000)

    if not words or duration_ms == 0:
        return ProsodyResult(
            attempt_id=attempt_id,
            pause_count=0,
            filler_count=0,
            mean_wpm=0.0,
            silence_ratio=1.0,
            cognitive_load_estimate="moderate",
            feedback_audio_path=feedback_audio_path,
            computed_at=now,
            latency_ms=latency_ms,
        )

    pause_count = 0
    total_silence_ms = 0.0
    prev_end_ms = 0.0
    for w in words:
        gap_ms = max(0.0, w.start_ms - prev_end_ms)
        if gap_ms >= _PAUSE_MS:
            pause_count += 1
        total_silence_ms += gap_ms
        prev_end_ms = w.end_ms
    total_silence_ms += max(0.0, duration_ms - prev_end_ms)

    silence_ratio = min(1.0, max(0.0, total_silence_ms / duration_ms))
    speech_duration_s = max(0.0, (duration_ms - total_silence_ms) / 1000.0)
    # WPM uses *speech* duration, not total audio duration, so a learner
    # with long leading/trailing silence isn't reported as slower than
    # they actually spoke. Earlier versions divided by `duration_ms`,
    # which made `mean_wpm` and `pause_rate` dimensionally inconsistent
    # in the classifier and biased classification toward "overloaded".
    mean_wpm = len(words) / max(speech_duration_s / 60.0, 1e-3)
    filler_count = _count_fillers(words, lang)

    cognitive_load = classify_cognitive_load(
        pause_count=pause_count,
        speech_duration_s=speech_duration_s,
        filler_count=filler_count,
        mean_wpm=mean_wpm,
        silence_ratio=silence_ratio,
        word_count=len(words),
    )

    return ProsodyResult(
        attempt_id=attempt_id,
        pause_count=pause_count,
        filler_count=filler_count,
        mean_wpm=mean_wpm,
        silence_ratio=silence_ratio,
        cognitive_load_estimate=cognitive_load,
        feedback_audio_path=feedback_audio_path,
        computed_at=now,
        latency_ms=latency_ms,
    )
