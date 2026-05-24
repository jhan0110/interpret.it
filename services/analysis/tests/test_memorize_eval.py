"""Tests for the memorization evaluator.

Mirrors the style of test_content_generate.py: monkeypatch
``structured_generate`` so no real Claude call is made, and stub the Redis
client so no Redis instance is required.
"""

from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timezone
from uuid import uuid4

import pytest

os.environ.setdefault("USE_MOCKS", "1")

# The real Anthropic SDK isn't required for these tests — we monkeypatch
# `structured_generate` directly. Stub the module so `app.llm.client`'s
# top-level `import anthropic` succeeds in lean environments.
if "anthropic" not in sys.modules:
    _stub = types.ModuleType("anthropic")
    _stub.Anthropic = lambda *a, **k: None  # type: ignore[attr-defined]
    sys.modules["anthropic"] = _stub

from app.evaluation import memorize as memorize_mod
from app.evaluation.memorize import (
    _compute_overall_score,
    evaluate_memorization,
    extract_key_points,
)


class _FakeRedis:
    """Just enough of the sync redis API to back the keypoints cache."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.last_ex: int | None = None

    def get(self, key: str) -> str | None:
        return self.store.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value
        self.last_ex = ex


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(memorize_mod, "_get_redis", lambda: fake)
    return fake


def _stub_extract(monkeypatch: pytest.MonkeyPatch, points: list[dict]) -> list[dict]:
    """Force ``structured_generate`` (in memorize_mod) to return canned key points."""
    calls: list[dict] = []

    def _fake(*, system: str, user: str, tool: dict, max_tokens: int = 1024):
        calls.append({"system": system, "user": user, "tool": tool["name"]})
        return {"key_points": points}

    monkeypatch.setattr(memorize_mod, "structured_generate", _fake)
    return calls


def _stub_eval(
    monkeypatch: pytest.MonkeyPatch,
    extract_points: list[dict],
    eval_payload: dict,
) -> list[dict]:
    """Force structured_generate to return extract output then eval output."""
    calls: list[dict] = []
    sequence = iter(
        [
            {"key_points": extract_points},
            eval_payload,
        ]
    )

    def _fake(*, system: str, user: str, tool: dict, max_tokens: int = 1024):
        calls.append({"tool": tool["name"], "user": user, "system": system})
        return next(sequence)

    monkeypatch.setattr(memorize_mod, "structured_generate", _fake)
    return calls


def test_extract_key_points_returns_keypoints(monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis) -> None:
    _stub_extract(
        monkeypatch,
        [
            {"text": "convoy departs at 0600", "importance": "primary"},
            {"text": "route Bravo", "importance": "primary"},
            {"text": "weather is clear", "importance": "secondary"},
        ],
    )
    seg_id = uuid4()

    points = extract_key_points(seg_id, "Convoy departs at 0600 via route Bravo; weather clear.", "en")

    assert len(points) == 3
    assert {p.text for p in points} == {"convoy departs at 0600", "route Bravo", "weather is clear"}
    assert all(p.recalled is False for p in points)
    assert points[0].importance == "primary"
    assert points[2].importance == "secondary"
    assert f"keypoints:{seg_id}" in fake_redis.store
    assert fake_redis.last_ex == 604800


def test_extract_key_points_uses_cache_on_second_call(
    monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
) -> None:
    calls = _stub_extract(
        monkeypatch,
        [
            {"text": "Alpha", "importance": "primary"},
            {"text": "Bravo", "importance": "secondary"},
        ],
    )
    seg_id = uuid4()

    first = extract_key_points(seg_id, "Alpha then Bravo.", "en")
    second = extract_key_points(seg_id, "Alpha then Bravo.", "en")

    assert len(calls) == 1, "second call should hit Redis cache, not Claude"
    assert [p.text for p in first] == [p.text for p in second]
    assert [p.importance for p in first] == [p.importance for p in second]


def test_compute_overall_score_all_primary_recalled_no_bonus() -> None:
    from app.contracts.models import KeyPoint

    kps = [
        KeyPoint(text="a", importance="primary", recalled=True),
        KeyPoint(text="b", importance="primary", recalled=True),
        KeyPoint(text="c", importance="secondary", recalled=True),
    ]
    score = _compute_overall_score(kps, verbatim_bonus=0.0)
    assert score == pytest.approx(0.85, abs=1e-6)


def test_compute_overall_score_all_recalled_max_bonus() -> None:
    from app.contracts.models import KeyPoint

    kps = [
        KeyPoint(text="a", importance="primary", recalled=True),
        KeyPoint(text="b", importance="primary", recalled=True),
        KeyPoint(text="c", importance="secondary", recalled=True),
    ]
    score = _compute_overall_score(kps, verbatim_bonus=0.15)
    assert score == pytest.approx(1.0, abs=1e-6)


def test_compute_overall_score_half_recalled() -> None:
    from app.contracts.models import KeyPoint

    # 2 primaries (1 recalled) + 2 secondaries (1 recalled)
    # units_recovered = 1 + 0.5 = 1.5; units_total = 1 + 1 + 0.5 + 0.5 = 3
    # recall_ratio = 0.5; recall_score = 0.425
    kps = [
        KeyPoint(text="a", importance="primary", recalled=True),
        KeyPoint(text="b", importance="primary", recalled=False),
        KeyPoint(text="c", importance="secondary", recalled=True),
        KeyPoint(text="d", importance="secondary", recalled=False),
    ]
    score = _compute_overall_score(kps, verbatim_bonus=0.0)
    assert score == pytest.approx(0.425, abs=1e-3)


def test_compute_overall_score_caps_at_one() -> None:
    from app.contracts.models import KeyPoint

    kps = [KeyPoint(text="a", importance="primary", recalled=True)]
    # Even if Claude (mis)reports verbatim_bonus > 0.15 the clamp keeps us ≤ 1.0
    score = _compute_overall_score(kps, verbatim_bonus=0.5)
    assert 0.99 <= score <= 1.0


def test_evaluate_memorization_returns_semantic_result_with_keypoints(
    monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
) -> None:
    extract_points = [
        {"text": "convoy departs 0600", "importance": "primary"},
        {"text": "route Bravo", "importance": "primary"},
        {"text": "weather clear", "importance": "secondary"},
    ]
    eval_payload = {
        "key_points": [
            {"text": "convoy departs 0600", "recalled": True},
            {"text": "route Bravo", "recalled": True},
            {"text": "weather clear", "recalled": True},
        ],
        "verbatim_bonus": 0.0,
        "feedback_text": "Solid recall — every point landed.",
        "followup_exercise": {
            "type": "repeat",
            "prompt_text": "Repeat the phrase one more time, slightly faster.",
        },
    }
    _stub_eval(monkeypatch, extract_points, eval_payload)

    result = evaluate_memorization(
        attempt_id=uuid4(),
        segment_id=uuid4(),
        source_text="Convoy departs at 0600 via route Bravo; weather is clear.",
        source_lang="en",
        target_lang="en",
        register="formal-military",
        domain="logistics",
        difficulty_level=3,
        user_transcript="Convoy departs at 0600 via route Bravo, weather is clear.",
        feedback_audio_path="placeholder/feedback.mp3",
        followup_audio_path="placeholder/followup.mp3",
        start_time=datetime.now(timezone.utc),
    )

    assert result.mode == "memorization"
    assert result.reference_translation.startswith("Convoy departs")
    assert result.errors == []
    assert result.acceptable_paraphrases == []
    assert result.key_points is not None
    assert len(result.key_points) == 3
    assert all(kp.recalled for kp in result.key_points)
    # all primary + all secondary recalled, no verbatim bonus → 0.85
    assert result.overall_score == pytest.approx(0.85, abs=1e-3)
    assert result.followup_exercise.prompt_audio_path == "placeholder/followup.mp3"


def test_evaluate_memorization_half_recall_scores_near_half(
    monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
) -> None:
    extract_points = [
        {"text": "alpha", "importance": "primary"},
        {"text": "bravo", "importance": "primary"},
        {"text": "charlie", "importance": "secondary"},
        {"text": "delta", "importance": "secondary"},
    ]
    eval_payload = {
        "key_points": [
            {"text": "alpha", "recalled": True},
            {"text": "bravo", "recalled": False},
            {"text": "charlie", "recalled": True},
            {"text": "delta", "recalled": False},
        ],
        "verbatim_bonus": 0.0,
        "feedback_text": "Half the load-bearing units landed; drill the missed primary.",
        "followup_exercise": {"type": "drill_term", "prompt_text": "Repeat 'bravo'."},
    }
    _stub_eval(monkeypatch, extract_points, eval_payload)

    result = evaluate_memorization(
        attempt_id=uuid4(),
        segment_id=uuid4(),
        source_text="alpha bravo charlie delta",
        source_lang="en",
        target_lang="en",
        register="informal",
        domain="operations",
        difficulty_level=2,
        user_transcript="alpha charlie",
        feedback_audio_path="fb.mp3",
        followup_audio_path="fu.mp3",
        start_time=datetime.now(timezone.utc),
    )

    assert result.mode == "memorization"
    assert result.overall_score == pytest.approx(0.425, abs=1e-3)


def test_evaluate_memorization_full_recall_with_verbatim_hits_one(
    monkeypatch: pytest.MonkeyPatch, fake_redis: _FakeRedis
) -> None:
    extract_points = [
        {"text": "alpha", "importance": "primary"},
        {"text": "bravo", "importance": "secondary"},
    ]
    eval_payload = {
        "key_points": [
            {"text": "alpha", "recalled": True},
            {"text": "bravo", "recalled": True},
        ],
        "verbatim_bonus": 0.15,
        "feedback_text": "Word-for-word match.",
        "followup_exercise": {"type": "repeat", "prompt_text": "Again."},
    }
    _stub_eval(monkeypatch, extract_points, eval_payload)

    result = evaluate_memorization(
        attempt_id=uuid4(),
        segment_id=uuid4(),
        source_text="alpha bravo",
        source_lang="en",
        target_lang="en",
        register="informal",
        domain="operations",
        difficulty_level=1,
        user_transcript="alpha bravo",
        feedback_audio_path="fb.mp3",
        followup_audio_path="fu.mp3",
        start_time=datetime.now(timezone.utc),
    )

    assert result.overall_score == pytest.approx(1.0, abs=1e-3)
