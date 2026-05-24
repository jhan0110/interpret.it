"""Memorization evaluation module: Claude-driven recall scoring.

Mirrors the structure of ``evaluation/evaluate.py`` but for the memorization
session mode, where the learner is asked to recall a source phrase verbatim
(or near-verbatim) in the source language rather than render an interpretation.
The "reference" is the source text itself; quality is measured as
how many key information units the learner recovered.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from uuid import UUID

from ..contracts.models import FollowupExercise, KeyPoint, SemanticResult
from ..llm.client import structured_generate

log = logging.getLogger(__name__)

_KEYPOINTS_CACHE_TTL = 604800  # 7 days


_EXTRACT_TOOL = {
    "name": "extract_key_points",
    "description": "Extract the canonical key information units from a source phrase.",
    "input_schema": {
        "type": "object",
        "properties": {
            "key_points": {
                "type": "array",
                "minItems": 3,
                "maxItems": 6,
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "A short canonical phrase in the source language naming this information unit.",
                        },
                        "importance": {
                            "type": "string",
                            "enum": ["primary", "secondary"],
                            "description": "primary = must-recall for the message to land; secondary = nice-to-have detail.",
                        },
                    },
                    "required": ["text", "importance"],
                },
            },
        },
        "required": ["key_points"],
    },
}


_EXTRACT_SYSTEM_PROMPT = """\
You break a short source phrase into its key information units for a memorization drill.
The learner will be scored on how many of these units they can recall verbatim.

Return 3–6 key points covering every load-bearing piece of information: named entities,
quantities, time markers, actions, and any modifiers that change the meaning.

Classify each point:
- **primary** — the message fails without it (the main subject/verb/object, headline
  quantities, named entities, decisive time markers).
- **secondary** — supporting detail (descriptive modifiers, secondary clauses, soft
  qualifiers). A learner who skips secondary points still conveys the gist.

Each `text` field should be a short canonical phrase in {source_lang} — the smallest
chunk a coach would point at and say "recall this exactly." Do not paraphrase into the
other language. Do not summarize the whole phrase as one point.

Respond only by calling the extract_key_points tool.
"""


_EVAL_TOOL = {
    "name": "emit_memorization_evaluation",
    "description": "Score how well the learner recalled the source phrase.",
    "input_schema": {
        "type": "object",
        "properties": {
            "key_points": {
                "type": "array",
                "description": "Echo each key point from the input with a recall verdict.",
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "The key point text (echo verbatim from input).",
                        },
                        "recalled": {
                            "type": "boolean",
                            "description": "True if the learner conveyed this unit, even in slightly different wording.",
                        },
                    },
                    "required": ["text", "recalled"],
                },
            },
            "verbatim_bonus": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 0.15,
                "description": "Bonus on top of the recall score for how close the rendition is to verbatim. 0.15 = essentially word-for-word; 0.0 = paraphrased.",
            },
            "feedback_text": {
                "type": "string",
                "description": "3-5 sentences naming what the learner recalled well and what they missed.",
            },
            "followup_exercise": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["repeat", "rephrase", "drill_term", "contextual_qa"],
                    },
                    "prompt_text": {
                        "type": "string",
                        "description": "The exercise prompt the learner should respond to.",
                    },
                },
                "required": ["type", "prompt_text"],
            },
        },
        "required": ["key_points", "verbatim_bonus", "feedback_text", "followup_exercise"],
    },
}


_EVAL_SYSTEM_PROMPT = """\
You are a memorization coach, NOT an interpretation evaluator. The learner heard a short
phrase in {source_lang} and is repeating it back in the same language from memory.
Score recall, not translation quality and not interpretation craft.

## Scoring philosophy

Recall is the only thing that matters. For each key point you were given, decide whether
the learner conveyed that unit — exact wording is not required as long as the
information is unambiguously present. Treat near-synonyms, minor word-order
rearrangement, and small grammatical drift as recalled.

Verbatim bonus is separate. Award up to 0.15 only when the learner's rendition is
essentially the source phrase word-for-word. Award 0.0 when they captured the meaning
but used substantially different wording. Partial verbatim (a few exact spans embedded
in paraphrase) earns a value in between.

## What counts as recalled

- A primary point is recalled when the named entity / quantity / action / time marker
  is present. If the learner says "around 50" for "exactly 47", that primary point is
  NOT recalled — primary points include the precision.
- A secondary point is recalled when its gist is present, even loosely.
- Silence or unrelated content for a unit = not recalled.

Echo every key point you were given (same `text` strings, same order) with a boolean
recall verdict. Then write 3-5 sentences of feedback naming the specific units the
learner missed and praising what they captured. Recommend a follow-up that drills the
weakest unit.

Source language: {source_lang}. Difficulty level: {difficulty_level}/10.

