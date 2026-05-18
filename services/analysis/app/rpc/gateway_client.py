"""
Internal RPC client: push ProsodyResult back to Gateway.

Until Agent 1's Gateway RPC endpoint lands, results are also stored in
Redis under key "prosody_result:{attempt_id}" so the Gateway can poll.
The Gateway is the single writer to Postgres — Analysis never writes DB directly.
"""

from __future__ import annotations

import json
import os

import redis.asyncio as aioredis

from uuid import UUID

from app.contracts.models import ProsodyResult, SemanticResult

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_GATEWAY_RPC_URL = os.getenv("GATEWAY_RPC_URL", "http://localhost:8000")
_RESULT_TTL_S = 300


async def push_prosody_result(result: ProsodyResult) -> None:
    """Deliver ProsodyResult to Gateway (HTTP), with Redis fallback."""
    await _write_redis(f"prosody_result:{result.attempt_id}", result.model_dump_json())
    await _post(
        f"{_GATEWAY_RPC_URL}/internal/prosody_result",
        result.model_dump_json(),
    )


async def push_semantic_result(result: SemanticResult) -> None:
    """Deliver SemanticResult to Gateway (HTTP), with Redis fallback."""
    await _write_redis(f"semantic_result:{result.attempt_id}", result.model_dump_json())
    await _post(
        f"{_GATEWAY_RPC_URL}/internal/semantic_result",
        result.model_dump_json(),
    )


async def push_segment_embeddings(
    segment_id: UUID,
    paraphrases: list[str],
    embeddings: list[list[float]],
) -> None:
    """POST paraphrase embeddings to the gateway to persist in paraphrase_embeddings."""
    import json

    body = json.dumps(
        {
            "paraphrases": [
                {"text": text, "embedding": emb}
                for text, emb in zip(paraphrases, embeddings, strict=False)
            ]
        }
    )
    await _post(f"{_GATEWAY_RPC_URL}/internal/segments/{segment_id}/embeddings", body)


async def _write_redis(key: str, payload: str) -> None:
    client = aioredis.from_url(_REDIS_URL, decode_responses=True)
    try:
        await client.set(key, payload, ex=_RESULT_TTL_S)
    finally:
        await client.aclose()


async def _post(url: str, payload: str) -> None:
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, content=payload, headers={"Content-Type": "application/json"})
    except httpx.HTTPError:
        # Redis fallback already written; gateway can recover from there.
        pass
