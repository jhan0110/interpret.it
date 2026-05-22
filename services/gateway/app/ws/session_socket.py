"""WebSocket endpoint for an active session.

Frame discipline (per ARCHITECTURE.md §3):
- JSON envelopes are `{type, ts, payload}`; payload validated against the
  contracts discriminated union (`WSMessage`).
- Binary frames carry raw Opus/WebM bytes; they MUST be preceded by
  exactly one `audio.submit_header` envelope on the same connection.

The handler is intentionally fail-soft: protocol violations send an
`error` frame and keep the socket open, while server-side faults log
and close with code 1011.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.contracts.models import (
    AudioSubmission,
    ErrorPayload,
    WSAudioAckPayload,
    WSAudioSubmitHeader,
    WSGenerationCompletePayload,
    WSGenerationProgressPayload,
    WSMessage,
    WSSegmentPlayPayload,
    WSStateChangePayload,
)
from app.db import sessionmaker_factory
from app.engine.segment_picker import pick_segment_for_session
from app.engine.state_machine import InvalidTransition, next_state
from app.queue import enqueue_analysis
from app.session_manager import (
    SessionNotFound,
    persist_attempt,
    set_state,
    snapshot,
)
from app.storage import signed_get_url, upload_attempt

GENERATION_CHANNEL = "generation_events"
ANALYSIS_CHANNEL = "analysis_events"

log = logging.getLogger(__name__)

# Hardcoded for now — when sessions are configurable per learner-profile
# this should move onto SessionRow with a default.
SESSION_SEGMENT_TARGET = 12

router = APIRouter()


async def _send_envelope(ws: WebSocket, type_: str, payload: Any) -> None:
    await ws.send_json(
        {
            "type": type_,
            "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "payload": payload,
        }
    )


async def _send_error(
    ws: WebSocket,
    code: str,
    detail: str,
    *,
    attempt_id: UUID | None = None,
    session_id: UUID | None = None,
) -> None:
    payload = ErrorPayload(
        code=code,  # type: ignore[arg-type]
        detail=detail,
        attempt_id=attempt_id,
        session_id=session_id,
    )
    await _send_envelope(ws, "error", payload.model_dump(mode="json"))


async def _emit_state(
    ws: WebSocket,
    session_id: UUID,
    from_state: str,
    to_state: str,
    reason: str,
) -> None:
    payload = WSStateChangePayload(
        session_id=session_id,
        from_=from_state,  # type: ignore[arg-type]
        to=to_state,  # type: ignore[arg-type]
        reason=reason,
    )
    await _send_envelope(
        ws,
        "state.change",
        payload.model_dump(mode="json", by_alias=True),
    )
    log.info("[ws.state_change.sent] session=%s from=%s to=%s reason=%s", session_id, from_state, to_state, reason)


async def _generation_listener(ws: WebSocket, session_id: UUID) -> None:
    """Subscribe to Redis `generation_events`; forward matching frames to `ws`.

    Lossy on purpose — if the connection lags, we drop frames rather than
    backpressure. The session row carries `generation_state` so the client
    can still recover state by polling on reconnect.
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis = aioredis.from_url(redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(GENERATION_CHANNEL)
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                event = json.loads(message["data"])
            except (ValueError, KeyError):
                continue
            if str(event.get("session_id")) != str(session_id):
                continue
            if event.get("type") == "progress":
                payload = WSGenerationProgressPayload(
                    session_id=session_id,
                    ready=int(event.get("ready", 0)),
                    target=int(event.get("target", 10)),
                    state=event.get("state", "pending"),  # type: ignore[arg-type]
                )
                await _send_envelope(
                    ws, "generation.progress", payload.model_dump(mode="json")
                )
            elif event.get("type") == "complete":
                payload_c = WSGenerationCompletePayload(
                    session_id=session_id,
                    count=int(event.get("count", 0)),
                    scenario_summary=event.get("scenario_summary"),
                )
                await _send_envelope(
                    ws, "generation.complete", payload_c.model_dump(mode="json")
                )
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("generation_listener for session=%s failed", session_id)
    finally:
        try:
            await pubsub.unsubscribe(GENERATION_CHANNEL)
            await pubsub.close()
        finally:
            await redis.close()


async def _analysis_listener(ws: WebSocket, session_id: UUID) -> None:
    """Subscribe to Redis `analysis_events`; forward this session's frames to `ws`.

    The internal RPC endpoints (`app.api.internal`) publish prosody/semantic
    results and the `analyzing -> feedback` state change here once analysis
    lands. Each event carries a pre-built WS envelope, forwarded verbatim.
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    redis = aioredis.from_url(redis_url, decode_responses=True)
    pubsub = redis.pubsub()
    try:
        await pubsub.subscribe(ANALYSIS_CHANNEL)
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                event = json.loads(message["data"])
            except (ValueError, KeyError):
                continue
            if str(event.get("session_id")) != str(session_id):
                continue
            envelope = event.get("envelope")
            if isinstance(envelope, dict):
                await ws.send_json(envelope)
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("analysis_listener for session=%s failed", session_id)
    finally:
        try:
            await pubsub.unsubscribe(ANALYSIS_CHANNEL)
            await pubsub.close()
        finally:
            await redis.close()


async def _handle_feedback_next(
    ws: WebSocket,
    session_id: UUID,
    from_state: str,
    target_reached: bool,
) -> None:
    """Drive the post-feedback transition.

    Walks `feedback + feedback.next → next_segment + engine.pick_segment →
    listening` server-side, so the client only ever sends `segment.request`.
    If `target_reached`, ends at `complete` instead of picking again.
    """
    trans = next_state(from_state, "feedback.next", target_reached=target_reached)  # type: ignore[arg-type]
    await set_state(session_id, trans.to_state)
    await _emit_state(ws, session_id, trans.from_state, trans.to_state, trans.reason)
    if trans.to_state == "complete":
        return
    # `next_segment` is transient; we immediately fire engine.pick_segment.
    pick_trans = next_state(trans.to_state, "engine.pick_segment")
    await set_state(session_id, pick_trans.to_state)
    await _emit_state(
        ws, session_id, pick_trans.from_state, pick_trans.to_state, pick_trans.reason
    )
    await _pick_and_emit_segment(
        ws, session_id, rollback_state=from_state
    )


async def _pick_and_emit_segment(
    ws: WebSocket, session_id: UUID, rollback_state: str | None = None
) -> None:
    """Pick the next segment via the ladder selector and emit `segment.play`.

    On miss, roll the session state back to `rollback_state` (if given) so a
    pre-emptive state transition does not leave the session stuck, and send
    an `error` frame so the client can surface it.
    """
    sm = sessionmaker_factory()
    async with sm() as db:
        picked = await pick_segment_for_session(db, session_id)
    if picked is None:
        if rollback_state is not None:
            await set_state(session_id, rollback_state)
            await _emit_state(
                ws, session_id, "listening", rollback_state, "picker found no candidate"
            )
        await _send_error(
            ws,
            "invalid_state",
            "no candidate segment available for this learner / domain",
            session_id=session_id,
        )
        return
    audio_url = signed_get_url(picked.segment.audio_path)
    # Calibrated delay: 2000ms base + 500ms per difficulty level above 1,
    # clamped to [2000, 6500] for difficulty levels 1..10.
    delay_ms = 2000 + 500 * (picked.difficulty_level - 1)
    delay_ms = max(2000, min(6500, delay_ms))
    payload = WSSegmentPlayPayload(
        segment_id=picked.segment.id,
        audio_url=audio_url,
        duration_ms=0,
        difficulty_level=picked.difficulty_level,  # type: ignore[arg-type]
        delay_ms=delay_ms,
    )
    await _send_envelope(
        ws, "segment.play", payload.model_dump(mode="json")
    )


@router.websocket("/ws/sessions/{session_id}")
async def session_ws(ws: WebSocket, session_id: UUID) -> None:
    await ws.accept()

    pending_audio_header: AudioSubmission | None = None
    listener_task: asyncio.Task | None = None
    analysis_task: asyncio.Task | None = None

    try:
        # On connect, broadcast current state so reconnecting clients sync.
        try:
            snap = await snapshot(session_id)
        except SessionNotFound:
            await _send_error(ws, "invalid_state", "session not found", session_id=session_id)
            await ws.close(code=1008)
            return

        await _emit_state(ws, session_id, snap.state, snap.state, "connected")
        listener_task = asyncio.create_task(_generation_listener(ws, session_id))
        analysis_task = asyncio.create_task(_analysis_listener(ws, session_id))

        while True:
            msg = await ws.receive()

            if msg.get("type") == "websocket.disconnect":
                return

            if msg.get("bytes") is not None:
                blob = msg["bytes"]
                if pending_audio_header is None:
                    await _send_error(
                        ws,
                        "invalid_state",
                        "binary frame without preceding audio.submit_header",
                        session_id=session_id,
                    )
                    continue
                hdr = pending_audio_header
                pending_audio_header = None

                if len(blob) != hdr.byte_length:
                    await _send_error(
                        ws,
                        "invalid_payload",
                        f"byte length mismatch: header={hdr.byte_length} blob={len(blob)}",
                        attempt_id=hdr.attempt_id,
                        session_id=session_id,
                    )
                    continue

                try:
                    audio_key = upload_attempt(hdr.attempt_id, blob)
                except Exception as exc:  # boto3 / minio failure
                    log.exception("minio upload failed")
                    await _send_error(
                        ws,
                        "upload_failed",
                        f"upload error: {exc}",
                        attempt_id=hdr.attempt_id,
                        session_id=session_id,
                    )
                    continue

                try:
                    snap = await persist_attempt(
                        session_id=session_id,
                        attempt_id=hdr.attempt_id,
                        segment_id=hdr.segment_id,
                        audio_path=audio_key,
                        recorded_at=hdr.recorded_at,
                        duration_ms=hdr.duration_ms,
                    )
                except SessionNotFound:
                    await _send_error(
                        ws,
                        "invalid_state",
                        "session not found",
                        session_id=session_id,
                    )
                    continue

                trans = next_state(snap.state, "audio.submit")
                await set_state(session_id, trans.to_state)
                await _emit_state(ws, session_id, trans.from_state, trans.to_state, trans.reason)
                await _send_envelope(
                    ws,
                    "audio.ack",
                    WSAudioAckPayload(
                        attempt_id=hdr.attempt_id, audio_path=audio_key
                    ).model_dump(mode="json"),
                )

                await enqueue_analysis(
                    attempt_id=hdr.attempt_id,
                    segment_id=hdr.segment_id,
                    session_id=session_id,
                    learner_id=snap.learner_id,
                    audio_path=audio_key,
                    source_text=snap.current_source_text,
                    source_lang=snap.source_lang,
                    target_lang=snap.target_lang,
                    register=snap.current_register,
                    domain=snap.domain,
                    difficulty_level=snap.current_difficulty,
                )
                continue

            text = msg.get("text")
            if text is None:
                continue

            try:
                envelope = WSMessage.model_validate_json(text).root
            except ValidationError as exc:
                await _send_error(
                    ws,
                    "invalid_payload",
                    f"validation error: {exc.errors()[0].get('msg', 'invalid')}",
                    session_id=session_id,
                )
                continue

            if isinstance(envelope, WSAudioSubmitHeader):
                pending_audio_header = envelope.payload
                continue

            # All other control frames drive the state machine; pick the
            # right trigger by envelope type.
            trigger_map = {
                "session.start": "session.start",
                "segment.request": "segment.request",
                "recording.begin": "playback.finished",
                "session.complete": "session.complete",
            }
            trigger = trigger_map.get(envelope.type)
            if trigger is None:
                continue

            snap = await snapshot(session_id)

            # `segment.request` is the universal "give me the next segment"
            # entry. From `idle` the state machine accepts it directly; from
            # `feedback` we walk `feedback.next → engine.pick_segment` server-
            # side so the client doesn't need to know about either trigger.
            if envelope.type == "segment.request" and snap.state == "feedback":
                # A planned session ends at its plan length; an open-ended
                # (ladder-only) session falls back to SESSION_SEGMENT_TARGET.
                target = snap.planned_count or SESSION_SEGMENT_TARGET
                target_reached = snap.segment_count >= target
                await _handle_feedback_next(
                    ws, session_id, snap.state, target_reached
                )
                continue

            try:
                trans = next_state(snap.state, trigger)  # type: ignore[arg-type]
            except InvalidTransition as exc:
                await _send_error(ws, "invalid_state", str(exc), session_id=session_id)
                continue
            if trans.to_state != trans.from_state:
                await set_state(session_id, trans.to_state)
            await _emit_state(ws, session_id, trans.from_state, trans.to_state, trans.reason)

            if envelope.type == "segment.request":
                await _pick_and_emit_segment(
                    ws, session_id, rollback_state=trans.from_state
                )

    except WebSocketDisconnect:
        return
    except Exception:
        log.exception("websocket internal error")
        try:
            await ws.close(code=1011)
        except RuntimeError:
            pass
    finally:
        for task in (listener_task, analysis_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass
