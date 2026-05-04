"""Mock handlers returning contract-conformant SemanticResult fixtures.

Used when USE_MOCKS=1 so that Agent 2 (frontend) can integrate immediately
without live API keys. Fixtures are keyed by segment_id to allow deterministic
UI testing across different scenario types.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from ..contracts.models import FollowupExercise, SemanticResult, SemanticResultError

_DEFAULT_SEGMENT_ID = "00000000-0000-0000-0000-000000000000"

_FIXTURES: dict[str, dict] = {
    # Good performance — high score, no critical errors
    "good": {
        "transcript": "The convoy will depart at 0600 hours from the northern checkpoint.",
        "reference_translation": "The convoy will depart at 0600 hours from the northern checkpoint.",
        "acceptable_paraphrases": [
            "The convoy leaves at 6 AM from the north checkpoint.",
            "The convoy departs from the northern checkpoint at 0600.",
        ],
        "errors": [],
        "overall_score": 0.92,
        "feedback_text": (
            "Excellent interpretation. You accurately conveyed the departure time and location "
            "with proper military register. Your pacing was clear and your terminology precise."
        ),
        "followup_exercise": {
            "type": "rephrase",
            "prompt_text": "Now try rephrasing this in a formal-diplomatic register instead.",
        },
    },
    # Moderate performance — some lexical gaps
    "moderate": {
        "transcript": "The group will leave at six from the checkpoint in the north.",
        "reference_translation": "The convoy will depart at 0600 hours from the northern checkpoint.",
        "acceptable_paraphrases": [
            "The convoy leaves at 6 AM from the north checkpoint.",
        ],
        "errors": [
            {
                "type": "lexical_gap",
                "source_span": "convoy",
                "user_span": "group",
                "severity": "moderate",
                "explanation": (
                    "'Group' is a generic term. In military register, 'convoy' specifically refers "
                    "to a group of vehicles traveling together for mutual protection."
                ),
            },
            {
                "type": "precision_loss",
                "source_span": "0600 hours",
                "user_span": "six",
                "severity": "minor",
                "explanation": (
                    "Military time '0600 hours' should be preserved as-is rather than "
                    "converted to colloquial 'six' which lacks AM/PM clarity."
                ),
            },
        ],
        "overall_score": 0.68,
        "feedback_text": (
            "Good effort. Your interpretation captured the core meaning but lost some "
            "precision. 'Convoy' is the correct military term and military time should "
            "be preserved verbatim. Focus on maintaining domain-specific vocabulary."
        ),
        "followup_exercise": {
            "type": "drill_term",
            "prompt_text": "Drill: How would you interpret '0800 hours convoy departure from sector 4'?",
        },
    },
    # Poor performance — omissions and register errors
    "poor": {
        "transcript": "We go at the checkpoint.",
        "reference_translation": "The convoy will depart at 0600 hours from the northern checkpoint.",
        "acceptable_paraphrases": [
            "The convoy leaves at 6 AM from the north checkpoint.",
        ],
        "errors": [
            {
                "type": "omission",
                "source_span": "0600 hours",
                "user_span": None,
                "severity": "critical",
                "explanation": "The departure time was completely omitted. Time is critical in military coordination.",
            },
            {
                "type": "register_error",
                "source_span": "The convoy will depart",
                "user_span": "We go",
                "severity": "critical",
                "explanation": (
                    "Informal first-person 'We go' violates military register. "
                    "Use third-person formal constructions."
                ),
            },
            {
                "type": "semantic_drift",
                "source_span": "northern checkpoint",
                "user_span": "the checkpoint",
                "severity": "moderate",
                "explanation": "The directional qualifier 'northern' was dropped, losing location specificity.",
            },
        ],
        "overall_score": 0.25,
        "feedback_text": (
            "This interpretation needs significant improvement. Critical information "
            "was omitted (departure time) and the register does not match military standards. "
            "Try again focusing on preserving all time references and using formal third-person constructions."
        ),
        "followup_exercise": {
            "type": "repeat",
            "prompt_text": "Repeat this segment focusing on: (1) include all time markers, (2) use formal register.",
        },
    },
}

# Map segment_id → fixture key (for deterministic frontend testing)
_SEGMENT_FIXTURE_MAP: dict[str, str] = {
    "11111111-1111-1111-1111-111111111111": "good",
    "22222222-2222-2222-2222-222222222222": "moderate",
    "33333333-3333-3333-3333-333333333333": "poor",
}

_MOCK_AUDIO_PATH = "mocks/feedback_audio_placeholder.mp3"


def get_mock_semantic_result(attempt_id: UUID, segment_id: UUID | str) -> SemanticResult:
    """Return a contract-conformant SemanticResult fixture for the given segment_id.

    Unknown segment IDs return the 'moderate' fixture by default.
    """
    seg_str = str(segment_id)
    fixture_key = _SEGMENT_FIXTURE_MAP.get(seg_str, "moderate")
    fx = _FIXTURES[fixture_key]

    errors = [
        SemanticResultError(
            type=e["type"],
            source_span=e["source_span"],
            user_span=e.get("user_span"),
            severity=e["severity"],
            explanation=e["explanation"],
        )
        for e in fx["errors"]
    ]
    followup = FollowupExercise(
        type=fx["followup_exercise"]["type"],
        prompt_text=fx["followup_exercise"]["prompt_text"],
        prompt_audio_path=_MOCK_AUDIO_PATH,
    )
    return SemanticResult(
        attempt_id=attempt_id,
        transcript=fx["transcript"],
        reference_translation=fx["reference_translation"],
        acceptable_paraphrases=fx["acceptable_paraphrases"],
        errors=errors,
        overall_score=fx["overall_score"],
        feedback_text=fx["feedback_text"],
        feedback_audio_path=_MOCK_AUDIO_PATH,
        followup_exercise=followup,
        computed_at=datetime.now(timezone.utc),
        latency_ms=42,
    )
