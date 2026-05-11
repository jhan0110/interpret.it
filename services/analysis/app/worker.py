"""Arq worker — runs `prosody` and `semantic` jobs from gateway.

Two queues share this WorkerSettings (start two `arq` processes with
`--queue prosody` and `--queue semantic` for CPU isolation). Both job
functions consume the same `AnalysisRequest` payload.

Per-attempt timeout is 20s (ARCHITECTURE.md ADR — locked in commit
0586fb6). Prosody targets ≤2s; semantic targets ≤12s. Hitting the 20s
cap is treated as failure; gateway will treat the missing result as a
neutral contribution to mastery.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import boto3
from arq.connections import RedisSettings

from app.contracts.models import AnalysisRequest, FollowupExercise, SemanticResult
from app.evaluation.evaluate import evaluate
from app.mocks.handlers import get_mock_semantic_result
from app.prosody.pipeline import run_prosody_pipeline
from app.reference.generate import ReferenceBundle, generate_reference
from app.rpc.gateway_client import push_prosody_result, push_semantic_result
from app.tts.elevenlabs_tts import generate_feedback_audio

log = logging.getLogger(__name__)

_PER_ATTEMPT_TIMEOUT_S = 20
_USE_MOCKS = os.getenv("USE_MOCKS") == "1"
_REFERENCE_CACHE_TTL = 86400  # 24 hours


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _download_blob(audio_path: str) -> bytes:
    client = boto3.client(
        "s3",
        endpoint_url=os.getenv("MINIO_ENDPOINT", "http://localhost:9000"),
        aws_access_key_id=os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        aws_secret_access_key=os.getenv("MINIO_SECRET_KEY", "minioadmin"),
    )
    bucket = os.getenv("MINIO_BUCKET", "interpretit")
    with tempfile.NamedTemporaryFile(suffix=Path(audio_path).suffix, delete=False) as tmp:
        client.download_fileobj(bucket, audio_path, tmp)
        tmp.flush()
        return Path(tmp.name).read_bytes()


async def run_prosody(_ctx: dict, payload: dict) -> dict:
    """Prosody fast-path job. Returns the serialized ProsodyResult."""
    req = AnalysisRequest.model_validate(payload)
    log.info("prosody start attempt=%s", req.attempt_id)

    async def _run() -> dict:
        audio_bytes = await asyncio.to_thread(_download_blob, req.audio_path)

        def _compute():
            return run_prosody_pipeline(
                audio_bytes=audio_bytes,
                attempt_id=req.attempt_id,
                lang=req.target_lang,
                word_tokens=None,
                feedback_audio_path="placeholder/feedback.wav",
            )

        result = await asyncio.to_thread(_compute)
        await push_prosody_result(result)
        return result.model_dump(mode="json")

    return await asyncio.wait_for(_run(), timeout=_PER_ATTEMPT_TIMEOUT_S)


async def _get_cached_reference(redis, segment_id: str) -> ReferenceBundle | None:
    """Fetch a cached ReferenceBundle from Redis. Returns None on miss."""
    raw = await redis.get(f"reference:{segment_id}")
    if raw is None:
        return None
    try:
        return ReferenceBundle.model_validate_json(raw)
    except Exception:
        log.warning("reference cache deserialization failed for segment=%s", segment_id)
        return None


async def _set_cached_reference(redis, segment_id: str, bundle: ReferenceBundle) -> None:
    """Store a ReferenceBundle in Redis with TTL."""
    await redis.set(f"reference:{segment_id}", bundle.model_dump_json(), ex=_REFERENCE_CACHE_TTL)


def _warm_whisper() -> None:
    """Load the Whisper model into the process cache so job 1 pays no penalty."""
    from app.asr.transcribe import _get_model

    _get_model()


async def run_semantic(_ctx: dict, payload: dict) -> dict:
    """Semantic full-path job. Returns the serialized SemanticResult."""
    req = AnalysisRequest.model_validate(payload)
    log.info("semantic start attempt=%s", req.attempt_id)

    if _USE_MOCKS:
        result = get_mock_semantic_result(req.attempt_id, req.segment_id)
        await push_semantic_result(result)
        return result.model_dump(mode="json")

    redis = _ctx["redis"]

    async def _run() -> dict:
        from app.asr.transcribe import transcribe

        start = datetime.now(UTC)

        # Mitigation 2: check reference cache before launching the Claude call.
        cached_ref = await _get_cached_reference(redis, str(req.segment_id))

        if cached_ref is not None:
            log.info("reference cache hit segment=%s", req.segment_id)
            # Only need to transcribe; skip generate_reference entirely.
            transcript = await asyncio.to_thread(transcribe, req.audio_path, req.target_lang)
            reference = cached_ref
        else:
            # Mitigation 1: run ASR and reference generation concurrently.
            transcript, reference = await asyncio.gather(
                asyncio.to_thread(transcribe, req.audio_path, req.target_lang),
                asyncio.to_thread(
                    generate_reference,
                    req.source_text,
                    req.source_lang,
                    req.target_lang,
                    req.register,
                    req.domain,
                ),
            )
            # Mitigation 2: populate cache for future attempts on the same segment.
            await _set_cached_reference(redis, str(req.segment_id), reference)

        feedback_audio_key = "placeholder/semantic_feedback.mp3"
        followup_audio_key = "placeholder/semantic_followup.mp3"
        try:
            feedback_audio_key = await asyncio.to_thread(
                generate_feedback_audio,
                "feedback placeholder",
                os.getenv("ELEVENLABS_FEEDBACK_VOICE", "EXAVITQu4vr4xnSDxMaL"),
            )
        except Exception:
            log.exception("feedback TTS failed; using placeholder")

        result = await asyncio.to_thread(
            evaluate,
            req.attempt_id,
            req.source_text,
            req.source_lang,
            req.target_lang,
            req.register,
            req.domain,
            req.difficulty_level,
            transcript.text,
            reference,
            feedback_audio_key,
            followup_audio_key,
            start,
        )
        await push_semantic_result(result)
        return result.model_dump(mode="json")

    try:
        return await asyncio.wait_for(_run(), timeout=_PER_ATTEMPT_TIMEOUT_S)
    except TimeoutError:
        log.warning("semantic timeout attempt=%s", req.attempt_id)
        # Emit a "no-op" SemanticResult so the gateway can still close the attempt.
        fallback = SemanticResult(
            attempt_id=req.attempt_id,
            transcript="",
            reference_translation="",
            acceptable_paraphrases=[],
            errors=[],
            overall_score=0.5,
            feedback_text="Analysis timed out.",
            feedback_audio_path="placeholder/timeout.mp3",
            followup_exercise=FollowupExercise(
                type="repeat",
                prompt_text="Please try the segment again.",
                prompt_audio_path="placeholder/timeout_followup.mp3",
            ),
            computed_at=datetime.now(UTC),
            latency_ms=_PER_ATTEMPT_TIMEOUT_S * 1000,
        )
        await push_semantic_result(fallback)
        return fallback.model_dump(mode="json")


async def on_startup(ctx: dict) -> None:
    """Pre-warm the Whisper model so job 1 doesn't pay the load cost."""
    if _USE_MOCKS:
        log.info("USE_MOCKS=1 — skipping Whisper warm-up")
        return
    try:
        log.info("warming Whisper model...")
        await asyncio.to_thread(_warm_whisper)
        log.info("Whisper model warm-up complete")
    except Exception:
        log.exception("Whisper warm-up failed; worker will continue without pre-warmed model")


class WorkerSettings:
    functions = [run_prosody, run_semantic]
    on_startup = on_startup
    redis_settings = _redis_settings()
    queue_name = os.getenv("ARQ_QUEUE_NAME", "prosody")
    max_jobs = int(os.getenv("ARQ_MAX_JOBS", "4"))
    job_timeout = _PER_ATTEMPT_TIMEOUT_S
    keep_result = 60
