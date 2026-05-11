"""Semantic evaluation module: Claude Sonnet with tool_use structured output."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from ..contracts.models import FollowupExercise, SemanticResult, SemanticResultError
from ..llm.client import structured_generate
from ..reference.generate import ReferenceBundle


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

Analyze the following dimensions systematically:
1. **Register adherence** — Does the learner match the required register ({register})?
2. **Key-term coverage** — Are domain-critical terms ({domain}) accurately rendered?
3. **Temporal precision** — Are time markers, sequences, and tenses preserved correctly?
4. **Omissions** — What significant content from the source was dropped?
5. **Tense shifts** — Are there unexpected changes in grammatical tense?
6. **Lexical gaps** — Are there missing or incorrect technical/specialized terms?
7. **Overall quality** — Holistic score from 0.0 to 1.0.

Source language: {source_lang}. Target language: {target_lang}.
Difficulty level: {difficulty_level}/10.

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

    inp = structured_generate(
        system=system,
        user=user_message,
        tool=_EVAL_TOOL,
        max_tokens=2048,
    )

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
    return SemanticResult(
        attempt_id=attempt_id,
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
