"""Tests for the per-language filler lexicon and filler counting.

The Chinese (zh) lexicon was added alongside EN↔ZH support. The pure
hesitation markers (嗯/呃/啊) are high-confidence; the demonstratives
那个/这个 are provisional pending Mandarin-linguist sign-off (see the
module docstring in app/prosody/filler_lexicon.py).
"""

from __future__ import annotations

from app.asr.transcribe import WordToken
from app.prosody.filler_lexicon import FILLER_LEXICON
from app.prosody.word_prosody import _count_fillers


def _w(word: str) -> WordToken:
    return WordToken(word=word, start_ms=0, end_ms=100, probability=1.0)


def test_chinese_lexicon_present() -> None:
    assert "zh" in FILLER_LEXICON
    # High-confidence hesitation vocalisations.
    assert "嗯" in FILLER_LEXICON["zh"]
    assert "啊" in FILLER_LEXICON["zh"]


def test_count_fillers_chinese() -> None:
    words = [_w("我们"), _w("嗯"), _w("需要"), _w("那个"), _w("补给")]
    assert _count_fillers(words, "zh") == 2


def test_count_fillers_unknown_lang_is_zero() -> None:
    # Graceful fallback: an unseeded language yields no fillers.
    assert _count_fillers([_w("嗯")], "fr") == 0
