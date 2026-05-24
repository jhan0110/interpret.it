"""Semantic evaluation module: Claude Sonnet with tool_use structured output."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from uuid import UUID

from ..contracts.models import FollowupExercise, SemanticResult, SemanticResultError
from ..llm.client import structured_generate
from ..reference.generate import ReferenceBundle

log = logging.getLogger(__name__)


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
                            "description": "Clear pedagogical explanation of the error.",
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
                "description": "3-5 sentence pedagogical feedback addressing the most important issues.",
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

## Scoring philosophy

Content accuracy is the primary criterion and carries roughly 80% of the weight.
A learner who conveys all the key information — even imperfectly worded — deserves a
score in the 0.75–0.85 range before supplemental factors are considered.

Supplemental factors (register, tense precision, lexical choices) together account for
the remaining ~20%. Penalise them only when the deviation materially harms comprehension
or professional suitability. Minor phrasing differences, stylistic variation, and
near-synonyms are not errors.

Score anchors:
- **0.85–1.0** — All key content conveyed; supplemental factors mostly correct. 1.0 is
  reserved for interpretations that are both complete and polished — it does NOT mean
  word-for-word match with the reference. A natural, fluent rendition that captures all
  meaning and sounds professional is a 1.0.
- **0.70–0.84** — All or nearly all key content present; one or two supplemental
  weaknesses (register slip, missed technical term, minor tense inconsistency).
- **0.50–0.69** — Most content present but a meaningful omission or semantic drift that
  a listener would notice.
- **0.30–0.49** — Significant content missing or substantially altered; meaning partially
  lost.
- **0.00–0.29** — Core meaning not conveyed; major structural or content failure.

## Dimensions to analyze

**Primary (content — ~80% weight):**
- **Omissions** — Significant information from the source that the learner dropped
  entirely. Only flag items a listener would miss; incidental detail is not an omission.
- **Semantic drift** — Places where the learner's wording changes the meaning in a way
  that could mislead.

**Supplemental (~20% weight combined):**
- **Register adherence** — Does the learner match the required register ({register})?
  Flag only clear mismatches (casual language in a formal briefing, etc.).
- **Key-term coverage** — Are domain-critical terms ({domain}) accurately rendered?
- **Temporal precision** — Are time markers and sequences preserved?
- **Tense shifts** — Unexpected grammatical tense changes that affect meaning.
- **Lexical gaps** — Missing or incorrect technical terms that impede understanding.

Treat the acceptable paraphrases as fully equivalent to the reference translation —
a learner who matches any paraphrase closely should receive the same credit as one who
matches the reference.

Source language: {source_lang}. Target language: {target_lang}.
Difficulty level: {difficulty_level}/10. At lower difficulty levels, be more forgiving
of supplemental imperfections; reserve critical-severity flags for high difficulty (7+).

Be pedagogically specific. Point to exact spans. Recommend a follow-up exercise
that targets the most critical weakness.

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

    system = _SYSTEM_PROMPT.format(
        register=register,
        domain=domain,
        source_lang=source_lang,
        target_lang=target_lang,
        difficulty_level=difficulty_level,
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
        for e in inp["errors"]
    ]
    followup_raw = inp["followup_exercise"]
    followup = FollowupExercise(
        type=followup_raw["type"],
        prompt_text=followup_raw["prompt_text"],
        prompt_audio_path=followup_audio_path,
    )
    result = SemanticResult(
        attempt_id=attempt_id,
        source_text=source_text,
        transcript=user_transcript,
        reference_translation=reference.canonical,
        acceptable_paraphrases=reference.paraphrases,
        errors=errors,
        overall_score=float(inp["overall_score"]),
        feedback_text=inp["feedback_text"],
        feedback_audio_path=feedback_audio_path,
        followup_exercise=followup,
        computed_at=now,
        latency_ms=latency_ms,
    )
    total_eval_ms = int((time.monotonic() - eval_t0) * 1000)
    log.info("[eval.complete] attempt=%s total_took=%dms", attempt_id, total_eval_ms)
    return result
