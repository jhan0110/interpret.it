"""Arq queue dispatch from gateway → analysis.

Gateway enqueues the SAME AnalysisRequest payload onto both the `prosody`
and `semantic` arq queues so both pipelines see identical inputs (per
ARCHITECTURE.md §1.1 and the contracts.json "AnalysisRequest" comment).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID

from arq import create_pool
from arq.connections import RedisSettings

from app.contracts.models import AnalysisRequest
from app.vocab.seeds import domain_asr_prompt


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


async def enqueue_analysis(
    *,
    attempt_id: UUID,
    segment_id: UUID,
    session_id: UUID,
    learner_id: UUID,
    audio_path: str,
    source_text: str,
    source_lang: str,
    target_lang: str,
    register: str,
    domain: str,
    difficulty_level: int,
    mode: str = "interpretation",
) -> AnalysisRequest:
    """Push the AnalysisRequest to both arq queues. Returns the payload."""
    hint = domain_asr_prompt(domain, target_lang) or None
    req = AnalysisRequest(
        attempt_id=attempt_id,
        segment_id=segment_id,
        session_id=session_id,
        learner_id=learner_id,
        audio_path=audio_path,
        source_text=source_text,
        source_lang=source_lang,  # type: ignore[arg-type]
        target_lang=target_lang,  # type: ignore[arg-type]
        register=register,  # type: ignore[arg-type]
        domain=domain,
        difficulty_level=difficulty_level,
        enqueued_at=datetime.now(UTC),
        asr_prompt=hint,
        mode=mode,  # type: ignore[arg-type]
    )
    payload = req.model_dump(mode="json")

    pool = await create_pool(_redis_settings())
    try:
        # Prosody is now derived inside run_semantic from ASR word timestamps;
        # see services/analysis/app/prosody/word_prosody.py. No separate queue.
        await pool.enqueue_job("run_semantic", payload, _queue_name="semantic")
    finally:
        await pool.aclose()
    return req


async def enqueue_generation(
    *,
    session_id: UUID,
    learner_id: UUID,
    domain: str,
    source_lang: str,
    target_lang: str,
    generation_params: dict,
) -> None:
    """Push a generation job onto the `generation` arq queue."""
    payload = {
        "session_id": str(session_id),
        "learner_id": str(learner_id),
        "domain": domain,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "params": generation_params,
    }
    pool = await create_pool(_redis_settings())
    try:
        await pool.enqueue_job(
            "run_generation", payload, _queue_name="generation"
        )
    finally:
        await pool.aclose()
