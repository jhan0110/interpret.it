"""
Waveform disfluency splicer.

Splices pre-recorded filler/silence clips into a clean TTS audio file at
specified timestamps. Uses pydub; applies 10ms crossfades at splice points
to prevent clicks.

Clip assets live in audio_assets/disfluencies/. The asset lookup table is
defined at module level so it can be extended without touching splice logic.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Literal

from pydub import AudioSegment

log = logging.getLogger(__name__)

DisfluencyType = Literal["filler_ko", "filler_en", "breath", "silence_200", "silence_500", "silence_1000", "silence_2000"]


class DisfluencyInsertion:
    __slots__ = ("timestamp_ms", "type", "duration_ms")

    def __init__(self, timestamp_ms: int, type: DisfluencyType, duration_ms: int) -> None:
        self.timestamp_ms = timestamp_ms
        self.type = type
        self.duration_ms = duration_ms


_ASSETS_DIR = Path(os.getenv("AUDIO_ASSETS_DIR", "audio_assets/disfluencies"))

# Maps DisfluencyType → asset filename relative to _ASSETS_DIR.
# Add new entries when real recordings arrive.
_ASSET_MAP: dict[str, str] = {
    "silence_200": "silence_200ms.wav",
    "silence_500": "silence_500ms.wav",
    "silence_1000": "silence_1000ms.wav",
    "silence_2000": "silence_2000ms.wav",
    "filler_ko": "filler_ko.wav",
    "filler_en": "filler_en.wav",
    "breath": "breath.wav",
}

_CROSSFADE_MS = 10
_TARGET_SAMPLE_RATE = 24_000
_TARGET_CHANNELS = 1


def _load_clip(disfluency_type: str, duration_ms: int) -> AudioSegment:
    """Load a disfluency clip, falling back to generated silence if missing."""
    asset_name = _ASSET_MAP.get(disfluency_type)
    if asset_name:
        asset_path = _ASSETS_DIR / asset_name
        if asset_path.exists():
            clip = AudioSegment.from_file(str(asset_path))
            # Trim or pad to requested duration
            if len(clip) > duration_ms:
                clip = clip[:duration_ms]
            elif len(clip) < duration_ms:
                clip = clip + AudioSegment.silent(duration=duration_ms - len(clip))
            return clip.set_channels(_TARGET_CHANNELS).set_frame_rate(_TARGET_SAMPLE_RATE)

    # Fallback: generate silence of requested duration
    return AudioSegment.silent(duration=duration_ms).set_channels(_TARGET_CHANNELS).set_frame_rate(_TARGET_SAMPLE_RATE)


def splice_disfluencies(
    clean_audio_path: str,
    spec: list[DisfluencyInsertion],
    output_path: str,
) -> str:
    """
    Splice disfluency clips into clean_audio_path at the specified timestamps.

    Args:
        clean_audio_path: Path to the source (clean TTS) audio file.
        spec: List of DisfluencyInsertion, sorted ascending by timestamp_ms.
              If unsorted, this function will sort internally.
        output_path: Destination path for the spliced audio file.

    Returns:
        output_path (convenience for callers).

    The output duration equals:
        original_duration + sum(insertion.duration_ms for insertion in spec)
    within ±5ms tolerance (pydub frame rounding).
    """
    base = (
        AudioSegment.from_file(clean_audio_path)
        .set_channels(_TARGET_CHANNELS)
        .set_frame_rate(_TARGET_SAMPLE_RATE)
    )

    sorted_spec = sorted(spec, key=lambda s: s.timestamp_ms)

    # Drop out-of-bounds insertions explicitly rather than silently
    # clamping them all to the end of the base track (which would
    # stack every overflow at the tail).
    base_len = len(base)
    filtered = [s for s in sorted_spec if 0 <= s.timestamp_ms <= base_len]
    dropped = len(sorted_spec) - len(filtered)
    if dropped:
        log.warning(
            "splice: dropped %d insertion(s) outside base [0, %d]",
            dropped,
            base_len,
        )

    result = AudioSegment.empty()
    cursor_ms = 0

    for insertion in filtered:
        cut_at = max(0, min(insertion.timestamp_ms, base_len))

        # Append base up to cut point (with crossfade overlap if possible)
        if cut_at > cursor_ms:
            chunk = base[cursor_ms:cut_at]
            if len(result) > 0 and len(chunk) >= _CROSSFADE_MS:
                result = result.append(chunk, crossfade=_CROSSFADE_MS)
            else:
                result += chunk

        # Load and append the disfluency clip
        clip = _load_clip(insertion.type, insertion.duration_ms)
        if len(result) > 0 and len(clip) >= _CROSSFADE_MS:
            result = result.append(clip, crossfade=_CROSSFADE_MS)
        else:
            result += clip

        cursor_ms = cut_at

    # Append remaining base audio
    if cursor_ms < len(base):
        tail = base[cursor_ms:]
        if len(result) > 0 and len(tail) >= _CROSSFADE_MS:
            result = result.append(tail, crossfade=_CROSSFADE_MS)
        else:
            result += tail

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    result.export(output_path, format="wav")
    return output_path
