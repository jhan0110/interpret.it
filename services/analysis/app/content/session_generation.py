"""arq job: produce a 10-pack of training segments for a session.

Wired in `app.worker` as `run_generation`. The job:

1. Generates the segment SET via `content.generate.generate_segments`
   (cohesive scenario, validated against the user's difficulty band).
2. For each generated segment, in parallel:
   - Calls ElevenLabs TTS (or mock silent mp3) to produce playback audio.
   - Computes a paraphrase embedding for the source text (mock vector
     in `USE_MOCKS=1` mode).
3. POSTs each segment to the gateway's `/internal/segments` endpoint,
   which inserts the SegmentRow + paraphrase rows and returns the
   deterministic segment_id.
4. Publishes `generation.progress` events to Redis after each segment
   lands, and a final `generation.complete` (with the ordered list of
   `segment_ids`) for the gateway to persist on the session row and
   broadcast over the WS.

The gateway separately consumes the Redis `generation_events` channel
and fans the frames out to WS connections; that wire-up lives in
`app/ws/session_socket.py`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.content.generate import GenerateParams, generate_segments
from app.embeddings import embed_texts
from app.rpc.gateway_client import (
    publish_generation_event,
    push_segment_insert,
)
from app.tts.elevenlabs_tts import generate_segment_audio
from app.content.durations import DURATION_BANDS

log = logging.getLogger(__name__)


def _coerce_params(payload: dict) -> GenerateParams:
    p = payload["params"]
    return GenerateParams(
        topics=tuple(p["topics"]),
        user_level=int(p["user_level"]),
        duration=p["duration"],
        direction=f"{payload['source_lang']}-{payload['target_lang']}",  # type: ignore[arg-type]
        n=int(p.get("n", 10)),
        current_context=p.get("current_context"),
    )


async def run_generation(_ctx: dict, payload: dict) -> dict:
    """arq entrypoint. `payload` is the dict pushed by gateway.enqueue_generation."""
    session_id = payload["session_id"]
    learner_id = payload["learner_id"]
    domain = payload["domain"]
    log.info("generation start session=%s learner=%s", session_id, learner_id)

    try:
        params = _coerce_params(payload)
        duration_spec = DURATION_BANDS[params.duration]
        await publish_generation_event(
            {
                "type": "progress",
                "session_id": session_id,
                "ready": 0,
                "target": params.n,
                "state": "pending",
            }
        )

        result = generate_segments(params)
        segment_ids: list[str] = []

        for idx, seg in enumerate(result.segments):
            audio_key = await asyncio.to_thread(
                generate_segment_audio,
                seg.source_text,
                seg.source_lang,
                target_seconds=duration_spec.target_seconds,
            )
            embedding_vec = embed_texts([seg.source_text])[0]
            insert_payload = {
                "source_text": seg.source_text,
                "source_lang": seg.source_lang,
                "target_lang": seg.target_lang,
                "register": seg.register,
                "domain": seg.domain,
                "difficulty_level": seg.difficulty_level,
                "audio_path": audio_key,
                "paraphrases": [
                    {"text": seg.source_text, "embedding": embedding_vec}
                ],
            }
            resp = await push_segment_insert(insert_payload)
            segment_ids.append(resp["segment_id"])
            await publish_generation_event(
                {
                    "type": "progress",
                    "session_id": session_id,
                    "ready": idx + 1,
                    "target": params.n,
                    "state": "pending",
                }
            )

        await _push_planned_segments(session_id, segment_ids, result.scenario_summary)
        await publish_generation_event(
            {
                "type": "complete",
                "session_id": session_id,
                "count": len(segment_ids),
                "scenario_summary": result.scenario_summary,
                "segment_ids": segment_ids,
            }
        )
        log.info("generation complete session=%s count=%d", session_id, len(segment_ids))
        return {"ok": True, "count": len(segment_ids)}
    except Exception as exc:  # noqa: BLE001
        log.exception("generation failed session=%s: %s", session_id, exc)
        await publish_generation_event(
            {
                "type": "progress",
                "session_id": session_id,
                "ready": 0,
                "target": 10,
                "state": "failed",
            }
        )
        return {"ok": False, "error": str(exc)}


async def _push_planned_segments(
    session_id: str, segment_ids: list[str], scenario_summary: str
) -> None:
    """Tell the gateway which segments to walk for this session."""
    import httpx
    import os

    gateway_url = os.getenv("GATEWAY_RPC_URL", "http://localhost:8000")
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(
            f"{gateway_url}/internal/session_plan",
            json={
                "session_id": session_id,
                "segment_ids": segment_ids,
                "scenario_summary": scenario_summary,
            },
        )
