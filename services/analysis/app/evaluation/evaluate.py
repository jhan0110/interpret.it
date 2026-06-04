"""Semantic evaluation module: Claude Sonnet with tool_use structured output."""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from uuid import UUID

from ..contracts.models import FollowupExercise, SemanticResult, SemanticResultError
from ..llm.client import structured_generate
from ..reference.generate import ReferenceBundle

log = logging.getLogger(__name__)

# Scoring runs on a faster model than reference/generation. Haiku 4.5 was
# measured at ~2x Sonnet's eval speed (13.7s -> 6.1s median) with calibration
# preserved across self-correction, near-perfect, major/moderate omission,
# and register-slip cases — the difference that pulls the whole analysis
# under 15s. Reference (the scoring anchor) stays on Sonnet. Override with
# EVAL_MODEL to revert: EVAL_MODEL=anthropic/claude-sonnet-4-6.
_DEFAULT_EVAL_MODEL = "anthropic/claude-haiku-4-5"


def _eval_model() -> str:
    return os.getenv("EVAL_MODEL", _DEFAULT_EVAL_MODEL)


_EVAL_TOOL = {
    "name": "emit_evaluation",
    "description": "Emit the structured semantic evaluation of the user's interpretation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "errors": {
                "type": "array",
                "description": "List of identified interpretation errors.",
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": [
                                "semantic_drift",
                                "lexical_gap",
                                "register_error",
                                "omission",
                                "tense_shift",
                                "precision_loss",
                            ],
                        },
                        "source_span": {
                            "type": "string",
                            "description": "The portion of source text that was mis-handled.",
                        },
                        "user_span": {
                            "type": ["string", "null"],
                            "description": "The user's corresponding output span, or null if omitted entirely.",
                        },
                        "severity": {"type": "string", "enum": ["minor", "moderate", "critical"]},
                        "explanation": {
                            "type": "string",
                            "description": "Clear pedagogical explanation of the error, written in English.",
                        },
                    },
                    "required": ["type", "source_span", "user_span", "severity", "explanation"],
                },
            },
            "overall_score": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Holistic quality score from 0.0 (failed) to 1.0 (perfect).",
            },
            "feedback_text": {
                "type": "string",
                "description": "3-5 sentence pedagogical feedback addressing the most important issues. Written in English.",
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
        "required": ["errors", "overall_score", "feedback_text", "followup_exercise"],
    },
}

_SYSTEM_PROMPT = """\
You are an expert interpretation trainer. Evaluate the learner's interpretation of the
provided source text against the reference translation and acceptable paraphrases.

## Comprehension-first checkpoint (apply BEFORE scoring)

Before assigning any score, ask yourself two questions:

1. **Would a listener of the target language walk away with the same essential
   understanding of the situation, action, or fact?** If yes, the floor is 0.70.
2. **Are the people, places, times, numbers, and outcomes the listener cares about
   all correctly identified?** If yes, the floor is 0.75.

Only after answering "yes" to both should supplemental imperfections pull the score
DOWN from that floor — and never by more than 0.20 cumulatively.

A learner who heard "sudden onset of chest tightness" and rendered it as
"complained of chest compressions or tightness" passes both checkpoints: the listener
understands the soldier has chest discomfort during training. The misfire on
"compressions" is mitigated by the immediate self-correction to "tightness", the
missing "sudden onset" is a minor temporal nuance. Target score: 0.72–0.78.

## Scoring philosophy

Content accuracy is the primary criterion and carries roughly 80% of the weight.
A learner who conveys all the key information — even imperfectly worded — deserves a
score in the 0.75–0.85 range before supplemental factors are considered.

Supplemental factors (register, tense precision, lexical choices) together account for
the remaining ~20%. Penalise them only when the deviation materially harms comprehension
or professional suitability. Minor phrasing differences, stylistic variation, and
near-synonyms are not errors.

### Self-correction policy

When a learner offers an incorrect term followed by the correct term using "or",
"I mean", "actually", "no, ...", or a similar repair marker, treat the FINAL
chosen term as the interpretation. Do not penalize for the false start unless the
self-correction itself is wrong. ("compressions or tightness" → "tightness"
counts as a successful self-correction; do not flag "compressions" as a lexical
error.)

### Near-synonym policy

Treat domain-equivalent verbs and nouns as fully interchangeable unless the
distinction is operationally meaningful:
- reported / complained of / stated / described / mentioned — equivalent
- noted / observed / saw — equivalent
- intercepted / received / picked up — equivalent
Only flag word choice when the substitution changes operational meaning
(e.g. "destroyed" vs "damaged", "killed" vs "wounded", "confirmed" vs "suspected").

Score anchors:
- **0.85–1.0** — All key content conveyed; supplemental factors mostly correct. 1.0 is
  reserved for interpretations that are both complete and polished — it does NOT mean
  word-for-word match with the reference. A natural, fluent rendition that captures all
  meaning and sounds professional is a 1.0.
- **0.70–0.84** — All or nearly all key content present; one or two supplemental
  weaknesses (register slip, missed technical term, minor tense inconsistency, omitted
  temporal qualifier like "sudden" or "shortly after"). A self-corrected lexical
  stumble belongs HERE, not lower.
- **0.50–0.69** — Most content present but a meaningful omission or semantic drift that
  a listener would notice. Use this band when the listener would walk away with a
  partially wrong impression of WHO, WHAT, or WHEN.
- **0.30–0.49** — Significant content missing or substantially altered; meaning partially
  lost. Listener would form a noticeably incorrect picture of the event.
- **0.00–0.29** — Core meaning not conveyed; major structural or content failure.
  Listener would not understand what happened.

## Dimensions to analyze

**Primary (content — ~80% weight):**
- **Omissions** — Significant information from the source that the learner dropped
  entirely. Only flag items a listener would miss; incidental detail is not an omission.
  Temporal qualifiers ("sudden", "briefly", "shortly") are MINOR omissions: flag with
  `severity: "minor"` and a single-bullet explanation.
- **Semantic drift** — Places where the learner's wording changes the meaning in a way
  that could mislead. A self-corrected stumble is NOT semantic drift.

**Supplemental (~20% weight combined):**
- **Register adherence** — Does the learner match the required register ({register})?
  Flag only clear mismatches (casual language in a formal briefing, etc.).
- **Key-term coverage** — Are domain-critical terms ({domain}) accurately rendered?
- **Temporal precision** — Are time markers and sequences preserved?
- **Tense shifts** — Unexpected grammatical tense changes that affect meaning.
- **Lexical gaps** — Missing or incorrect technical terms that impede understanding.
  Apply the self-correction and near-synonym policies above before flagging.

Treat the acceptable paraphrases as fully equivalent to the reference translation —
a learner who matches any paraphrase closely should receive the same credit as one who
matches the reference.

Source language: {source_lang}. Target language: {target_lang}.
Difficulty level: {difficulty_level}/10. At lower difficulty levels, be more forgiving
of supplemental imperfections; reserve critical-severity flags for high difficulty (7+).

Be pedagogically specific. Point to exact spans. Recommend a follow-up exercise
that targets the most critical weakness.

## Language of feedback

Write ALL feedback prose in English — `feedback_text`, every error
`explanation`, and the follow-up `prompt_text` — regardless of the source or
target language of the exercise. You may quote exact words or spans from the
source or the learner's interpretation in their original language, but every
explanation and instruction you write must be in English.

Respond only by calling the emit_evaluation tool.
"""


