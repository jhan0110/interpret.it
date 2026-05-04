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

from app.contracts.models import ProsodyResult

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_GATEWAY_RPC_URL = os.getenv("GATEWAY_RPC_URL", "http://localhost:8000")
_RESULT_TTL_S = 300


async def push_prosody_result(result: ProsodyResult) -> None:
    """
    Deliver ProsodyResult to Gateway.

    Strategy (in order):
    1. Try HTTP POST to Gateway internal RPC endpoint.
    2. Always write to Redis result queue as fallback/supplement.
    """
    await _write_to_redis(result)
    await _post_to_gateway(result)


async def _write_to_redis(result: ProsodyResult) -> None:
    client = aioredis.from_url(_REDIS_URL, decode_responses=True)
    try:
        key = f"prosody_result:{result.attempt_id}"
        await client.set(key, result.model_dump_json(), ex=_RESULT_TTL_S)
    finally:
        await client.aclose()


async def _post_to_gateway(result: ProsodyResult) -> None:
    import httpx

    url = f"{_GATEWAY_RPC_URL}/internal/prosody_result"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(url, content=result.model_dump_json(), headers={"Content-Type": "application/json"})
    except httpx.HTTPError:
        # Redis fallback already written; gateway will pick up on next poll.
        pass
