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
) -> AnalysisRequest:
    """Push the AnalysisRequest to both arq queues. Returns the payload."""
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
    )
    payload = req.model_dump(mode="json")

    pool = await create_pool(_redis_settings())
    try:
        await pool.enqueue_job("run_prosody", payload, _queue_name="prosody")
        await pool.enqueue_job("run_semantic", payload, _queue_name="semantic")
    finally:
        await pool.aclose()
    return req