def evaluate(
    attempt_id: UUID,
    source_text: str,
    source_lang: str,
    target_lang: str,
    register: str,
    domain: str,
    difficulty_level: int,
    user_transcript: str,
    reference: ReferenceBundle,
    feedback_audio_path: str,
    followup_audio_path: str,
    start_time: datetime,
) -> SemanticResult:
    """Call Claude to produce a SemanticResult for the user's interpretation.

    The feedback_audio_path and followup_audio_path are MinIO keys for TTS audio
    that must be generated before calling this function.
    """
    eval_t0 = time.monotonic()
    log.info(
        "[eval.begin] attempt=%s transcript_len=%d reference_len=%d",
        attempt_id,
        len(user_transcript),
        len(reference.canonical),
    )

    # `str.format` was historically a latent injection vector: any
    # future use of user-supplied content as a format argument that
    # contains literal `{}` would raise. Switch to %-substitution via
    # an explicit replace so the prompt template is mechanically safe
    # against that class of bug. Today the substituted values are all
    # enum-constrained but the discipline is worth keeping.
    system = (
        _SYSTEM_PROMPT.replace("{register}", str(register))
        .replace("{domain}", str(domain))
        .replace("{source_lang}", str(source_lang))
        .replace("{target_lang}", str(target_lang))
        .replace("{difficulty_level}", str(difficulty_level))
    )

    user_message = f"""\
Source text ({source_lang}):
{source_text}

Reference translation:
{reference.canonical}

Acceptable paraphrases:
{chr(10).join(f"- {p}" for p in reference.paraphrases)}

Learner's interpretation ({target_lang}):
{user_transcript}
"""

    log.info("[eval.claude.begin] attempt=%s", attempt_id)
    t_claude = time.monotonic()
    inp = structured_generate(
        system=system,
        user=user_message,
        tool=_EVAL_TOOL,
        model=_eval_model(),
        max_tokens=2048,
    )
    claude_ms = int((time.monotonic() - t_claude) * 1000)
    log.info("[eval.claude.done] attempt=%s took=%dms", attempt_id, claude_ms)

    now = datetime.now(timezone.utc)
    latency_ms = int((now - start_time).total_seconds() * 1000)

    errors = [
        SemanticResultError(
            type=e["type"],
            source_span=e["source_span"],
            user_span=e.get("user_span"),
            severity=e["severity"],
            explanation=e["explanation"],
        )
        for e in (inp.get("errors") or [])
    ]
    followup_raw = inp.get("followup_exercise") or {}
    followup = FollowupExercise(
        type=followup_raw.get("type", "repeat"),
        prompt_text=followup_raw.get("prompt_text", ""),
        prompt_audio_path=followup_audio_path,
    )
    try:
        overall_score = float(inp.get("overall_score", 0.0) or 0.0)
    except (TypeError, ValueError):
        log.warning("[eval.bad_score] attempt=%s raw=%r", attempt_id, inp.get("overall_score"))
        overall_score = 0.0
    result = SemanticResult(
        attempt_id=attempt_id,
        source_text=source_text,
        transcript=user_transcript,
        reference_translation=reference.canonical,
        acceptable_paraphrases=reference.paraphrases,
        errors=errors,
        overall_score=overall_score,
        feedback_text=inp.get("feedback_text", ""),
        feedback_audio_path=feedback_audio_path,
        followup_exercise=followup,
        computed_at=now,
        latency_ms=latency_ms,
    )
    total_eval_ms = int((time.monotonic() - eval_t0) * 1000)
    log.info("[eval.complete] attempt=%s total_took=%dms", attempt_id, total_eval_ms)
    return result