Respond only by calling the emit_memorization_evaluation tool.
"""


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379/0")


def _get_redis():
    """Return a sync Redis client, lazily importing the module.

    Returns ``None`` when the redis package is unavailable (e.g. unit tests
    that monkeypatch this function).
    """
    try:
        import redis  # type: ignore
    except Exception:
        return None
    return redis.Redis.from_url(_redis_url(), decode_responses=True)


def extract_key_points(
    segment_id: UUID,
    source_text: str,
    source_lang: str,
) -> list[KeyPoint]:
    """Extract 3–6 key information units from ``source_text``.

    Cached in Redis at ``keypoints:<segment_id>`` for 7 days. The returned
    list always has ``recalled=False``; that flag is filled in by
    ``evaluate_memorization`` after the learner attempts the segment.
    """
    cache_key = f"keypoints:{segment_id}"
    client = _get_redis()
    cached_raw: str | None = None
    if client is not None:
        try:
            cached_raw = client.get(cache_key)
        except Exception:
            log.warning("keypoints cache read failed for segment=%s", segment_id)
            cached_raw = None

    if cached_raw is not None:
        try:
            items = json.loads(cached_raw)
            return [
                KeyPoint(text=item["text"], importance=item["importance"], recalled=False)
                for item in items
            ]
        except Exception:
            log.warning("keypoints cache deserialization failed for segment=%s", segment_id)

    log.info("[keypoints.claude.begin] segment=%s len=%d", segment_id, len(source_text))
    t0 = time.monotonic()
    inp = structured_generate(
        system=_EXTRACT_SYSTEM_PROMPT.format(source_lang=source_lang),
        user=f"Source phrase ({source_lang}):\n\n{source_text}",
        tool=_EXTRACT_TOOL,
        max_tokens=1024,
    )
    claude_ms = int((time.monotonic() - t0) * 1000)
    log.info(
        "[keypoints.claude.done] segment=%s n=%d took=%dms",
        segment_id,
        len(inp["key_points"]),
        claude_ms,
    )

    items = [{"text": kp["text"], "importance": kp["importance"]} for kp in inp["key_points"]]

    if client is not None:
        try:
            client.set(cache_key, json.dumps(items, ensure_ascii=False), ex=_KEYPOINTS_CACHE_TTL)
        except Exception:
            log.warning("keypoints cache write failed for segment=%s", segment_id)

    return [
        KeyPoint(text=item["text"], importance=item["importance"], recalled=False)
        for item in items
    ]


def _compute_overall_score(
    key_points: list[KeyPoint],
    verbatim_bonus: float,
) -> float:
    units_recovered = 0.0
    units_total = 0.0
    for kp in key_points:
        weight = 1.0 if kp.importance == "primary" else 0.5
        units_total += weight
        if kp.recalled:
            units_recovered += weight
    if units_total == 0.0:
        recall_ratio = 0.0
    else:
        recall_ratio = units_recovered / units_total
    recall_score = 0.85 * recall_ratio
    return min(1.0, recall_score + max(0.0, min(0.15, verbatim_bonus)))


def evaluate_memorization(
    attempt_id: UUID,
    segment_id: UUID,
    source_text: str,
    source_lang: str,
    target_lang: str,
    register: str,
    domain: str,
    difficulty_level: int,
    user_transcript: str,
    feedback_audio_path: str,
    followup_audio_path: str,
    start_time: datetime,
) -> SemanticResult:
    """Evaluate a memorization attempt and return a ``SemanticResult``.

    For memorization the "reference" is the source text itself: the learner was
    asked to memorize the phrase and repeat it back, so we score how many of
    the extracted key points they recovered.
    """
    eval_t0 = time.monotonic()
    log.info(
        "[memorize.begin] attempt=%s segment=%s transcript_len=%d source_len=%d",
        attempt_id,
        segment_id,
        len(user_transcript),
        len(source_text),
    )

    key_points = extract_key_points(segment_id, source_text, source_lang)

    system = _EVAL_SYSTEM_PROMPT.format(
        source_lang=source_lang,
        difficulty_level=difficulty_level,
    )

    keypoints_listing = "\n".join(
        f"- ({kp.importance}) {kp.text}" for kp in key_points
    )
    user_message = f"""\
Source phrase ({source_lang}):
{source_text}

Key points to check (echo every `text` back in your tool call):
{keypoints_listing}

Learner's recall ({source_lang}):
{user_transcript}
"""

    log.info("[memorize.claude.begin] attempt=%s", attempt_id)
    t_claude = time.monotonic()
    inp = structured_generate(
        system=system,
        user=user_message,
        tool=_EVAL_TOOL,
        max_tokens=2048,
    )
    claude_ms = int((time.monotonic() - t_claude) * 1000)
    log.info("[memorize.claude.done] attempt=%s took=%dms", attempt_id, claude_ms)

    recall_by_text: dict[str, bool] = {
        kp["text"]: bool(kp["recalled"]) for kp in inp["key_points"]
    }
    populated = [
        KeyPoint(
            text=kp.text,
            importance=kp.importance,
            recalled=recall_by_text.get(kp.text, False),
        )
        for kp in key_points
    ]

    verbatim_bonus = float(inp.get("verbatim_bonus", 0.0))
    overall_score = _compute_overall_score(populated, verbatim_bonus)

    followup_raw = inp["followup_exercise"]
    followup = FollowupExercise(
        type=followup_raw["type"],
        prompt_text=followup_raw["prompt_text"],
        prompt_audio_path=followup_audio_path,
    )

    now = datetime.now(timezone.utc)
    latency_ms = int((now - start_time).total_seconds() * 1000)

    result = SemanticResult(
        attempt_id=attempt_id,
        mode="memorization",
        transcript=user_transcript,
        reference_translation=source_text,
        acceptable_paraphrases=[],
        errors=[],
        key_points=populated,
        overall_score=overall_score,
        feedback_text=inp["feedback_text"],
        feedback_audio_path=feedback_audio_path,
        followup_exercise=followup,
        computed_at=now,
        latency_ms=latency_ms,
    )
    total_eval_ms = int((time.monotonic() - eval_t0) * 1000)
    log.info(
        "[memorize.complete] attempt=%s score=%.3f recalled=%d/%d took=%dms",
        attempt_id,
        result.overall_score,
        sum(1 for kp in populated if kp.recalled),
        len(populated),
        total_eval_ms,
    )
    return result
