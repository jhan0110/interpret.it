"""
Prosody analysis pipeline.

Fast-path target: ≤2s end-to-end.
No LLM calls — silero-vad + librosa only.

Filler detection cross-references word-level timestamps from ASR.
Until Agent 3 publishes real transcripts, callers may pass word_tokens=None
and filler_count will default to 0.
"""

from __future__ import annotations

import io
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import librosa
import numpy as np
from pydub import AudioSegment

from app.contracts.models import ProsodyResult
from app.prosody.cognitive_load import classify_cognitive_load
from app.prosody.filler_lexicon import FILLER_LEXICON

if TYPE_CHECKING:
    from app.asr.transcribe import WordToken

_SAMPLE_RATE = 16_000  # silero-vad requirement


def _load_silero_vad():  # type: ignore[return]
    """Load silero-vad model (cached after first call via torch.hub)."""
    import torch

    model, utils = torch.hub.load(
        repo_or_dir="snakers4/silero-vad",
        model="silero_vad",
        force_reload=False,
        onnx=False,
    )
    return model, utils


def _decode_to_pcm(audio_bytes: bytes) -> tuple[np.ndarray, int]:
    """Decode any pydub-readable format to float32 mono PCM at 16kHz."""
    seg = AudioSegment.from_file(io.BytesIO(audio_bytes))
    seg = seg.set_channels(1).set_frame_rate(_SAMPLE_RATE)
    samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
    samples /= float(2 ** (seg.sample_width * 8 - 1))
    return samples, _SAMPLE_RATE


def _vad_pauses(samples: np.ndarray, sr: int) -> tuple[int, float, float]:
    """
    Run silero-vad and return (pause_count, silence_ratio, speech_duration_s).
    A 'pause' is a silence gap between voiced segments ≥ 300ms.
    """
    import torch

    model, utils = _load_silero_vad()
    get_speech_timestamps = utils[0]

    tensor = torch.from_numpy(samples)
    speech_ts = get_speech_timestamps(tensor, model, sampling_rate=sr)

    total_duration_s = len(samples) / sr
    if total_duration_s == 0:
        return 0, 1.0, 0.0

    speech_samples = sum(ts["end"] - ts["start"] for ts in speech_ts)
    speech_duration_s = speech_samples / sr
    silence_ratio = max(0.0, min(1.0, 1.0 - (speech_duration_s / total_duration_s)))

    pause_count = 0
    min_pause_samples = int(0.300 * sr)
    for i in range(1, len(speech_ts)):
        gap = speech_ts[i]["start"] - speech_ts[i - 1]["end"]
        if gap >= min_pause_samples:
            pause_count += 1

    return pause_count, silence_ratio, speech_duration_s


def _mean_wpm_from_tokens(
    word_tokens: list[WordToken], speech_duration_s: float
) -> float:
    """Derive WPM from word-level timestamps."""
    if not word_tokens or speech_duration_s <= 0:
        return 0.0
    word_count = len(word_tokens)
    return (word_count / speech_duration_s) * 60.0


def _count_fillers(word_tokens: list[WordToken], lang: str) -> int:
    """Count filler words by cross-referencing the per-language lexicon."""
    lexicon = FILLER_LEXICON.get(lang, frozenset())
    if not lexicon or not word_tokens:
        return 0
    count = 0
    for token in word_tokens:
        normalized = token.word.strip().lower().strip(".,!?;:")
        if normalized in lexicon:
            count += 1
    return count


def run_prosody_pipeline(
    audio_bytes: bytes,
    attempt_id: UUID,
    lang: str,
    word_tokens: list[WordToken] | None = None,
    feedback_audio_path: str = "placeholder/feedback.wav",
) -> ProsodyResult:
    """
    Run the full prosody fast-path pipeline.

    Args:
        audio_bytes: Raw audio file bytes (any pydub-readable format).
        attempt_id: UUID from AnalysisRequest.
        lang: BCP-47 language code ("ko" or "en").
        word_tokens: Optional word-level timestamps from ASR (Agent 3).
                     If None, filler_count=0 and mean_wpm uses VAD speech duration.
        feedback_audio_path: MinIO key for TTS feedback (set by caller after TTS generation).
    """
    t_start = time.monotonic()

    samples, sr = _decode_to_pcm(audio_bytes)
    pause_count, silence_ratio, speech_duration_s = _vad_pauses(samples, sr)

    if word_tokens is not None:
        filler_count = _count_fillers(word_tokens, lang)
        mean_wpm = _mean_wpm_from_tokens(word_tokens, speech_duration_s)
    else:
        filler_count = 0
        # Estimate WPM from librosa tempo (beats → approximate syllable rate)
        tempo, _ = librosa.beat.beat_track(y=samples, sr=sr)
        mean_wpm = float(tempo) * 0.8 if speech_duration_s > 0 else 0.0

    cognitive_load = classify_cognitive_load(
        pause_count=pause_count,
        speech_duration_s=speech_duration_s,
        filler_count=filler_count,
        mean_wpm=mean_wpm,
        silence_ratio=silence_ratio,
    )

    latency_ms = int((time.monotonic() - t_start) * 1000)

    return ProsodyResult(
        attempt_id=attempt_id,
        pause_count=pause_count,
        filler_count=filler_count,
        mean_wpm=round(mean_wpm, 2),
        silence_ratio=round(silence_ratio, 4),
        cognitive_load_estimate=cognitive_load,
        feedback_audio_path=feedback_audio_path,
        computed_at=datetime.now(UTC),
        latency_ms=latency_ms,
    )
