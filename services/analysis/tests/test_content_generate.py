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
    with mock.patch.dict(os.environ, {"USE_MOCKS": "0"}):
        with mock.patch(
            "app.content.generate.run_template", return_value=fake_tool_out
        ):
            with mock.patch(
                "app.content.generate.render_template"
            ) as render_mock:
                render_mock.return_value = mock.Mock(
                    system="sys", user="usr"
                )
                result = generate_segments(_params(user_level=3))
    assert len(result.segments) == 10
    assert result.scenario_summary == "Test"
