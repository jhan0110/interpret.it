# Handoff — Interpretit Platform

State as of 2026-05-15. Phases 0–4 complete and merged to `main`.

## Quick orientation

- **Stack**: Two FastAPI services (`gateway`, `analysis`) + Next.js 16 frontend, wired through Postgres + Redis + MinIO. Full architecture in `ARCHITECTURE.md`.
- **Authoritative contracts**: `contracts/contracts.json`. Pydantic models in each service and `frontend/lib/contracts.ts` mirror it. Do not change the JSON without updating all three mirrors.
- **Working agreements**: see `CLAUDE.md` — especially "no text during `(session)` route" and "gateway is the single DB writer".

## What's working

| Layer | What runs end-to-end |
|---|---|
| Gateway | Session state machine, difficulty ladder, WS handler (header+binary discipline), REST `/sessions` `/learners`, internal RPC for analysis results, Redis pub/sub fan-out to WS, `segment.play` emission, `mastery.update` broadcast, bearer-token WS auth (off by default) |
| Analysis | arq workers for prosody and semantic queues, faster-whisper ASR, silero-vad + librosa prosody, Claude tool-use for reference + evaluation, ElevenLabs TTS, centralised LLM client at `app/llm/client.py`, parallel ASR + reference, Redis cache for reference per `segment_id`, Whisper pre-warm at worker startup |
| Frontend | Operator dashboard at `/` (create-session form), audio-only session view at `/<sessionId>` with `AttemptRecorder` + WS client, review at `/review/<sessionId>` |
| Infra | `docker-compose.yml` covers all 8 services; `USE_MOCKS=1` default so no API keys needed for dev; alembic migration creates all 6 tables + pgvector ivfflat index |
| Tests | 42 Python tests (gateway 32, analysis 10), all green; 4 vitest tests for the recorder; full type-check clean |

## What's deferred / open

1. **`_pick_segment` is a stub** — it does exact-match on `(domain, difficulty_level)` and returns the first row. The full ladder-aware query (using recency exclusion + cosine novelty + mastery-weighted sampling) is Phase 5 work. See `services/gateway/app/ws/session_socket.py:_pick_segment` for the TODO marker.
2. **Paraphrase embedding bank not populated.** The `paraphrase_embeddings` table exists with a pgvector ivfflat index, but no embedding generation pipeline runs yet. Phase 5 deliverable.
3. **spaCy models not downloaded.** `ko_core_news_lg` and `en_core_web_trf` referenced in `CLAUDE.md` are not in the analysis Dockerfile. Add a `RUN python -m spacy download …` step when Phase 5 needs them.
4. **Disfluency injection (filler clip splicing) not built.** Architecture says pre-recorded clips spliced with pydub. No clips, no splicer. Phase 5/6.
5. **Placeholder segment audio.** `scripts/seed.py` uploads a non-playable blob. Real audio assets need to be uploaded to the same MinIO keys (`segments/<uuid>.webm`).
6. **WS auth is a shared secret only.** `WS_SECRET` env var; no per-user JWT. Real auth deferred per `ARCHITECTURE.md`.

## Outstanding minor fix (live as of this handoff)

`services/gateway/scripts/seed.py` exists but `services/gateway/Dockerfile` does not COPY it into the image — `docker compose run --rm gateway python -m scripts.seed` currently fails with `ModuleNotFoundError`. Fix: add `COPY scripts ./scripts` to the gateway Dockerfile alongside `COPY app ./app`.

## How to run end-to-end

```bash
# 1. Bring up infra
docker compose up postgres redis minio -d

# 2. Run migrations (first time only)
docker compose run --rm gateway alembic upgrade head

# 3. Seed dev data (after fixing the Dockerfile COPY)
docker compose build gateway
docker compose run --rm gateway python -m scripts.seed

# 4. Full stack
docker compose up --build
# Frontend: http://localhost:3000
# Gateway:  http://localhost:8000
# MinIO console: http://localhost:9001 (minioadmin / minioadmin)
```

Then on the dashboard at `/`:
- Learner ID: `00000000-0000-0000-0000-000000000001` (seeded)
- Domain: `logistics` or `diplomacy`
- Difficulty: 3, 4, 5, or 6

## Notable conventions

- **Worktrees for code changes.** Background agent sessions in this repo use `.claude/worktrees/<name>` and merge back via FF (or `--no-ff` when histories diverge). Never push to `main` from an agent.
- **One commit per logical change.** Conventional Commits.
- **No emojis in code or commits.**
- **Gateway is the only DB writer.** Analysis workers POST results to `/internal/*` endpoints; the gateway persists and publishes the Redis fan-out envelope. Workers never touch Postgres directly.
- **Audio blobs in MinIO, paths in Postgres.** Never store audio bytes in the DB.

## Phase 5 entry checklist (recommended)

1. Fix the gateway Dockerfile `COPY scripts` line.
2. `docker compose up --build` and run `scripts/seed.py` end-to-end to confirm the pipes are alive.
3. Replace `_pick_segment` with the ladder-aware query, using `select_next_segment()` from `app/engine/difficulty_ladder.py`. The selector is already tested — wire it to a real candidate query.
4. Build the embedding generation step: when a new segment is inserted, generate sentence-transformers embeddings for its source text + paraphrases and write to `paraphrase_embeddings`.
5. Add spaCy to the analysis image.
6. Add a `_seed_paraphrases` step to `scripts/seed.py` so the embedding-based novelty filter has data to work against.

## Files worth knowing about

- `CLAUDE.md` — project conventions (loaded into every session automatically)
- `ARCHITECTURE.md` — full Phase-1 blueprint including the state-machine transition table (§5) and difficulty ladder formulas (§6)
- `contracts/contracts.json` — wire shapes
- `docs/PHASE3_NOTES.md` — latency budget analysis, integration checks
- `services/gateway/app/engine/` — pure-logic state machine + difficulty ladder (no DB/IO; fully unit-tested)
- `services/analysis/app/llm/client.py` — single point of contact with the Anthropic SDK; swap LLM providers here

## Memory for future Claude sessions

Auto-memory is stored at `~/.claude/projects/-Users-jhyun-personal-projects-interpretit/memory/`. New conversations inherit it. If you discover a load-bearing fact the team has not documented, save it there rather than only telling the user.
