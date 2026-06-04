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

Direction = Literal[
    # Cross-language directions (interpretation mode).
    "en-ko", "ko-en",
    "en-es", "es-en",
    "ko-es", "es-ko",
    "en-zh", "zh-en",
    "ko-zh", "zh-ko",
    "es-zh", "zh-es",
    # Same-language directions (memorization mode — source == target).
    "en-en", "ko-ko", "es-es", "zh-zh",
]

_LANG_LONG_NAMES: dict[str, str] = {
    "en": "English",
    "ko": "Korean",
    "es": "Spanish",
    "zh": "Chinese",
}


def _direction_label(direction: str) -> str:
    src, tgt = direction.split("-")
    if src == tgt:
        # Memorization mode — render as just the single language so
        # the generation prompt doesn't read like "English → English".
        return _LANG_LONG_NAMES.get(src, src)
    return f"{_LANG_LONG_NAMES.get(src, src)} → {_LANG_LONG_NAMES.get(tgt, tgt)}"


def _source_lang_long(direction: str) -> str:
    src = direction.split("-")[0]
    return _LANG_LONG_NAMES.get(src, src)


# Backward-compat dicts so any external import keeps working. New code
# should use the helpers above. List includes the same-language
# directions used by memorization mode (en-en, ko-ko, es-es).
_ALL_DIRECTIONS: tuple[str, ...] = (
    "en-ko", "ko-en",
    "en-es", "es-en",
    "ko-es", "es-ko",
    "en-zh", "zh-en",
    "ko-zh", "zh-ko",
    "es-zh", "zh-es",
    "en-en", "ko-ko", "es-es", "zh-zh",
)
_DIRECTION_LABEL: dict[str, str] = {d: _direction_label(d) for d in _ALL_DIRECTIONS}
_SOURCE_LANG_LONG: dict[str, str] = {d: _source_lang_long(d) for d in _ALL_DIRECTIONS}


@dataclass(frozen=True)
class GenerateParams:
    topics: tuple[Topic, ...]
    user_level: UserLevel
    duration: DurationBand
    direction: Direction
    n: int = 5
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


def compute_generation_keys(params: GenerateParams) -> tuple[str, str]:
    """Return ``(prompt_template_hash, prompt_vars_hash)`` — the shared-pool key.

    Renders the template (cheap, **no LLM**) so ``template_hash`` captures
    the prompt text, every rendered variable (domain/language guidance,
    difficulty band, target length) AND ``n`` (the tool schema renders
    ``minItems/maxItems: {{ n }}``). ``vars_hash`` captures the raw params.

    Single source of truth: both ``generate_segments`` (recording a set)
    and the pool-reuse check call this, so the recorded key and the
    lookup key can never drift (R22). The extra render here is microseconds
    next to the LLM call it gates.
    """
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
    return template_hash, vars_hash


def _domain_guidance(topics: tuple[str, ...], internal_max: int) -> str:
    """Per-domain framing overrides injected into the generation prompt.

    The platform's default register is military; `medical` is the
    deliberate exception — it must read as a CIVILIAN clinical domain
    with no combat/field-medicine framing. Difficulty-scaled: at the
    higher bands, ask for the clinical jargon a clinician would meet.
    """
    notes: list[str] = []
    if "medical" in topics:
        note = (
            "MEDICAL is a CIVILIAN clinical domain — patients, doctors, "
            "nurses, hospitals, outpatient and family clinics. Do NOT use "
            "any military, combat, battlefield, MEDEVAC, mass-casualty, "
            "triage-under-fire, or field-medicine framing; no ranks, units, "
            "deployments, or command language. Use informal or operational "
            "register: natural clinician–patient and clinician–clinician "
            "dialogue, not formal-military."
        )
        if internal_max >= 7:
            note += (
                " At this difficulty, weave in the realistic clinical jargon "
                "and case detail encountered at a clinic — presenting "
                "complaint, history of present illness, differential "
                "diagnosis, medication names and dosages, lab values, and "
                "relevant specialist terminology."
            )
        notes.append(note)
    return "\n".join(notes)


def _language_guidance(source_lang: str) -> str:
    """Per-source-language tone overrides (single line, prompt-injected).

    Chinese source material defaulted to stiff, bureaucratic prose; the
    learner hears and interprets it, so it should sound like real speech.
    """
    if source_lang == "zh":
        return (
            "The source phrases are spoken Mandarin the learner will hear and "
            "interpret — write NATURAL, CONVERSATIONAL spoken Mandarin with "
            "everyday phrasing, natural connectors, and idiomatic rhythm, not "
            "stiff written or bureaucratic prose. Avoid translationese and "
            "overly formal set phrases; make it sound like how the scenario's "
            "speakers really talk."
        )
    return ""


# Generation runs on a faster model than the default. Haiku 4.5 was
# measured at ~2x Sonnet's generation speed (9.3s -> 4.3s) with cohesion,
# difficulty laddering, conversational-Chinese, and civilian-medical
# quality preserved across en/ko/zh. Override with GEN_MODEL to revert:
# GEN_MODEL=anthropic/claude-sonnet-4-6.
_DEFAULT_GEN_MODEL = "anthropic/claude-haiku-4-5"


def _gen_model() -> str:
    return os.getenv("GEN_MODEL", _DEFAULT_GEN_MODEL)


def _template_variables(params: GenerateParams) -> dict:
    band = LEVEL_BANDS[params.user_level]
    duration_spec = DURATION_BANDS[params.duration]
    topic_csv = ", ".join(params.topics)
    src, tgt = params.direction.split("-")
    return {
        "gen_model": _gen_model(),
        "domain_guidance": _domain_guidance(params.topics, band.internal_range[1]),
        "language_guidance": _language_guidance(src),
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
    template_hash, vars_hash = compute_generation_keys(params)
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
    tool_out, _rendered = run_template(
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
    template_hash, vars_hash = compute_generation_keys(params)
    return GenerationResult(
        scenario_summary=str(tool_out.get("scenario_summary", "")),
        segments=segments,
        prompt_template_hash=template_hash,
        prompt_vars_hash=vars_hash,
    )
