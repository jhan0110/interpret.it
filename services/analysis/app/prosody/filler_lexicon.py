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

The Spanish lexicon follows the same conservative discipline. Common
markers like `como` (also the comparative "like") and `vale`
(affirmation, not stalling) are excluded because they can't be
disambiguated without context-aware POS tagging. Expand only with
linguist sign-off; document the reasoning per added entry.

If a linguist re-evaluates either lexicon, expand here with a
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
    "es": frozenset(
        {
            # Pure hesitation vocalisations.
            "eh",
            "este",  # "this" but overwhelmingly stalling in interpretation contexts
            # Discourse markers used as stalling tokens.
            "pues",  # "well"
            "bueno",  # "good/well" — high-confidence filler in non-confirming positions
            "o sea",  # "I mean / that is"
            # NOT INCLUDED (would over-flag; revisit with linguist sign-off):
            #   "como"  — also the comparative "like"; can't disambiguate without context
            #   "vale"  — affirmation; not unambiguously a filler
            #   "digamos" — "let's say"; meaningful framing in formal Spanish
        }
    ),
}
