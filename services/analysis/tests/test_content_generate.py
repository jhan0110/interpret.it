"""Tests for content.generate — the LLM-driven phrase set generator.

`USE_MOCKS=1` is the default in dev + tests, so generation returns
deterministic stub data. We assert shape + the few invariants that the
mock guarantees; the real LLM path is exercised only when USE_MOCKS=0
and ANTHROPIC_API_KEY is set (not in CI).
"""

from __future__ import annotations

import os
from unittest import mock

import pytest

# Ensure mocks are on regardless of environment.
os.environ.setdefault("USE_MOCKS", "1")

from app.content.generate import GenerateParams, generate_segments
from app.content.levels import LEVEL_BANDS
from app.content.topics import TOPICS


def _params(**overrides):
    base = dict(
        topics=("logistics",),
        user_level=3,
        duration="medium",
        direction="en-ko",
        n=10,
        current_context=None,
    )
    base.update(overrides)
    return GenerateParams(**base)


def test_generate_segments_returns_n_phrases() -> None:
    result = generate_segments(_params())
    assert len(result.segments) == 10


def test_generate_segments_empty_topics_raises() -> None:
    with pytest.raises(ValueError, match="at least one topic"):
        generate_segments(_params(topics=()))


def test_generate_segments_difficulty_within_band() -> None:
    band = LEVEL_BANDS[3]
    lo, hi = band.internal_range
    result = generate_segments(_params(user_level=3))
    for seg in result.segments:
        assert lo <= seg.difficulty_level <= hi


def test_generate_segments_langs_match_direction() -> None:
    en_ko = generate_segments(_params(direction="en-ko"))
    for seg in en_ko.segments:
        assert seg.source_lang == "en"
        assert seg.target_lang == "ko"

    ko_en = generate_segments(_params(direction="ko-en"))
    for seg in ko_en.segments:
        assert seg.source_lang == "ko"
        assert seg.target_lang == "en"


def test_generate_segments_supports_chinese_direction() -> None:
    en_zh = generate_segments(_params(direction="en-zh"))
    assert len(en_zh.segments) == 10
    for seg in en_zh.segments:
        assert seg.source_lang == "en"
        assert seg.target_lang == "zh"


def test_direction_label_renders_chinese() -> None:
    from app.content.generate import _direction_label

    assert _direction_label("en-zh") == "English → Chinese"
    assert _direction_label("zh-en") == "Chinese → English"
    # Memorization (same-language) renders just the single language.
    assert _direction_label("zh-zh") == "Chinese"


def test_medical_domain_guidance_is_civilian() -> None:
    from app.content.generate import _domain_guidance

    # Low difficulty: civilian framing, explicitly no military.
    low = _domain_guidance(("medical",), internal_max=3)
    assert "CIVILIAN" in low
    for banned in ("combat", "MEDEVAC", "battlefield", "field-medicine"):
        assert banned in low  # they appear inside the "do NOT use" list
    assert "differential" not in low  # no clinic-jargon ask at low difficulty

    # High difficulty: adds clinic jargon / case detail.
    high = _domain_guidance(("medical",), internal_max=9)
    assert "differential diagnosis" in high
    assert "history of present illness" in high

    # Non-medical domains get no override.
    assert _domain_guidance(("logistics",), internal_max=9) == ""


def test_prompt_injects_medical_guidance_and_chinese_conversational() -> None:
    from app.content.generate import _template_variables
    from app.llm.templates import render_template

    med_zh = render_template(
        "generate_segments",
        _template_variables(_params(topics=("medical",), direction="zh-en")),
    )
    # Civilian medical guidance reaches the system prompt.
    assert "CIVILIAN clinical domain" in med_zh.system
    # Chinese source → conversational-Mandarin block is rendered.
    assert "CONVERSATIONAL spoken Mandarin" in med_zh.system

    # English source, non-medical → neither block renders.
    log_en = render_template(
        "generate_segments",
        _template_variables(_params(topics=("logistics",), direction="en-ko")),
    )
    assert "CIVILIAN clinical domain" not in log_en.system
    assert "CONVERSATIONAL spoken Mandarin" not in log_en.system


def test_generate_segments_domain_is_first_topic() -> None:
    result = generate_segments(_params(topics=("operations", "medical")))
    for seg in result.segments:
        assert seg.domain == "operations"


def test_generate_segments_hashes_change_with_inputs() -> None:
    a = generate_segments(_params(topics=("logistics",)))
    b = generate_segments(_params(topics=("diplomacy",)))
    assert a.prompt_vars_hash != b.prompt_vars_hash


def test_generate_segments_hashes_stable_for_same_inputs() -> None:
    a = generate_segments(_params())
    b = generate_segments(_params())
    assert a.prompt_vars_hash == b.prompt_vars_hash
    assert a.prompt_template_hash == b.prompt_template_hash


def test_generate_segments_all_topics_accepted() -> None:
    for topic in TOPICS:
        result = generate_segments(_params(topics=(topic,)))
        assert len(result.segments) == 10


def test_generate_segments_calls_llm_when_mocks_off() -> None:
    fake_tool_out = {
        "scenario_summary": "Test",
        "segments": [
            {
                "source_text": f"Phrase {i}.",
                "register": "formal-military",
                "difficulty_level": 5,
            }
            for i in range(10)
        ],
    }
    # `run_template` now returns `(tool_out, PromptCall)` so the second
    # render is no longer needed for the prompt hash.
    fake_call = mock.Mock(system="sys", user="usr")
    with mock.patch.dict(os.environ, {"USE_MOCKS": "0"}):
        with mock.patch(
            "app.content.generate.run_template",
            return_value=(fake_tool_out, fake_call),
        ) as rt_mock:
            result = generate_segments(_params(user_level=3))
    assert len(result.segments) == 10
    assert result.scenario_summary == "Test"
    # `run_template` should be called exactly once now (was twice).
    assert rt_mock.call_count == 1
