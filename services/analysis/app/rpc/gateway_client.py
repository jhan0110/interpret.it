"""
Internal RPC client: push results from analysis workers back to Gateway.

Until Agent 1's Gateway RPC endpoint lands, results are also stored in
Redis under key "prosody_result:{attempt_id}" so the Gateway can poll.
The Gateway is the single writer to Postgres — Analysis never writes DB directly.

Implementation notes:

- The Redis client and httpx client are both module-level and cached.
  Earlier versions opened a fresh client per call; on the hot path
  (one prosody + one semantic push per attempt + one generation
  event per segment), that meant 3+ Redis connection spin-ups per
  attempt.
- `push_vocab_extraction` used to swallow HTTPError silently with
  `pass`; failures are now logged so bug investigations have a trail.
- `httpx` was imported inside each function. Module-level import is
  cheaper and conventional.
"""

from __future__ import annotations

import json
import logging
import os
import time

import httpx
import redis.asyncio as aioredis

from app.contracts.models import ProsodyResult, SemanticResult

log = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_GATEWAY_RPC_URL = os.getenv("GATEWAY_RPC_URL", "http://localhost:8000")
_RESULT_TTL_S = 300

_INTERNAL_RPC_SECRET = os.getenv("INTERNAL_RPC_SECRET", "")
if not _INTERNAL_RPC_SECRET:
    log.warning(
        "[rpc.gateway_client] INTERNAL_RPC_SECRET is unset — "
        "calls to gateway /internal/* will be rejected in production"
    )


_redis_client: aioredis.Redis | None = None
_http_client: httpx.AsyncClient | None = None


def _redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(_REDIS_URL, decode_responses=True)
    return _redis_client


def _http() -> httpx.AsyncClient:
    """Single cached async HTTP client.

    Connection pool stays warm across attempts. Per-call timeout is set
    on the `request` / `post` site so we can use different budgets for
    different endpoints (segment inserts are slower than vocab pushes).
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient()
    return _http_client


def _rpc_headers() -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if _INTERNAL_RPC_SECRET:
        h["Authorization"] = f"Bearer {_INTERNAL_RPC_SECRET}"
    return h


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
    """POST missed vocab terms to gateway /internal/vocab_extraction.

    Logs (rather than swallows) HTTP failures so a misconfigured
    deployment doesn't lose every extracted-term post silently.
    """
    try:
        r = await _http().post(
            f"{_GATEWAY_RPC_URL}/internal/vocab_extraction",
            json=payload,
            headers=_rpc_headers(),
            timeout=5.0,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        log.exception(
            "[rpc.push_vocab_extraction.failed] attempt=%s",
            payload.get("attempt_id", "?"),
        )


async def push_segment_insert(payload: dict) -> dict:
    """POST a generated segment to the gateway. Returns the response JSON.

    Raises on non-2xx so callers can fail-fast during generation.
    """
    r = await _http().post(
        f"{_GATEWAY_RPC_URL}/internal/segments",
        json=payload,
        headers=_rpc_headers(),
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


async def push_session_plan(
    session_id: str,
    segment_ids: list[str],
    scenario_summary: str | None = None,
) -> None:
    """Tell the gateway which segments to walk for this session.

    Raises on non-2xx so the generation worker can fail loudly instead of
    silently dropping the session plan.
    """
    r = await _http().post(
        f"{_GATEWAY_RPC_URL}/internal/session_plan",
        json={
            "session_id": session_id,
            "segment_ids": segment_ids,
            "scenario_summary": scenario_summary,
        },
        headers=_rpc_headers(),
        timeout=10.0,
    )
    r.raise_for_status()


async def push_generation_failed(session_id: str, error: str) -> None:
    """Tell the gateway that a generation job failed so it can flip
    `sessions.generation_state` from 'pending' to 'failed'.

    Best-effort: a failure here doesn't bubble up because the worker
    is already in its exception path. Without this call the row would
    stay 'pending' indefinitely and the frontend overlay would loop
    forever after any page reload.
    """
    try:
        r = await _http().post(
            f"{_GATEWAY_RPC_URL}/internal/generation_failed",
            json={"session_id": session_id, "error": error[:500]},
            headers=_rpc_headers(),
            timeout=5.0,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        log.exception(
            "[rpc.push_generation_failed.failed] session=%s; "
            "session row will stay generation_state=pending",
            session_id,
        )


GENERATION_CHANNEL = "generation_events"


async def publish_generation_event(event: dict) -> None:
    """Publish a generation progress/complete event for the gateway to fan
    out over the WebSocket. Lossy on purpose — late connectors miss events,
    which is fine because the session row also carries `generation_state`."""
    await _redis().publish(GENERATION_CHANNEL, json.dumps(event))


async def _write_redis(key: str, payload: str) -> None:
    await _redis().set(key, payload, ex=_RESULT_TTL_S)


async def _post(url: str, payload: str) -> None:
    try:
        await _http().post(
            url, content=payload, headers=_rpc_headers(), timeout=5.0
        )
    except httpx.HTTPError:
        # Redis fallback already written; gateway can recover from there.
        log.warning("[rpc._post.failed] url=%s — redis fallback in place", url)


async def aclose() -> None:
    """Tear down module-level clients (FastAPI lifespan shutdown)."""
    global _redis_client, _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
