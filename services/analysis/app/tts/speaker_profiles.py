"""
Speaker simulation profiles mapped to difficulty levels 1–10.

Each profile controls TTS pace, voice selection, disfluency injection rate,
and topic-switch probability. The difficulty ladder (ARCHITECTURE.md §6)
uses cognitive_load_estimate to adjust mastery — these profiles control
what the learner *hears*, not what they say.

Level bands:
  1–2   : Slow, clear, neutral accent, no disfluencies. Beginner-friendly.
  3–4   : Slightly faster, minimal disfluencies. Building confidence.
  5–6   : Natural conversational pace, occasional fillers. Intermediate.
  7–8   : Fast, accented, regular fillers, rare topic hints. Advanced.
  9–10  : Very fast, strong accent, frequent fillers+breaths, abrupt topic switches.

ElevenLabs voice IDs are placeholders; replace with real IDs from the voices API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

DisfluencyType = Literal["filler_ko", "filler_en", "breath", "silence_200", "silence_500", "silence_1000", "silence_2000"]


@dataclass(frozen=True)
class SpeakerProfile:
    level: int
    pace_multiplier: float
    accent_voice_id: str
    disfluency_rate_per_min: float
    topic_switch_probability: float
    preferred_disfluency_types: tuple[DisfluencyType, ...]
    description: str


SPEAKER_PROFILES: dict[int, SpeakerProfile] = {
    1: SpeakerProfile(
        level=1,
        pace_multiplier=0.70,
        accent_voice_id="EXAVITQu4vr4xnSDxMaL",  # placeholder: calm neutral
        disfluency_rate_per_min=0.0,
        topic_switch_probability=0.0,
        preferred_disfluency_types=(),
        description="Very slow, clear enunciation, neutral accent, no disfluencies.",
    ),
    2: SpeakerProfile(
        level=2,
        pace_multiplier=0.80,
        accent_voice_id="EXAVITQu4vr4xnSDxMaL",
        disfluency_rate_per_min=0.0,
        topic_switch_probability=0.0,
        preferred_disfluency_types=(),
        description="Slow, clear, neutral accent, no disfluencies.",
    ),
    3: SpeakerProfile(
        level=3,
        pace_multiplier=0.90,
        accent_voice_id="21m00Tcm4TlvDq8ikWAM",  # placeholder: slightly accented
        disfluency_rate_per_min=1.0,
        topic_switch_probability=0.0,
        preferred_disfluency_types=("silence_200",),
        description="Near-natural pace, very occasional silence pauses.",
    ),
    4: SpeakerProfile(
        level=4,
        pace_multiplier=0.95,
        accent_voice_id="21m00Tcm4TlvDq8ikWAM",
        disfluency_rate_per_min=2.0,
        topic_switch_probability=0.02,
        preferred_disfluency_types=("silence_200", "silence_500"),
        description="Near-natural pace, light fillers and pauses.",
    ),
    5: SpeakerProfile(
        level=5,
        pace_multiplier=1.00,
        accent_voice_id="AZnzlk1XvdvUeBnXmlld",  # placeholder: neutral conversational
        disfluency_rate_per_min=4.0,
        topic_switch_probability=0.05,
        preferred_disfluency_types=("filler_en", "silence_500"),
        description="Natural conversational pace, occasional fillers, rare topic hints.",
    ),
    6: SpeakerProfile(
        level=6,
        pace_multiplier=1.05,
        accent_voice_id="AZnzlk1XvdvUeBnXmlld",
        disfluency_rate_per_min=6.0,
        topic_switch_probability=0.08,
        preferred_disfluency_types=("filler_en", "filler_ko", "silence_500"),
        description="Slightly faster than natural, moderate fillers, occasional topic transitions.",
    ),
    7: SpeakerProfile(
        level=7,
        pace_multiplier=1.15,
        accent_voice_id="MF3mGyEYCl7XYWbV9V6O",  # placeholder: accented
        disfluency_rate_per_min=8.0,
        topic_switch_probability=0.12,
        preferred_disfluency_types=("filler_en", "filler_ko", "breath", "silence_200"),
        description="Fast, accented, regular fillers and breaths, occasional topic switches.",
    ),
    8: SpeakerProfile(
        level=8,
        pace_multiplier=1.25,
        accent_voice_id="MF3mGyEYCl7XYWbV9V6O",
        disfluency_rate_per_min=10.0,
        topic_switch_probability=0.18,
        preferred_disfluency_types=("filler_en", "filler_ko", "breath", "silence_200", "silence_500"),
        description="Fast, strong accent, frequent fillers and breaths, topic switches.",
    ),
    9: SpeakerProfile(
        level=9,
        pace_multiplier=1.35,
        accent_voice_id="pNInz6obpgDQGcFmaJgB",  # placeholder: heavy accent
        disfluency_rate_per_min=14.0,
        topic_switch_probability=0.25,
        preferred_disfluency_types=("filler_en", "filler_ko", "breath", "silence_200"),
        description="Very fast, heavy accent, very frequent fillers/breaths, abrupt topic switches.",
    ),
    10: SpeakerProfile(
        level=10,
        pace_multiplier=1.45,
        accent_voice_id="pNInz6obpgDQGcFmaJgB",
        disfluency_rate_per_min=18.0,
        topic_switch_probability=0.35,
        preferred_disfluency_types=("filler_en", "filler_ko", "breath", "silence_200", "silence_500"),
        description="Maximum difficulty: fastest pace, heaviest accent, maximal disfluencies, frequent topic switches.",
    ),
}


def get_speaker_profile(difficulty_level: int) -> SpeakerProfile:
    level = max(1, min(10, difficulty_level))
    return SPEAKER_PROFILES[level]
