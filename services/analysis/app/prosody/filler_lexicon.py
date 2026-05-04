"""
Per-language filler word lexicons for detecting disfluencies in transcripts.

Add entries here to expand coverage. Keys are BCP-47 language codes.
All entries are lowercase; comparison should be case-insensitive and
strip leading/trailing punctuation before matching.
"""

from __future__ import annotations

FILLER_LEXICON: dict[str, frozenset[str]] = {
    "ko": frozenset(
        {
            "어",
            "음",
            "그",
            "그냥",
            "저",
            "뭐",
            "그러니까",
            "이제",
            "아",
            "예",
            "네",
            "좀",
            "그래서",
            "뭐냐",
            "그거",
            "막",
            "약간",
        }
    ),
    "en": frozenset(
        {
            "um",
            "uh",
            "like",
            "you know",
            "you know what i mean",
            "i mean",
            "basically",
            "actually",
            "literally",
            "right",
            "so",
            "well",
            "okay",
            "er",
            "ah",
        }
    ),
}
