# AUTO-GENERATED — do not edit manually.
# Regenerate with: python scripts/gen_contracts.py
# Source: contracts/contracts.json v1.0.0

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

# ── type aliases ──────────────────────────────────────────────────────────────
BoundedFloat = Annotated[float, Field(ge=0.0, le=1.0)]
DifficultyLevel = Annotated[int, Field(ge=1, le=10)]

class AudioSubmission(BaseModel):
    segment_id: UUID
    attempt_id: UUID
    audio_format: str
    audio_blob: bytes
    byte_length: int
    duration_ms: int
    recorded_at: datetime

class AnalysisRequest(BaseModel):
    attempt_id: UUID
    segment_id: UUID
    session_id: UUID
    learner_id: UUID
    audio_path: str
    source_text: str
    source_lang: Literal["ko", "en"]
    target_lang: Literal["ko", "en"]
    register: Literal["formal-military", "formal-diplomatic", "informal"]
    domain: str
    difficulty_level: DifficultyLevel
    enqueued_at: datetime
    asr_prompt: Optional[str] = None
    mode: Literal["interpretation", "memorization"]

class ProsodyResult(BaseModel):
    attempt_id: UUID
    pause_count: int
    filler_count: int
    mean_wpm: float
    silence_ratio: BoundedFloat
    cognitive_load_estimate: Literal["low", "moderate", "high", "overloaded"]
    feedback_audio_path: str
    computed_at: datetime
    latency_ms: int

class SemanticResult_Followup_Exercise(BaseModel):
    type: Literal["repeat", "rephrase", "drill_term", "contextual_qa"]
    prompt_text: str
    prompt_audio_path: str

class SemanticResult_Key_Points(BaseModel):
    text: str
    recalled: str
    importance: Literal["primary", "secondary"]

class SemanticResult_Errors(BaseModel):
    type: Literal["semantic_drift", "lexical_gap", "register_error", "omission", "tense_shift", "precision_loss"]
    source_span: str
    user_span: Optional[str] = None
    severity: Literal["minor", "moderate", "critical"]
    explanation: str

class SemanticResult(BaseModel):
    attempt_id: UUID
    mode: Literal["interpretation", "memorization"]
    source_text: str
    transcript: str
    reference_translation: str
    acceptable_paraphrases: list[str]
    errors: list[SemanticResult_Errors]
    key_points: list[SemanticResult_Key_Points]
    overall_score: BoundedFloat
    feedback_text: str
    feedback_audio_path: str
    followup_exercise: SemanticResult_Followup_Exercise
    computed_at: datetime
    latency_ms: int

class MasteryUpdate(BaseModel):
    learner_id: UUID
    segment_id: UUID
    domain: str
    old_mastery: BoundedFloat
    new_mastery: BoundedFloat
    difficulty_delta: int
    triggered_by: Literal["prosody", "semantic", "both"]
    computed_at: datetime

class Learner(BaseModel):
    id: UUID
    display_name: str
    primary_lang: Literal["ko", "en"]
    created_at: datetime

class Session(BaseModel):
    id: UUID
    learner_id: UUID
    mode: Literal["interpretation", "memorization"]
    state: Literal["idle", "listening", "recording", "analyzing", "feedback", "next_segment", "complete"]
    domain: str
    target_lang: Literal["ko", "en"]
    source_lang: Literal["ko", "en"]
    started_at: datetime
    completed_at: Optional[datetime] = None
    segment_count: int
    replays_budget: int
    current_segment_id: Optional[UUID] = None

class Segment(BaseModel):
    id: UUID
    source_text: str
    source_lang: Literal["ko", "en"]
    target_lang: Literal["ko", "en"]
    register: Literal["formal-military", "formal-diplomatic", "informal"]
    domain: str
    difficulty_level: DifficultyLevel
    audio_path: str
    embedding_id: Optional[UUID] = None
    created_at: datetime

class Attempt(BaseModel):
    id: UUID
    session_id: UUID
    segment_id: UUID
    learner_id: UUID
    audio_path: str
    recorded_at: datetime
    prosody_result: Optional[Literal["ProsodyResult"]] = None
    semantic_result: Optional[Literal["SemanticResult"]] = None
    replayed: str
    closed_at: Optional[datetime] = None

class MasteryScore(BaseModel):
    learner_id: UUID
    domain: str
    mastery: BoundedFloat
    tier: str
    tier_name: str
    next_tier_name: Optional[str] = None
    progress: BoundedFloat
    attempts_count: int
    last_attempt_at: datetime
    updated_at: datetime

class REST_PostSessionRequest(BaseModel):
    learner_id: UUID
    domain: str
    source_lang: Literal["ko", "en"]
    target_lang: Literal["ko", "en"]
    mode: Literal["interpretation", "memorization"]
    generation: Optional[Literal["REST.GenerationParams"]] = None

class REST_GenerationParams(BaseModel):
    topics: list[str]
    user_level: str
    duration: Literal["short", "medium", "long"]
    current_context: Optional[str] = None
    n: str

# REST.PostSessionResponse is an alias for: Session

# REST.GetSessionResponse is an alias for: Session

