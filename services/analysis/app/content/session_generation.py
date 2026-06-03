"""arq job: produce a 5-pack of training segments for a session.

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
import os
from typing import Any

from app.content.generate import (
    GenerateParams,
    compute_generation_keys,
    generate_segments,
)
from app.embeddings import embed_texts
from app.rpc.gateway_client import (
    publish_generation_event,
    push_generated_set,
    push_generation_failed,
    push_segment_insert,
    push_session_plan,
    query_segment_pool,
)
from app.tts.elevenlabs_tts import generate_segment_audio
from app.content.durations import DURATION_BANDS

log = logging.getLogger(__name__)


def _pool_reuse_enabled() -> bool:
    """Shared-pool reuse kill-switch. Default on ("1"); set
    GENERATION_POOL_REUSE=0 to force every session to generate fresh."""
    return os.getenv("GENERATION_POOL_REUSE", "1") == "1"


def _coerce_params(payload: dict) -> GenerateParams:
    p = payload["params"]
    return GenerateParams(
        topics=tuple(p["topics"]),
        user_level=int(p["user_level"]),
        duration=p["duration"],
        direction=f"{payload['source_lang']}-{payload['target_lang']}",  # type: ignore[arg-type]
        n=int(p.get("n", 5)),
        current_context=p.get("current_context"),
    )


# Cap parallel TTS calls so a generation burst doesn't trip provider
# rate limits. 8 lets the canonical n=5 set (and up to n=8) synthesize in
# a single wave instead of two, shaving a TTS round-trip off cold-miss
# generation. OpenAI TTS (the default provider) comfortably handles this;
# lower it if a future provider has tighter RPS.
_TTS_CONCURRENCY = 8


async def run_generation(_ctx: dict, payload: dict) -> dict:
    """arq entrypoint. `payload` is the dict pushed by gateway.enqueue_generation.

    Earlier versions ran each segment sequentially (TTS → embed → RPC
    insert), which on a 10-pack routinely overran the worker's 300 s
    job_timeout cold; even at the new n=5 default the same
    parallel shape applies. We now:

    - Batch all embeddings in one `embed_texts(...)` call (instead of
      ten size-1 batches).
    - Fan out TTS across a bounded `asyncio.Semaphore` so concurrent
      calls don't trip OpenRouter rate limits.
    - Issue segment inserts as each (text, audio, embedding) trio is
      ready, so the gateway sees progress incrementally.
    """
    session_id = payload["session_id"]
    learner_id = payload["learner_id"]
    domain = payload["domain"]
    log.info("generation start session=%s learner=%s", session_id, learner_id)

    params = _coerce_params(payload)
    target_n = params.n  # used in the failure branch's progress event
    try:
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

        # ── Shared-pool reuse: if an unseen cohesive set already exists for
        # this exact (prompt, params) key, serve it — no LLM/TTS/embeddings.
        # The set is recorded against the learner's seen-ledger atomically
        # with the plan, so they're never served the same set twice.
        tmpl_hash, vars_hash = compute_generation_keys(params)
        if _pool_reuse_enabled():
            hit = await query_segment_pool(
                tmpl_hash, vars_hash, learner_id, params.n
            )
            if hit:
                reused_ids = [str(s) for s in hit["segment_ids"]]
                await push_session_plan(
                    session_id,
                    reused_ids,
                    hit.get("scenario_summary"),
                    generated_set_id=hit["set_id"],
                )
                await publish_generation_event(
                    {
                        "type": "complete",
                        "session_id": session_id,
                        "count": len(reused_ids),
                        "scenario_summary": hit.get("scenario_summary"),
                        "segment_ids": reused_ids,
                    }
                )
                log.info(
                    "generation reused session=%s set=%s count=%d (no LLM)",
                    session_id,
                    hit["set_id"],
                    len(reused_ids),
                )
                return {"ok": True, "count": len(reused_ids), "reused": True}

        result = generate_segments(params)
        segments = list(result.segments)

        # Single batched embedding call instead of n size-1 calls.
        # embed_texts is CPU-bound; route through to_thread to avoid
        # blocking the worker event loop.
        embeddings = await asyncio.to_thread(
            embed_texts, [s.source_text for s in segments]
        )

        sem = asyncio.Semaphore(_TTS_CONCURRENCY)

        async def _tts(idx: int, seg) -> tuple[int, str]:
            async with sem:
                key = await asyncio.to_thread(
                    generate_segment_audio,
                    seg.source_text,
                    seg.source_lang,
                    target_seconds=duration_spec.target_seconds,
                )
                return idx, key

        tts_tasks = [
            asyncio.create_task(_tts(i, seg)) for i, seg in enumerate(segments)
        ]

        # As each (TTS, embedding) pair lands, insert the segment and
        # bump the progress counter. We process completions in TTS
        # finish order — order doesn't matter because the gateway
        # records segment_ids by index and we re-sort below.
        segment_ids: list[str | None] = [None] * len(segments)
        completed = 0
        for fut in asyncio.as_completed(tts_tasks):
            idx, audio_key = await fut
            seg = segments[idx]
            embedding_vec = embeddings[idx]
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
            segment_ids[idx] = resp["segment_id"]
            completed += 1
            await publish_generation_event(
                {
                    "type": "progress",
                    "session_id": session_id,
                    "ready": completed,
                    "target": params.n,
                    "state": "pending",
                }
            )

        # All slots are guaranteed populated at this point; cast for mypy.
        final_ids: list[str] = [sid for sid in segment_ids if sid is not None]
        # Record the fresh set for future reuse, then assign it to this
        # session AND mark it seen for the learner in one atomic call.
        set_id = await push_generated_set(
            tmpl_hash, vars_hash, result.scenario_summary, final_ids
        )
        await push_session_plan(
            session_id,
            final_ids,
            result.scenario_summary,
            generated_set_id=set_id,
        )
        await publish_generation_event(
            {
                "type": "complete",
                "session_id": session_id,
                "count": len(final_ids),
                "scenario_summary": result.scenario_summary,
                "segment_ids": final_ids,
            }
        )
        log.info("generation complete session=%s count=%d", session_id, len(final_ids))
        return {"ok": True, "count": len(final_ids)}
    except Exception as exc:  # noqa: BLE001
        log.exception("generation failed session=%s: %s", session_id, exc)
        # Two-pronged failure signal:
        # 1. Publish a WS event so any currently-connected client
        #    sees the overlay flip from "pending" to "failed".
        # 2. POST to the gateway so the DB row flips
        #    generation_state→"failed". Without (2), a page reload
        #    after the failure would show the preparing overlay
        #    forever (the gateway re-emits "pending" on WS connect
        #    based on the stale DB value).
        await publish_generation_event(
            {
                "type": "progress",
                "session_id": session_id,
                "ready": 0,
                "target": target_n,
                "state": "failed",
            }
        )
        await push_generation_failed(session_id, str(exc))
        return {"ok": False, "error": str(exc)}
