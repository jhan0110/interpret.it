# Hand-translated from contracts/contracts.json v1.0.0
# Source of truth: contracts/contracts.json — do not edit field names here without
# updating contracts.json first.

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

BoundedFloat = Annotated[float, Field(ge=0.0, le=1.0)]
DifficultyLevel = Annotated[int, Field(ge=1, le=10)]

Register = Literal["formal-military", "formal-diplomatic", "informal"]
Lang = Literal["ko", "en"]
CognitiveLoad = Literal["low", "moderate", "high", "overloaded"]
ErrorType = Literal[
    "semantic_drift",
    "lexical_gap",
    "register_error",
    "omission",
    "tense_shift",
    "precision_loss",
]
Severity = Literal["minor", "moderate", "critical"]
FollowupType = Literal["repeat", "rephrase", "drill_term", "contextual_qa"]
TriggeredBy = Literal["prosody", "semantic", "both"]
SessionMode = Literal["interpretation", "memorization"]
KeyPointImportance = Literal["primary", "secondary"]


class AudioSubmission(BaseModel):
    segment_id: UUID
    attempt_id: UUID
    audio_format: str
    byte_length: int
    duration_ms: int
    recorded_at: datetime
    # audio_blob delivered in the following binary frame — not in this model


class AnalysisRequest(BaseModel):
    # `register` is a normal field but pydantic warns about attr-shadowing on
    # some versions; the explicit ConfigDict silences that.
    model_config = ConfigDict(protected_namespaces=())

    attempt_id: UUID
    segment_id: UUID
    session_id: UUID
    learner_id: UUID
    audio_path: str
    source_text: str
    source_lang: Lang
    target_lang: Lang
    register: str
    domain: str
    difficulty_level: DifficultyLevel
    enqueued_at: datetime
    asr_prompt: str | None = None
    mode: SessionMode = "interpretation"


class ProsodyResult(BaseModel):
    attempt_id: UUID
    pause_count: int
    filler_count: int
    mean_wpm: float
    silence_ratio: BoundedFloat
    cognitive_load_estimate: CognitiveLoad
    feedback_audio_path: str
    computed_at: datetime
    latency_ms: int


class SemanticResultError(BaseModel):
    type: ErrorType
    source_span: str
    user_span: Optional[str] = None
    severity: Severity
    explanation: str


class FollowupExercise(BaseModel):
    type: FollowupType
    prompt_text: str
    prompt_audio_path: str


class KeyPoint(BaseModel):
    text: str
    recalled: bool
    importance: KeyPointImportance


class SemanticResult(BaseModel):
    attempt_id: UUID
    mode: SessionMode = "interpretation"
    source_text: str = ""
    transcript: str
    reference_translation: str
    acceptable_paraphrases: list[str]
    errors: list[SemanticResultError]
    key_points: list[KeyPoint] | None = None
    overall_score: BoundedFloat
    feedback_text: str
    feedback_audio_path: str
    followup_exercise: FollowupExercise
    computed_at: datetime
    latency_ms: int


class MasteryUpdate(BaseModel):
    learner_id: UUID
    segment_id: UUID
    domain: str
    old_mastery: BoundedFloat
    new_mastery: BoundedFloat
    difficulty_delta: int
    triggered_by: TriggeredBy
    computed_at: datetime
