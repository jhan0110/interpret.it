"""
Internal RPC client: push ProsodyResult back to Gateway.

Until Agent 1's Gateway RPC endpoint lands, results are also stored in
Redis under key "prosody_result:{attempt_id}" so the Gateway can poll.
The Gateway is the single writer to Postgres — Analysis never writes DB directly.
"""

from __future__ import annotations

import json
import logging
import os
import time

import redis.asyncio as aioredis

from app.contracts.models import ProsodyResult, SemanticResult

log = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_GATEWAY_RPC_URL = os.getenv("GATEWAY_RPC_URL", "http://localhost:8000")
_RESULT_TTL_S = 300


async def push_prosody_result(result: ProsodyResult) -> None:
    """Deliver ProsodyResult to Gateway (HTTP), with Redis fallback."""
    log.info("[rpc.push_prosody.begin] attempt=%s", result.attempt_id)
    t0 = time.monotonic()
    payload = result.model_dump_json()
    await _write_redis(f"prosody_result:{result.attempt_id}", payload)
    log.info("[rpc.push_prosody.redis_written] attempt=%s", result.attempt_id)
    await _post(
        f"{_GATEWAY_RPC_URL}/internal/prosody_result",
        payload,
    )
    rpc_ms = int((time.monotonic() - t0) * 1000)
    log.info("[rpc.push_prosody.done] attempt=%s took=%dms", result.attempt_id, rpc_ms)


async def push_semantic_result(result: SemanticResult) -> None:
    """Deliver SemanticResult to Gateway (HTTP), with Redis fallback."""
    log.info("[rpc.push_semantic.begin] attempt=%s", result.attempt_id)
    t0 = time.monotonic()
    payload = result.model_dump_json()
    await _write_redis(f"semantic_result:{result.attempt_id}", payload)
    log.info("[rpc.push_semantic.redis_written] attempt=%s", result.attempt_id)
    await _post(
        f"{_GATEWAY_RPC_URL}/internal/semantic_result",
        payload,
    )
    rpc_ms = int((time.monotonic() - t0) * 1000)
    log.info("[rpc.push_semantic.done] attempt=%s took=%dms", result.attempt_id, rpc_ms)


async def push_vocab_extraction(payload: dict) -> None:
    """POST missed vocab terms to gateway /internal/vocab_extraction."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.post(
                f"{_GATEWAY_RPC_URL}/internal/vocab_extraction",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            r.raise_for_status()
    except httpx.HTTPError:
        pass


async def push_segment_insert(payload: dict) -> dict:
    """POST a generated segment to the gateway. Returns the response JSON.

    Raises on non-2xx so callers can fail-fast during generation.
    """
    import httpx

    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{_GATEWAY_RPC_URL}/internal/segments", json=payload
        )
        r.raise_for_status()
        return r.json()


GENERATION_CHANNEL = "generation_events"


async def publish_generation_event(event: dict) -> None:
    """Publish a generation progress/complete event for the gateway to fan
    out over the WebSocket. Lossy on purpose — late connectors miss events,
    which is fine because the session row also carries `generation_state`."""
    client = aioredis.from_url(_REDIS_URL, decode_responses=True)
    try:
        await client.publish(GENERATION_CHANNEL, json.dumps(event))
    finally:
        await client.aclose()


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
