"""Generate a cohesive set of training phrases via Claude.

Stateless. No DB. No TTS. Returns plain Python data — the caller is
responsible for persisting segments and producing audio.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from typing import Literal

from app.content.durations import DURATION_BANDS, DurationBand
from app.content.levels import LEVEL_BANDS, UserLevel, sample_internal_levels
from app.content.topics import TOPIC_DESCRIPTIONS, Topic
from app.llm.templates import render_template, run_template

log = logging.getLogger(__name__)

Direction = Literal["en-ko", "ko-en"]
_DIRECTION_LABEL: dict[Direction, str] = {
    "en-ko": "English → Korean",
    "ko-en": "Korean → English",
}
_SOURCE_LANG_LONG: dict[Direction, str] = {
    "en-ko": "English",
    "ko-en": "Korean",
}


@dataclass(frozen=True)
class GenerateParams:
    topics: tuple[Topic, ...]
    user_level: UserLevel
    duration: DurationBand
    direction: Direction
    n: int = 10
    current_context: str | None = None


@dataclass(frozen=True)
class GeneratedSegment:
    source_text: str
    source_lang: str
    target_lang: str
    register: str
    difficulty_level: int
    domain: str  # the primary topic (first selected) for picker compatibility


@dataclass(frozen=True)
class GenerationResult:
    scenario_summary: str
    segments: tuple[GeneratedSegment, ...]
    prompt_template_hash: str
    prompt_vars_hash: str


def _hash_inputs(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()[:16]


def _template_variables(params: GenerateParams) -> dict:
    band = LEVEL_BANDS[params.user_level]
    duration_spec = DURATION_BANDS[params.duration]
    topic_csv = ", ".join(params.topics)
    src, tgt = params.direction.split("-")
    return {
        "n": params.n,
        "topic_csv": topic_csv,
        "topic_descriptions": [TOPIC_DESCRIPTIONS[t] for t in params.topics],
        "user_level": params.user_level,
        "user_level_label": band.label,
        "internal_min": band.internal_range[0],
        "internal_max": band.internal_range[1],
        "internal_peak": band.peak,
        "difficulty_description": band.description,
        "duration_label": duration_spec.band,
        "target_seconds": duration_spec.target_seconds,
        "approx_words": duration_spec.approx_words,
        "direction_label": _DIRECTION_LABEL[params.direction],
        "source_lang": src,
        "target_lang": tgt,
        "source_lang_long": _SOURCE_LANG_LONG[params.direction],
        "current_context": params.current_context or "",
    }


def _validate_segments(raw: list[dict], expected_n: int) -> list[dict]:
    if not isinstance(raw, list):
        raise ValueError("emit_segments.segments must be a list")
    if len(raw) != expected_n:
        raise ValueError(f"expected {expected_n} segments, got {len(raw)}")
    cleaned = []
    for i, seg in enumerate(raw):
        if not isinstance(seg, dict):
            raise ValueError(f"segment {i} is not an object")
        if not isinstance(seg.get("source_text"), str) or not seg["source_text"].strip():
            raise ValueError(f"segment {i} missing source_text")
        if not isinstance(seg.get("register"), str):
            raise ValueError(f"segment {i} missing register")
        if not isinstance(seg.get("difficulty_level"), int):
            raise ValueError(f"segment {i} missing difficulty_level")
        cleaned.append(seg)
    return cleaned


def _mock_generation(params: GenerateParams) -> GenerationResult:
    """Deterministic fake result for `USE_MOCKS=1` dev runs.

    Produces `params.n` semi-coherent template phrases referencing the
    requested topic + scenario so downstream wiring (TTS, persistence,
    picker) can be exercised without an Anthropic API key.
    """
    src, tgt = params.direction.split("-")
    primary_topic = params.topics[0]
    levels = sample_internal_levels(params.user_level, params.n)
    scenario = (
        f"Mock {primary_topic} scenario for {_DIRECTION_LABEL[params.direction]} "
        f"({params.duration} length)."
    )
    if src == "en":
        body = (
            "We have an update on the {topic} situation as of zero-six-hundred"
        )
    else:
        body = "{topic} 상황에 대한 최신 보고입니다"
    segs = tuple(
        GeneratedSegment(
            source_text=f"{body.format(topic=primary_topic)} — phrase {i + 1} of {params.n}.",
            source_lang=src,
            target_lang=tgt,
            register="formal-military",
            difficulty_level=levels[i],
            domain=primary_topic,
        )
        for i in range(params.n)
    )
    variables = _template_variables(params)
    rendered = render_template("generate_segments", variables)
    template_hash = _hash_inputs(rendered.system, rendered.user)
    vars_hash = _hash_inputs(
        ",".join(sorted(params.topics)),
        str(params.user_level),
        params.duration,
        params.direction,
        params.current_context or "",
    )
    return GenerationResult(
        scenario_summary=scenario,
        segments=segs,
        prompt_template_hash=template_hash,
        prompt_vars_hash=vars_hash,
    )


def generate_segments(params: GenerateParams) -> GenerationResult:
    """Call the LLM and return a coherent set of phrases.

    Pure orchestration: no DB writes, no audio. The caller decides what
    to do with the result (persist, generate audio, return to user).
    Honours `USE_MOCKS=1` to skip the real Anthropic call.
    """
    if not params.topics:
        raise ValueError("at least one topic is required")
    # Default OPT-IN with "0": every other call site reads USE_MOCKS as
    # opt-in (mock only when explicitly requested). The old default of
    # "1" silently served fake phrases on any deployment where the env
    # var happened to be unset.
    if os.getenv("USE_MOCKS", "0") == "1":
        log.info("generate_segments: USE_MOCKS=1, returning mock result")
        return _mock_generation(params)
    variables = _template_variables(params)
    # M14 fix: run_template now returns `(result, rendered_call)` so we
    # don't have to re-render the template a second time just to compute
    # the prompt-version hash.
    tool_out, rendered = run_template(
        "generate_segments", variables, spend_kind="claude_generation"
    )
    raw_segments = tool_out.get("segments", [])
    cleaned = _validate_segments(raw_segments, params.n)
    src, tgt = params.direction.split("-")
    # TODO: multi-topic sets are tagged with the first topic for picker
    # compatibility; the per-segment domain is therefore lossy.
    primary_topic = params.topics[0]
    segments = tuple(
        GeneratedSegment(
            source_text=s["source_text"].strip(),
            source_lang=src,
            target_lang=tgt,
            register=s["register"],
            difficulty_level=s["difficulty_level"],
            domain=primary_topic,
        )
        for s in cleaned
    )
    template_hash = _hash_inputs(rendered.system, rendered.user)
    vars_hash = _hash_inputs(
        ",".join(sorted(params.topics)),
        str(params.user_level),
        params.duration,
        params.direction,
        params.current_context or "",
    )
    return GenerationResult(
        scenario_summary=str(tool_out.get("scenario_summary", "")),
        segments=segments,
        prompt_template_hash=template_hash,
        prompt_vars_hash=vars_hash,
    )
