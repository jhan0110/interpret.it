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

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.contracts.models import (
    AudioSubmission,
    ErrorPayload,
    WSAudioAckPayload,
    WSAudioSubmitHeader,
    WSMessage,
    WSSegmentPlayPayload,
    WSSegmentRequest,
    WSStateChangePayload,
)
from app.engine.state_machine import InvalidTransition, next_state
from app.queue import enqueue_analysis
from app.session_manager import (
    SessionNotFound,
    advance_segment,
    persist_attempt,
    pick_segment,
    set_state,
    snapshot,
)
from app.storage import signed_get_url, upload_attempt

log = logging.getLogger(__name__)

router = APIRouter()


def _delay_ms(difficulty_level: int) -> int:
    """Working-memory delay in ms: 2 s at level 1, scaling to 8 s at level 10."""
    return 2_000 + (difficulty_level - 1) * 667


async def _handle_segment_request(ws: WebSocket, session_id: UUID) -> None:
    """Pick the next segment and emit segment.play.

    Handles two cases:
    - idle → first segment: transition via "segment.request"
    - feedback → next segment: transition via "feedback.next" then "engine.pick_segment"
    """
    snap = await snapshot(session_id)

    if snap.state not in ("idle", "feedback"):
        await _send_error(
            ws,
            "invalid_state",
            f"segment.request not valid from state {snap.state!r}",
            session_id=session_id,
        )
        return

    if snap.state == "feedback":
        trans = next_state(snap.state, "feedback.next", target_reached=False)
        await set_state(session_id, trans.to_state)
        await _emit_state(ws, session_id, trans.from_state, trans.to_state, trans.reason)
        snap = await snapshot(session_id)

    seg = await pick_segment(session_id, snap.domain, snap.learner_id)

    if seg is None:
        await _send_error(
            ws,
            "internal",
            "no candidate segment available in this domain",
            session_id=session_id,
        )
        return

    snap = await advance_segment(session_id, seg.id)

    if snap.state == "idle":
        trans = next_state("idle", "segment.request")
    else:
        trans = next_state("next_segment", "engine.pick_segment", has_next_segment=True)
    await set_state(session_id, trans.to_state)
    await _emit_state(ws, session_id, trans.from_state, trans.to_state, trans.reason)

    audio_url = signed_get_url(seg.audio_path)
    await _send_envelope(
        ws,
        "segment.play",
        WSSegmentPlayPayload(
            segment_id=seg.id,
            audio_url=audio_url,
            duration_ms=0,
            difficulty_level=seg.difficulty_level,
            delay_ms=_delay_ms(seg.difficulty_level),
        ).model_dump(mode="json"),
    )


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


@router.websocket("/ws/sessions/{session_id}")
async def session_ws(ws: WebSocket, session_id: UUID) -> None:
    await ws.accept()

    pending_audio_header: AudioSubmission | None = None

    try:
        # On connect, broadcast current state so reconnecting clients sync.
        try:
            snap = await snapshot(session_id)
        except SessionNotFound:
            await _send_error(ws, "invalid_state", "session not found", session_id=session_id)
            await ws.close(code=1008)
            return

        await _emit_state(ws, session_id, snap.state, snap.state, "connected")

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

            if isinstance(envelope, WSSegmentRequest):
                await _handle_segment_request(ws, session_id)
                continue

            # Remaining control frames drive the state machine by trigger name.
            trigger_map = {
                "session.start": "session.start",
                "recording.begin": "playback.finished",
                "session.complete": "session.complete",
            }
            trigger = trigger_map.get(envelope.type)
            if trigger is None:
                continue

            snap = await snapshot(session_id)
            try:
                trans = next_state(snap.state, trigger)  # type: ignore[arg-type]
            except InvalidTransition as exc:
                await _send_error(ws, "invalid_state", str(exc), session_id=session_id)
                continue
            if trans.to_state != trans.from_state:
                await set_state(session_id, trans.to_state)
            await _emit_state(ws, session_id, trans.from_state, trans.to_state, trans.reason)

    except WebSocketDisconnect:
        return
    except Exception:
        log.exception("websocket internal error")
        try:
            await ws.close(code=1011)
        except RuntimeError:
            pass