class REST_CompleteSessionResponse(BaseModel):
    session: str
    attempts_count: int
    mean_score: BoundedFloat
    mastery_changes: list[MasteryUpdate]

class REST_GetAttemptAudioUrlResponse(BaseModel):
    audio_url: str
    expires_in_s: int

# REST.GetLearnerResponse is an alias for: Learner

class REST_GetLearnerMasteryResponse(BaseModel):
    learner_id: UUID
    scores: list[MasteryScore]

class REST_HealthResponse_Dependencies(BaseModel):
    postgres: Literal["ok", "down"]
    redis: Literal["ok", "down"]
    minio: Literal["ok", "down"]

class REST_HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"]
    version: str
    checked_at: datetime
    dependencies: REST_HealthResponse_Dependencies

class WSEnvelope(BaseModel):
    type: str
    ts: datetime
    payload: dict

class WSMessage_SessionStart_Payload(BaseModel):
    session_id: UUID

class WSMessage_SessionStart(BaseModel):
    type: str
    payload: WSMessage_SessionStart_Payload

class WSMessage_SegmentRequest_Payload(BaseModel):
    session_id: UUID

class WSMessage_SegmentRequest(BaseModel):
    type: str
    payload: WSMessage_SegmentRequest_Payload

class WSMessage_RecordingBegin_Payload(BaseModel):
    session_id: UUID
    segment_id: UUID
    attempt_id: UUID

class WSMessage_RecordingBegin(BaseModel):
    type: str
    payload: WSMessage_RecordingBegin_Payload

class WSMessage_AudioSubmitHeader(BaseModel):
    type: str
    payload: str

class WSMessage_SessionComplete_Payload(BaseModel):
    session_id: UUID

class WSMessage_SessionComplete(BaseModel):
    type: str
    payload: WSMessage_SessionComplete_Payload

class WSMessage_SegmentPlay_Payload(BaseModel):
    segment_id: UUID
    audio_url: str
    duration_ms: int
    difficulty_level: DifficultyLevel
    delay_ms: int

class WSMessage_SegmentPlay(BaseModel):
    type: str
    payload: WSMessage_SegmentPlay_Payload

class WSMessage_AudioAck_Payload(BaseModel):
    attempt_id: UUID
    audio_path: str

class WSMessage_AudioAck(BaseModel):
    type: str
    payload: WSMessage_AudioAck_Payload

class WSMessage_ProsodyResult(BaseModel):
    type: str
    payload: str

class WSMessage_SemanticResult(BaseModel):
    type: str
    payload: str

class WSMessage_MasteryUpdate(BaseModel):
    type: str
    payload: str

class WSMessage_SessionCompleteAck_Payload(BaseModel):
    session_id: UUID
    attempts_count: int
    mean_score: BoundedFloat

class WSMessage_SessionCompleteAck(BaseModel):
    type: str
    payload: WSMessage_SessionCompleteAck_Payload

class WSMessage_StateChange_Payload(BaseModel):
    session_id: UUID
    from: Literal["idle", "listening", "recording", "analyzing", "feedback", "next_segment", "complete"]
    to: Literal["idle", "listening", "recording", "analyzing", "feedback", "next_segment", "complete"]
    reason: str

class WSMessage_StateChange(BaseModel):
    type: str
    payload: WSMessage_StateChange_Payload

class WSMessage_GenerationProgress_Payload(BaseModel):
    session_id: UUID
    ready: str
    target: str
    state: Literal["pending", "ready", "failed"]

class WSMessage_GenerationProgress(BaseModel):
    type: str
    payload: WSMessage_GenerationProgress_Payload

class WSMessage_GenerationComplete_Payload(BaseModel):
    session_id: UUID
    count: str
    scenario_summary: Optional[str] = None

class WSMessage_GenerationComplete(BaseModel):
    type: str
    payload: WSMessage_GenerationComplete_Payload

class WSMessage_ReplayRequest_Payload(BaseModel):
    session_id: UUID
    attempt_id: UUID

class WSMessage_ReplayRequest(BaseModel):
    type: str
    payload: WSMessage_ReplayRequest_Payload

class WSMessage_ReplayGranted_Payload(BaseModel):
    session_id: UUID
    attempt_id: UUID
    replays_remaining: int

class WSMessage_ReplayGranted(BaseModel):
    type: str
    payload: WSMessage_ReplayGranted_Payload

class WSMessage_ReplayDenied_Payload(BaseModel):
    session_id: UUID
    attempt_id: UUID
    reason: Literal["budget_exhausted", "already_replayed", "wrong_mode", "invalid_state"]
    replays_remaining: int

class WSMessage_ReplayDenied(BaseModel):
    type: str
    payload: WSMessage_ReplayDenied_Payload

class WSMessage_Error_Payload(BaseModel):
    code: Literal["invalid_state", "invalid_payload", "upload_failed", "analysis_failed", "internal"]
    detail: str
    attempt_id: Optional[UUID] = None
    session_id: Optional[UUID] = None

class WSMessage_Error(BaseModel):
    type: str
    payload: WSMessage_Error_Payload
