"""Pydantic v2 mirrors of contracts/contracts.json.

`contracts.json` is authoritative; service code conforms to it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel

Lang = Literal["ko", "en"]
Register = Literal["formal-military", "formal-diplomatic", "informal"]
CognitiveLoad = Literal["low", "moderate", "high", "overloaded"]
Severity = Literal["minor", "moderate", "critical"]
SemanticErrorType = Literal[
    "semantic_drift",
    "lexical_gap",
    "register_error",
    "omission",
    "tense_shift",
    "precision_loss",
]
SessionState = Literal[
    "idle",
    "listening",
    "recording",
    "analyzing",
    "feedback",
    "next_segment",
    "complete",
]
ErrorCode = Literal[
    "invalid_state",
    "invalid_payload",
    "upload_failed",
    "analysis_failed",
    "internal",
]
Unit = Annotated[float, Field(ge=0.0, le=1.0)]
DifficultyLevel = Annotated[int, Field(ge=1, le=10)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


# ---------------------------------------------------------------------------
# Core wire shapes
# ---------------------------------------------------------------------------


class AudioSubmission(_Strict):
    segment_id: UUID
    attempt_id: UUID
    audio_format: str = "opus/webm"
    byte_length: int = Field(gt=0)
    duration_ms: int = Field(ge=0)
    recorded_at: datetime


class AnalysisRequest(_Strict):
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


class ProsodyResult(_Strict):
    attempt_id: UUID
    pause_count: int = Field(ge=0)
    filler_count: int = Field(ge=0)
    mean_wpm: float = Field(ge=0)
    silence_ratio: Unit
    cognitive_load_estimate: CognitiveLoad
    feedback_audio_path: str
    computed_at: datetime
    latency_ms: int = Field(ge=0)


class SemanticError(_Strict):
    type: SemanticErrorType
    source_span: str
    user_span: str | None
    severity: Severity
    explanation: str


class FollowupExercise(_Strict):
    type: Literal["repeat", "rephrase", "drill_term", "contextual_qa"]
    prompt_text: str
    prompt_audio_path: str


class SemanticResult(_Strict):
    attempt_id: UUID
    transcript: str
    reference_translation: str
    acceptable_paraphrases: list[str]
    errors: list[SemanticError]
    overall_score: Unit
    feedback_text: str
    feedback_audio_path: str
    followup_exercise: FollowupExercise
    computed_at: datetime
    latency_ms: int = Field(ge=0)


class MasteryUpdate(_Strict):
    learner_id: UUID
    segment_id: UUID
    domain: str
    old_mastery: Unit
    new_mastery: Unit
    difficulty_delta: int
    triggered_by: Literal["prosody", "semantic", "both"]
    computed_at: datetime


# ---------------------------------------------------------------------------
# Persistent entities
# ---------------------------------------------------------------------------


class Learner(_Strict):
    id: UUID
    display_name: str
    primary_lang: Lang
    created_at: datetime


class Session(_Strict):
    id: UUID
    learner_id: UUID
    state: SessionState
    domain: str
    target_lang: Lang
    source_lang: Lang
    started_at: datetime
    completed_at: datetime | None
    segment_count: int = Field(ge=0)
    current_segment_id: UUID | None


class Segment(_Strict):
    id: UUID
    source_text: str
    source_lang: Lang
    target_lang: Lang
    register: str
    domain: str
    difficulty_level: DifficultyLevel
    audio_path: str
    embedding_id: UUID | None
    created_at: datetime


class Attempt(_Strict):
    id: UUID
    session_id: UUID
    segment_id: UUID
    learner_id: UUID
    audio_path: str
    recorded_at: datetime
    prosody_result: ProsodyResult | None
    semantic_result: SemanticResult | None
    closed_at: datetime | None


class MasteryScore(_Strict):
    learner_id: UUID
    domain: str
    mastery: Unit
    attempts_count: int = Field(ge=0)
    last_attempt_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# REST envelopes
# ---------------------------------------------------------------------------


class GenerationParams(_Strict):
    """Operator-chosen parameters for the daily-training-session generator."""

    topics: list[str] = Field(min_length=1)
    user_level: int = Field(ge=1, le=5)
    duration: Literal["short", "medium", "long"]
    current_context: str | None = None
    n: int = Field(default=2, ge=1, le=50)  # TEMP: reduced from 10 to save API while testing


class PostSessionRequest(_Strict):
    learner_id: UUID
    domain: str
    source_lang: Lang
    target_lang: Lang
    # When supplied, the gateway enqueues a generation job and the session
    # walks the pre-generated phrases rather than the live ladder.
    generation: GenerationParams | None = None


class CompleteSessionResponse(_Strict):
    session: Session
    attempts_count: int = Field(ge=0)
    mean_score: Unit
    mastery_changes: list[MasteryUpdate]


class GetLearnerMasteryResponse(_Strict):
    learner_id: UUID
    scores: list[MasteryScore]


class DependenciesHealth(_Strict):
    postgres: Literal["ok", "down"]
    redis: Literal["ok", "down"]
    minio: Literal["ok", "down"]


class HealthResponse(_Strict):
    status: Literal["ok", "degraded", "down"]
    version: str
    checked_at: datetime
    dependencies: DependenciesHealth


# ---------------------------------------------------------------------------
# WebSocket envelope + discriminated union
# ---------------------------------------------------------------------------


class _WSBase(_Strict):
    ts: datetime


class WSSessionStartPayload(_Strict):
    session_id: UUID


class WSSegmentRequestPayload(_Strict):
    session_id: UUID


class WSRecordingBeginPayload(_Strict):
    session_id: UUID
    segment_id: UUID
    attempt_id: UUID


class WSSessionCompletePayload(_Strict):
    session_id: UUID


class WSSegmentPlayPayload(_Strict):
    segment_id: UUID
    audio_url: str
    duration_ms: int = Field(ge=0)
    difficulty_level: DifficultyLevel
    delay_ms: int = Field(ge=0)


class WSGenerationProgressPayload(_Strict):
    session_id: UUID
    ready: int = Field(ge=0)
    target: int = Field(ge=1)
    state: Literal["pending", "ready", "failed"]


class WSGenerationCompletePayload(_Strict):
    session_id: UUID
    count: int = Field(ge=0)
    scenario_summary: str | None = None


class WSAudioAckPayload(_Strict):
    attempt_id: UUID
    audio_path: str


class WSSessionCompleteAckPayload(_Strict):
    session_id: UUID
    attempts_count: int = Field(ge=0)
    mean_score: Unit


class WSStateChangePayload(_Strict):
    session_id: UUID
    from_: SessionState = Field(alias="from")
    to: SessionState
    reason: str

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ErrorPayload(_Strict):
    code: ErrorCode
    detail: str
    attempt_id: UUID | None = None
    session_id: UUID | None = None


class WSSessionStart(_WSBase):
    type: Literal["session.start"]
    payload: WSSessionStartPayload


class WSSegmentRequest(_WSBase):
    type: Literal["segment.request"]
    payload: WSSegmentRequestPayload


class WSRecordingBegin(_WSBase):
    type: Literal["recording.begin"]
    payload: WSRecordingBeginPayload


class WSAudioSubmitHeader(_WSBase):
    type: Literal["audio.submit_header"]
    payload: AudioSubmission


class WSSessionComplete(_WSBase):
    type: Literal["session.complete"]
    payload: WSSessionCompletePayload


class WSSegmentPlay(_WSBase):
    type: Literal["segment.play"]
    payload: WSSegmentPlayPayload


class WSGenerationProgress(_WSBase):
    type: Literal["generation.progress"]
    payload: WSGenerationProgressPayload


class WSGenerationComplete(_WSBase):
    type: Literal["generation.complete"]
    payload: WSGenerationCompletePayload


class WSAudioAck(_WSBase):
    type: Literal["audio.ack"]
    payload: WSAudioAckPayload


class WSProsodyResult(_WSBase):
    type: Literal["prosody.result"]
    payload: ProsodyResult


class WSSemanticResult(_WSBase):
    type: Literal["semantic.result"]
    payload: SemanticResult


class WSMasteryUpdate(_WSBase):
    type: Literal["mastery.update"]
    payload: MasteryUpdate


class WSSessionCompleteAck(_WSBase):
    type: Literal["session.complete_ack"]
    payload: WSSessionCompleteAckPayload


class WSStateChange(_WSBase):
    type: Literal["state.change"]
    payload: WSStateChangePayload


class WSError(_WSBase):
    type: Literal["error"]
    payload: ErrorPayload


WSEnvelope = Annotated[
    WSSessionStart
    | WSSegmentRequest
    | WSRecordingBegin
    | WSAudioSubmitHeader
    | WSSessionComplete
    | WSSegmentPlay
    | WSAudioAck
    | WSProsodyResult
    | WSSemanticResult
    | WSMasteryUpdate
    | WSSessionCompleteAck
    | WSStateChange
    | WSGenerationProgress
    | WSGenerationComplete
    | WSError,
    Field(discriminator="type"),
]


class WSMessage(RootModel[WSEnvelope]):
    """Helper for parsing inbound JSON frames against the discriminated union.

    Clients send a bare envelope (`{type, ts, payload}`) at the top level;
    pydantic's RootModel lets us discriminate on it without wrapping.
    `WSMessage.model_validate_json(text).root` returns the typed envelope.
    """
