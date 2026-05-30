"""
Per-language filler word lexicons for detecting disfluencies in transcripts.

Add entries here to expand coverage. Keys are BCP-47 language codes.
All entries are lowercase; comparison should be case-insensitive and
strip leading/trailing punctuation before matching.

The Korean lexicon is intentionally conservative — it sticks to
unambiguous hesitation markers. Entries like `네`, `예`, `좀`, `약간`,
and `그` (a discourse particle, but also a demonstrative determiner)
appear with very high frequency in non-disfluent speech, so counting
them as fillers inflated the cognitive-load classifier toward
"overloaded" for routinely fluent learners.

If a Korean linguist re-evaluates the lexicon, expand here with a
clear comment on what specifically tipped the choice.
"""

from __future__ import annotations

FILLER_LEXICON: dict[str, frozenset[str]] = {
    "ko": frozenset(
        {
            # Pure hesitation vocalisations / fillers.
            "어",
            "음",
            "아",
            # Multi-syllable discourse markers used when the speaker is
            # stalling. These have content-word uses too but the
            # disfluency reading dominates in interpretation contexts.
            "그러니까",
            "뭐냐",
            # Conjunctive disfluencies — overused as filler in spoken Korean.
            "그래서",  # "and so"
            "그냥",    # "just / merely" — overused stalling token
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
