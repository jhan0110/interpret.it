# Phase 3 — Integration, Latency Budget, Ladder Smoke

This document records the Phase 3 verification pass on the Phase 2 build.
Live infra is not executed here; the checks below are static + unit-level.

## 1. Test coverage

Run from repo root:

```
cd services/gateway && PYTHONPATH=. python3 -m pytest tests/ -q
cd services/analysis && PYTHONPATH=. python3 -m pytest tests/ -q
cd frontend && npm run test
```

Current state:

| Suite                                                      | Tests | Status |
|------------------------------------------------------------|-------|--------|
| `services/gateway/tests/test_state_machine.py`             | 13    | pass   |
| `services/gateway/tests/test_difficulty_ladder.py`         | 12    | pass   |
| `services/gateway/tests/test_integration_attempt_flow.py`  | 7     | pass   |
| `services/analysis/tests/test_mocks.py`                    | 4     | pass   |
| `services/analysis/tests/test_cognitive_load.py`           | 6     | pass   |
| `frontend/lib/audio.test.ts`                               | 4     | pending† |

† vitest run requires `npm install` in the container with mic shims; the
test file is wired and will exercise FakeMediaRecorder in jsdom.

## 2. Latency budget (per CLAUDE.md and contracts)

Per-attempt timeout: **20s** (ARCHITECTURE.md ADR, commit `0586fb6`).

### Fast path — target ≤ 2 s

| Step                                  | Estimate | Notes                                        |
|---------------------------------------|----------|----------------------------------------------|
| Pull blob from MinIO                  | ~50 ms   | local LAN, ≤500 KB Opus blob                 |
| Decode → 16 kHz mono PCM (pydub)      | 80–150 ms| pure ffmpeg                                  |
| silero-vad inference                  | 200–500 ms| CPU; CUDA cuts ~4×                          |
| librosa beat track (fallback WPM)     | 100–200 ms| only when ASR tokens are absent             |
| Filler cross-reference                | <5 ms    | dict lookup over word tokens                 |
| Cognitive-load classifier             | <1 ms    | pure arithmetic                              |
| TTS for prosody feedback†             | 600–900 ms| ElevenLabs flash_v2_5                       |
| HTTP POST to gateway                  | 30–80 ms |                                              |
| **Total**                             | **~1.0–1.8 s** | within budget                          |

† For Phase 2 the prosody path uses a `placeholder/feedback.wav` MinIO
key — actual TTS hookup is wired in `app/worker.py:run_prosody` and
gated on per-deployment configuration. Real-world TTS adds the line
above; if it pushes total over 2 s, generate prosody TTS in parallel
with the librosa step (currently serialized).

### Full path — target ≤ 12 s

| Step                                  | Estimate    |
|---------------------------------------|-------------|
| Pull blob from MinIO                  | ~50 ms      |
| faster-whisper large-v3 transcription | 1.5–4.0 s   |
| Reference generation (Claude tool_use)| 2.0–4.0 s   |
| Semantic evaluation (Claude tool_use) | 2.0–5.0 s   |
| TTS for feedback + followup           | 1.0–2.0 s   |
| HTTP POST to gateway                  | 30–80 ms    |
| **Total**                             | **~6.5–15 s** |

The upper bound (~15 s) is at risk of breaching the 12 s target on
slow Claude calls + cold ASR. Mitigations available without contract
changes:

1. **Parallelize reference + ASR.** Reference generation does not need
   the transcript; today the worker runs ASR then reference
   sequentially. Switching to `asyncio.gather(asr, reference)` saves
   2–4 s.
2. **Cache reference per `segment_id`.** Reference text is segment-
   intrinsic and never changes; cache in Redis keyed on segment_id,
   skip the Claude call for every attempt after the first.
3. **Pre-warm the whisper model** in the worker startup hook (arq
   `on_startup`) so the first attempt doesn't pay the load cost.

These are recommended for Phase 4 but not blocking for Phase 3.

## 3. Difficulty ladder smoke test

`test_integration_attempt_flow.py::test_three_attempt_ladder_progression`
exercises a learner climbing 0.50 → 0.60 → 0.85 → 0.95 (semantic) with
prosody locked at "low". After three attempts mastery > 0.85 and the
final `difficulty_delta` is +1. The mirrored
`test_struggling_learner_drops_difficulty` confirms the descent path
(0.30 → 0.20 → 0.10 with high cognitive load) terminates with -1.

The selector (`select_next_segment`) is covered by recency-exclusion
and embedding-novelty tests in `test_difficulty_ladder.py`. The
bias-toward-weak-segments test runs 500 sampled picks and asserts
weak segments are chosen at >2× the rate of strong ones.

## 4. Static integrity checks

- **`contracts/contracts.json` ↔ pydantic mirrors:** Gateway has the
  full WS discriminated union; analysis has the result + request
  shapes only (it doesn't host a WS server).
- **`contracts/contracts.json` ↔ `frontend/lib/contracts.ts`:**
  Generated by `frontend/scripts/gen-contracts.ts` from the same
  source; `WSStateChange.payload.from` maps to Pydantic alias `from_`
  to avoid the Python keyword.
- **State machine ↔ ARCHITECTURE.md §5:** Transition table inlined as
  the test matrix in `test_state_machine.py`.
- **Difficulty ladder ↔ ARCHITECTURE.md §6:** `combined_score`,
  `update_mastery`, `difficulty_delta` formulas are copy-faithful;
  ivfflat index is created in alembic 0001.

## 5. Known gaps for Phase 4

1. **Live WS fan-out of analysis results.** Today the gateway
   internal-RPC endpoint persists results and updates mastery, but
   does not push `prosody.result` / `semantic.result` to the open WS
   for the matching session. A small Redis pub/sub bridge (publish in
   `api/internal.py`, subscribe in `ws/session_socket.py`) closes this
   loop without contract changes.
2. **`segment.play` emission.** The gateway selects/plays segments
   only in tests today; the WS handler does not yet emit
   `segment.play` upon entering `listening`. Needs to call the
   selector then sign a MinIO URL and `_send_envelope`.
3. **`mastery.update` emission.** Computed in `_close_if_ready` but
   not yet broadcast.
4. **Auth.** The session WS path takes no token; ARCHITECTURE.md
   marks this out of scope for Phase 1 explicitly.
5. **Frontend operator dashboard.** No UI yet to create a session
   (POST /sessions) and deep-link into the audio-only view. A trivial
   page can be added in Phase 4.

These are scoped intentionally — Phase 2/3 deliver the substrate;
Phase 4 wires the loops.

## 6. Merge plan

Worktree branch `worktree-orchestrator-main` is ahead of `main`. The
intended merge is a fast-forward at the end of Phase 3 review:

```
git checkout main
git merge --ff-only worktree-orchestrator-main
```

(Done manually by the human operator — agents do not push to main
per CLAUDE.md.)
