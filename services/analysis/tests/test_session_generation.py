"""Tests for run_generation pool-first reuse paths.

Stubs monkeypatch the module globals (RPC + generate). All stubs accept
`**kwargs` so production-side signature drift doesn't break them (R24).
`run_generation` is async; we drive it with `asyncio.run` to avoid
depending on pytest-asyncio config.
"""

from __future__ import annotations

import asyncio
import os

import pytest

import app.content.session_generation as sg
from app.content.generate import GeneratedSegment, GenerationResult


def _payload(n: int = 5) -> dict:
    return {
        "session_id": "sess-1",
        "learner_id": "learner-1",
        "domain": "logistics",
        "source_lang": "en",
        "target_lang": "ko",
        "params": {
            "topics": ["logistics"],
            "user_level": 3,
            "duration": "medium",
            "n": n,
            "current_context": None,
        },
    }


def _fresh_result(n: int = 5) -> GenerationResult:
    segs = tuple(
        GeneratedSegment(
            source_text=f"phrase {i}",
            source_lang="en",
            target_lang="ko",
            register="operational",
            difficulty_level=5,
            domain="logistics",
        )
        for i in range(n)
    )
    return GenerationResult(
        scenario_summary="fresh scenario",
        segments=segs,
        prompt_template_hash="th",
        prompt_vars_hash="vh",
    )


class _Recorder:
    """Collects calls + installs stubs on the session_generation module."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: dict[str, list] = {}
        self.events: list[dict] = []
        self.generate_called = False
        self.pool_called = False
        self._mp = monkeypatch
        self._seg_counter = 0

        monkeypatch.setattr(sg, "compute_generation_keys", lambda params: ("th", "vh"))

        async def publish(event, **_kw):
            self.events.append(event)

        async def plan(*args, **kwargs):
            self.calls.setdefault("plan", []).append((args, kwargs))

        async def gen_set(*args, **kwargs):
            self.calls.setdefault("gen_set", []).append((args, kwargs))
            return "new-set-id"

        async def seg_insert(payload, **_kw):
            self._seg_counter += 1
            return {"segment_id": f"seg-{self._seg_counter}"}

        def fake_embed(texts, **_kw):
            return [[0.1]] * len(texts)

        def fake_tts(text, lang, **_kw):
            return "audio-key"

        monkeypatch.setattr(sg, "publish_generation_event", publish)
        monkeypatch.setattr(sg, "push_session_plan", plan)
        monkeypatch.setattr(sg, "push_generated_set", gen_set)
        monkeypatch.setattr(sg, "push_segment_insert", seg_insert)
        monkeypatch.setattr(sg, "embed_texts", fake_embed)
        monkeypatch.setattr(sg, "generate_segment_audio", fake_tts)

    def stub_pool(self, result):
        async def pool(*args, **kwargs):
            self.pool_called = True
            return result

        self._mp.setattr(sg, "query_segment_pool", pool)

    def stub_generate(self, result):
        def gen(params, **_kw):
            self.generate_called = True
            return result

        self._mp.setattr(sg, "generate_segments", gen)


# ── B7 / B5 / B11: reuse hit — no LLM, plan in order, complete event ────


def test_reuse_hit_skips_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERATION_POOL_REUSE", "1")
    rec = _Recorder(monkeypatch)
    rec.stub_pool(
        {
            "set_id": "set-1",
            "segment_ids": ["a", "b", "c", "d", "e"],
            "scenario_summary": "reused story",
        }
    )
    # If the LLM path is taken this raises — proves it isn't.
    rec.stub_generate(_fresh_result())
    rec.generate_called = False

    out = asyncio.run(sg.run_generation({}, _payload(n=5)))

    assert out == {"ok": True, "count": 5, "reused": True}
    assert rec.generate_called is False  # B7: no LLM/TTS/embed on hit
    plan_args, plan_kwargs = rec.calls["plan"][0]
    assert plan_args[1] == ["a", "b", "c", "d", "e"]  # B5: exact order
    assert plan_kwargs["generated_set_id"] == "set-1"  # ledgered
    assert "gen_set" not in rec.calls  # didn't record a new set
    assert any(e["type"] == "complete" for e in rec.events)  # B11: overlay closes


# ── B8: miss — generate, record the set, plan with the new set id ───────


def test_miss_generates_and_records_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERATION_POOL_REUSE", "1")
    rec = _Recorder(monkeypatch)
    rec.stub_pool(None)  # pool miss
    rec.stub_generate(_fresh_result(n=5))

    out = asyncio.run(sg.run_generation({}, _payload(n=5)))

    assert out["ok"] is True and out["count"] == 5
    assert rec.generate_called is True
    assert "gen_set" in rec.calls  # recorded for future reuse
    gen_args, _ = rec.calls["gen_set"][0]
    assert gen_args[3] == [f"seg-{i}" for i in range(1, 6)]  # final ids recorded
    _, plan_kwargs = rec.calls["plan"][0]
    assert plan_kwargs["generated_set_id"] == "new-set-id"  # atomic mark-seen


# ── B9: flag off — never queries the pool, always generates ─────────────


def test_flag_off_skips_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GENERATION_POOL_REUSE", "0")
    rec = _Recorder(monkeypatch)
    rec.stub_pool({"set_id": "x", "segment_ids": ["a"] * 5, "scenario_summary": "y"})
    rec.stub_generate(_fresh_result(n=5))

    out = asyncio.run(sg.run_generation({}, _payload(n=5)))

    assert out["ok"] is True
    assert rec.pool_called is False  # never consulted the pool
    assert rec.generate_called is True  # generated fresh
