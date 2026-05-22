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
import time
from datetime import UTC, datetime

import arq.connections
from arq.connections import RedisSettings

from app.content.session_generation import run_generation
from app.contracts.models import AnalysisRequest, FollowupExercise, ProsodyResult, SemanticResult
from app.evaluation.evaluate import evaluate
from app.mocks.handlers import get_mock_semantic_result
from app.prosody.word_prosody import compute_prosody_from_words
from app.reference.generate import ReferenceBundle, generate_reference
from app.rpc.gateway_client import push_prosody_result, push_semantic_result
from app.tts.elevenlabs_tts import generate_feedback_audio
from app.vocab.extract import run_vocab_extraction

log = logging.getLogger(__name__)

_PER_ATTEMPT_TIMEOUT_S = 30
_USE_MOCKS = os.getenv("USE_MOCKS") == "1"
_REFERENCE_CACHE_TTL = 86400  # 24 hours


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


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


async def run_semantic(_ctx: dict, payload: dict) -> dict:
    """Semantic full-path job. Returns the serialized SemanticResult."""
    req = AnalysisRequest.model_validate(payload)
    job_start = time.monotonic()
    log.info(
        "[semantic.start] attempt=%s source_lang=%s target_lang=%s",
        req.attempt_id,
        req.source_lang,
        req.target_lang,
    )

    if _USE_MOCKS:
        result = get_mock_semantic_result(req.attempt_id, req.segment_id)
        mock_prosody = ProsodyResult(
            attempt_id=req.attempt_id,
            pause_count=1,
            filler_count=0,
            mean_wpm=120.0,
            silence_ratio=0.18,
            cognitive_load_estimate="moderate",
            feedback_audio_path="placeholder/feedback.wav",
            computed_at=datetime.now(UTC),
            latency_ms=50,
        )
        await push_prosody_result(mock_prosody)
        await push_semantic_result(result)
        return result.model_dump(mode="json")

    redis = _ctx["redis"]

    async def _run() -> dict:
        from app.asr.transcribe import transcribe

        start = datetime.now(UTC)

        # Mitigation 2: check reference cache before launching the Claude call.
        cached_ref = await _get_cached_reference(redis, str(req.segment_id))

        if cached_ref is not None:
            log.info("[semantic.reference.cache_hit] attempt=%s segment=%s", req.attempt_id, req.segment_id)
            # Only need to transcribe; skip generate_reference entirely.
            log.info("[semantic.transcribe.begin] attempt=%s", req.attempt_id)
            t_asr = time.monotonic()
            transcript = await asyncio.to_thread(transcribe, req.audio_path, req.target_lang)
            asr_ms = int((time.monotonic() - t_asr) * 1000)
            log.info("[semantic.transcribe.done] attempt=%s chars=%d took=%dms", req.attempt_id, len(transcript.text), asr_ms)
            reference = cached_ref
        else:
            log.info("[semantic.reference.cache_miss] attempt=%s", req.attempt_id)
            # Mitigation 1: run ASR and reference generation concurrently.
            log.info("[semantic.transcribe.begin] attempt=%s", req.attempt_id)
            log.info("[semantic.reference.begin] attempt=%s", req.attempt_id)
            t_parallel = time.monotonic()
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
            parallel_ms = int((time.monotonic() - t_parallel) * 1000)
            log.info("[semantic.transcribe.done] attempt=%s chars=%d took=%dms", req.attempt_id, len(transcript.text), parallel_ms)
            log.info("[semantic.reference.done] attempt=%s took=%dms", req.attempt_id, parallel_ms)
            # Mitigation 2: populate cache for future attempts on the same segment.
            await _set_cached_reference(redis, str(req.segment_id), reference)

        # Derive prosody from ASR word timestamps and push early so the
        # frontend cognitive-load indicator lights up before evaluate runs.
        t_pros = time.monotonic()
        prosody_result = compute_prosody_from_words(
            words=transcript.words,
            audio_duration_s=transcript.duration_s,
            lang=req.target_lang,
            attempt_id=req.attempt_id,
            feedback_audio_path="placeholder/feedback.wav",
            started_at=start,
        )
        log.info(
            "[prosody.derived] attempt=%s pauses=%d fillers=%d wpm=%.1f silence=%.2f load=%s took=%dms",
            req.attempt_id,
            prosody_result.pause_count,
            prosody_result.filler_count,
            prosody_result.mean_wpm,
            prosody_result.silence_ratio,
            prosody_result.cognitive_load_estimate,
            int((time.monotonic() - t_pros) * 1000),
        )
        await push_prosody_result(prosody_result)

        feedback_audio_key = "placeholder/semantic_feedback.mp3"
        followup_audio_key = "placeholder/semantic_followup.mp3"
        log.info("[semantic.tts.begin] attempt=%s", req.attempt_id)
        t_tts = time.monotonic()
        try:
            feedback_audio_key = await asyncio.to_thread(
                generate_feedback_audio,
                "feedback placeholder",
                os.getenv("ELEVENLABS_FEEDBACK_VOICE", "EXAVITQu4vr4xnSDxMaL"),
            )
            tts_ms = int((time.monotonic() - t_tts) * 1000)
            log.info("[semantic.tts.done] attempt=%s took=%dms key=%s", req.attempt_id, tts_ms, feedback_audio_key)
        except Exception as exc:
            tts_ms = int((time.monotonic() - t_tts) * 1000)
            log.info("[semantic.tts.error] attempt=%s err=%s took=%dms", req.attempt_id, exc, tts_ms)
            log.exception("feedback TTS failed; using placeholder")

        log.info("[semantic.evaluate.begin] attempt=%s", req.attempt_id)
        t_eval = time.monotonic()
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
        eval_ms = int((time.monotonic() - t_eval) * 1000)
        log.info(
            "[semantic.evaluate.done] attempt=%s score=%.3f errors=%d took=%dms",
            req.attempt_id,
            result.overall_score,
            len(result.errors),
            eval_ms,
        )

        log.info("[semantic.push.begin] attempt=%s", req.attempt_id)
        t_push = time.monotonic()
        await push_semantic_result(result)
        push_ms = int((time.monotonic() - t_push) * 1000)
        log.info("[semantic.push.done] attempt=%s took=%dms", req.attempt_id, push_ms)

        should_extract = result.overall_score < 0.75 or any(
            e.type in ("lexical_gap", "omission") for e in result.errors
        )
        if should_extract:
            pool = await arq.connections.create_pool(_redis_settings())
            try:
                await pool.enqueue_job(
                    "run_vocab_extraction",
                    {
                        "attempt_id": str(req.attempt_id),
                        "learner_id": str(req.learner_id),
                        "source_text": req.source_text,
                        "source_lang": req.source_lang,
                        "target_lang": req.target_lang,
                        "domain": req.domain,
                        "register": req.register,
                        "transcript": result.transcript,
                        "errors": [e.model_dump(mode="json") for e in result.errors],
                        "overall_score": result.overall_score,
                    },
                    _queue_name="semantic",
                )
                log.info("[semantic.vocab_extract.enqueued] attempt=%s", req.attempt_id)
            except Exception:
                log.exception("failed to enqueue vocab extraction attempt=%s", req.attempt_id)
            finally:
                await pool.aclose()

        total_ms = int((time.monotonic() - job_start) * 1000)
        log.info("[semantic.complete] attempt=%s total_took=%dms", req.attempt_id, total_ms)
        return result.model_dump(mode="json")

    try:
        return await asyncio.wait_for(_run(), timeout=_PER_ATTEMPT_TIMEOUT_S)
    except TimeoutError:
        elapsed_ms = int((time.monotonic() - job_start) * 1000)
        log.warning("[semantic.timeout] attempt=%s elapsed=%dms", req.attempt_id, elapsed_ms)
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


class WorkerSettings:
    functions = [run_semantic, run_generation, run_vocab_extraction]
    redis_settings = _redis_settings()
    queue_name = os.getenv("ARQ_QUEUE_NAME", "semantic")
    max_jobs = int(os.getenv("ARQ_MAX_JOBS", "4"))
    # Generation jobs include Claude + n×TTS + first-call multilingual-e5
    # cold-start (~60s on its own). Phase B saw n=3 take 83s cold / 16s warm,
    # so n=10 needs ~120s warm budget on top of the cold start. 300s gives
    # comfortable headroom; the per-attempt prosody/semantic 20s cap is
    # enforced inside those handlers via asyncio.wait_for.
    job_timeout = 300
    keep_result = 60
