# Interpretation Training Platform

## Project Summary
Real-time interpretation training app for military/classified/research environments.
Users hear audio segments, interpret them aloud after a calibrated delay, and receive
layered feedback (prosody first, then semantic). No text shown during active sessions.

## Architecture
Two FastAPI services behind a shared gateway, one Next.js frontend.

- **Gateway service** (`services/gateway/`): WebSocket connections, session state machine,
  difficulty ladder, learner mastery model. Async-native, IO-bound.
- **Analysis service** (`services/analysis/`): ASR transcription (Groq Whisper API),
  LLM evaluation, vocab extraction, content generation. Two arq workers (`semantic`,
  `generation`) consume from Redis queues.
- **Frontend** (`frontend/`): Next.js 16 App Router + React 19. Route layout:
  `/login` → `/learner/[id]` (home hub) → `/learner/[id]/train` → `/(session)/[id]` →
  `/review/[id]`, plus `/vocab/[id]` for the SRS deck.

## Stack
| Layer              | Tool                                    |
|--------------------|-----------------------------------------|
| Frontend           | Next.js 16, React 19, Web Audio API     |
| Backend            | FastAPI (Python 3.12), Pydantic v2      |
| Audio transport    | WebSockets, binary Opus blobs           |
| ASR                | Groq Whisper API (whisper-large-v3)     |
| TTS (cloud)        | ElevenLabs API (flash_v2_5)             |
| TTS (offline)      | Kokoro TTS or F5-TTS                    |
| LLM                | Claude Sonnet via Anthropic API         |
| Embeddings         | sentence-transformers (multilingual-e5) |
| Prosody            | Derived from Groq word timestamps       |
| Audio mixing       | pydub (for TTS disfluency splicing)     |
| Database           | PostgreSQL 16 + pgvector                |
| Blob storage       | MinIO (S3-compatible)                   |
| Task queue         | Redis + arq                             |
| Containers         | Docker Compose                          |

## Critical Commands
- Frontend dev: `cd frontend && npm run dev`
- Gateway service: `cd services/gateway && uvicorn app.main:app --reload --port 8000`
- Analysis service: `cd services/analysis && uvicorn app.main:app --reload --port 8001`
- Arq worker: `cd services/analysis && arq app.worker.WorkerSettings`
- Database: `docker compose up postgres redis minio -d`
- Migrations: `cd services/gateway && alembic upgrade head`
- Run all tests: `pytest services/ --tb=short`
- Run single test: `pytest services/gateway/tests/test_state_machine.py -k "test_name"`
- Lint: `ruff check . && ruff format --check .`
- Frontend lint: `cd frontend && npm run lint`
- Type check: `cd frontend && npx tsc --noEmit`

## Code Style
- Python: Ruff for linting+formatting. Type hints on all function signatures. Pydantic
  models for all API contracts. Async def for all FastAPI routes.
- TypeScript: Strict mode. Functional components only. No `any` types.
  Named exports, not default (except page.tsx / layout.tsx).
- Commits: Conventional Commits (feat:, fix:, refactor:, docs:, test:).
  One commit per logical change. Never commit to main directly.
- Tests: Every new module needs a test file. Use pytest + httpx for Python,
  Vitest for frontend.

## Key Architectural Rules
- **No text while interpreting.** During the `listening` and `recording`
  states the `(session)` route group must never render transcripts,
  subtitles, or any textual representation of the audio content — the
  learner interprets from audio alone. After each attempt the `feedback`
  state shows a full review-style breakdown (transcript, reference,
  errors, score); the post-session `(review)` route shows the same.
- **Single analysis pipeline.** When a user finishes recording, `run_semantic`
  on the `semantic` arq queue does the full sequence:
  1. **Groq Whisper transcription** (~1–2s) returns text + word-level timestamps
  2. **Prosody derivation** (~10 ms): pause/filler/pace/silence from the word
     timestamps via `app/prosody/word_prosody.py::compute_prosody_from_words`.
     Pushed to gateway immediately → cognitive-load indicator lights up.
  3. **Reference generation** (Claude, cached 24h in Redis)
  4. **ElevenLabs feedback TTS**
  5. **Claude `evaluate()`** → SemanticResult → push to gateway
  6. **Conditional vocab extraction** (separate `run_vocab_extraction` job
     enqueued post-eval if `score < 0.75` or `lexical_gap`/`omission` errors).
  
  The previous "fast path / full path" split was retired when faster-whisper
  was replaced with Groq — total latency target is now ~5–10s end-to-end.
- **Audio as Opus blobs, not streams.** Users record complete segment
  interpretations. The browser captures via MediaRecorder (Opus/WebM),
  ships the finished blob over a single binary WebSocket frame.
  No raw PCM streaming.
- **Disfluency injection is waveform splicing.** Agent 4 does NOT rely on TTS
  models to generate natural hesitations. Pre-record filler clips (어..., um,
  breath sounds, calibrated silence). Splice into TTS output with pydub at
  timestamps determined by the difficulty ladder.
- **Embeddings for retrieval, LLM for evaluation.** sentence-transformers
  handles the paraphrase bank (pgvector nearest-neighbor for spaced
  repetition). Actual interpretation quality evaluation uses Claude
  structured output (register, precision, omissions, tense).
- **Audio blobs in MinIO, not Postgres.** Store file paths in the DB.
- **Rate limits & spend ceiling.** Two layers gate external-API traffic:
  1. **Per-learner attempt cap** (`services/gateway/app/attempt_quota.py`) —
     Redis counter `attempt_quota:<learner>:<UTC-date>` with 24h TTL. Default
     `ATTEMPT_QUOTA_DAILY=100` per learner per UTC day. Dev learner has a
     1000/day override. Enforced at the WS `audio.submit` boundary BEFORE
     MinIO upload / DB write / analysis enqueue.
  2. **Global daily spend ceiling** (`services/analysis/app/spend.py`) —
     Redis counter `spend:<UTC-date>` in millicents. Every paid call site
     (Claude via OpenRouter, OpenAI/ElevenLabs TTS) increments by an estimated
     per-call cost. When the total reaches `MAX_DAILY_USD` (default `$5`),
     `is_over_ceiling()` returns True and TTS falls back to mock mode for
     the rest of the day. Per-kind cost overrides via `EST_COST_<KIND>` env
     vars (millicents).

  Both default to permissive dev-friendly values. Tighten for production
  via env vars; don't add new bypasses without a clear product reason.
- **Never commit `.env` or any secret-bearing file.** `.env` lives at the
  repo root and feeds `docker-compose.yml` via `${VAR:-default}`
  substitution. It contains live API keys (Anthropic, Groq, ElevenLabs)
  and must stay out of git — confirm `.gitignore` covers it before any
  commit that touches the file's directory. The same rule applies to
  any `.env.local`, `.env.bak`, `*.pem`, `*.key`, or credentials file.
  When restructuring the repo (renames, worktree removal, branch
  switches), surface `.env*` files to the user before performing
  destructive operations — they are not recoverable from git history.
- **Required env vars (no compose defaults).** As of the 2026-05-30
  review-sweep, the following are mandatory in `.env`; compose now
  uses `${VAR:?required}` so a missing value is a hard startup error:
  - `POSTGRES_PASSWORD`
  - `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD`
  - `INTERNAL_RPC_SECRET`
  - `BASIC_AUTH_PASSWORD_HASH`
  - `PUBLIC_DOMAIN`
  Defaults for non-secret keys (`POSTGRES_USER=interpretit`,
  `MINIO_BUCKET=interpretit`, `WS_AUTH_REQUIRED=0`) live in
  `.env.example`. When changing the required-env schema, update
  `.env.example` and `docs/DEPLOY.md` in the same commit so live
  operators get a clear migration path.
- **WebSocket auth (gated by `WS_AUTH_REQUIRED`).** The `/ws/sessions/{id}`
  endpoint can require a signed token query param. Mint via
  `GET /sessions/{id}/ws_token` (5-minute HMAC-SHA256 over
  `<session_id>|<exp>` with `INTERNAL_RPC_SECRET`). Defaults off
  (`WS_AUTH_REQUIRED=0`) so the existing frontend keeps working.
  Flip to `1` only after the frontend learns to fetch and append the
  token — see open follow-up in HANDOFF.md.

## Content generation parameters
The "daily training session" form collects:

- **Topic** (multi-select, ≥1): `logistics`, `diplomacy`, `intelligence`,
  `operations`, `medical`, `cyber`.
- **Difficulty** (1–5, user-facing). Maps to overlapping internal 1–10
  spreads via the table in `services/analysis/app/content/levels.py`:
  1=[1–3], 2=[2–5], 3=[4–7], 4=[6–9], 5=[8–10]. Sampling is weighted
  toward the peak of each band. The internal 1–10 ladder is the source
  of truth — never expose it to the operator.
- **Duration** (`short`/`medium`/`long`): expected ElevenLabs audio
  length in seconds — 10 / 20 / 40. The prompt receives target seconds;
  generation post-validates output length and retries once if >25% off.
- **Current context** (optional free text): operator-pasted bias toward
  today's news / ongoing operations. Injected as a prompt variable.

A generation request produces **10 cohesive phrases telling one story** —
not a random sequence. Even at high difficulty, the SET is narratively
coherent (same scenario, same actors, evolving events); per-phrase
disfluency/topic-switch behaviour is a TTS-layer concern, separate from
set-level cohesion.

**Quota: 2 generations / 20 phrases per learner per UTC day**, enforced
via Redis counter `gen_quota:<learner_id>:<YYYY-MM-DD>` with 24h TTL.
Override via `GEN_QUOTA_DAILY` env var or operator-only `?force=1`.

Phrases live in a **shared pool** keyed by `(domain, direction,
level-band, length-band, prompt-template-hash, prompt-vars-hash)`. Each
learner gets a random unseen sample; the LLM is only called when
`pool − learner_history < 10`. Learner history = any `AttemptRow` they
own referencing the segment.

Prompt templates live in `services/analysis/app/llm/prompts/*.md` —
Markdown with YAML front-matter (model, temperature, max_tokens, tool
schema). Jinja2-rendered, **re-read from disk on every call** so edits
take effect without restart.

## Learner-facing surface

- **Login** (`/login`) — UUID input, persisted to `localStorage['interpretit:learner_id']`.
  Temporary stand-in for real auth.
- **Home hub** (`/learner/[learnerId]`) — server-rendered; sections:
  1. Compact greeting (`Welcome back, {display_name}`)
  2. Feature grid (modular via `features.ts` registry) — Interpretation Training,
     Vocabulary Deck, Memorization Practice (coming-soon)
  3. Overview: streak tile + minutes-interpreted tile + per-domain mastery bars
  4. Recent sessions (latest 5)
- **Vocabulary Deck** (`/vocab/[learnerId]`) — SRS flashcard review (SM-2).
  Three DB tables: `vocab_entries`, `learner_topics`, `learner_vocab_deck`.
  Cards arrive from two signals: topic-seeded (`app/vocab/seeds.py`, ~30 terms /
  domain × 6 domains) and extraction (Claude identifies missed terms post-attempt,
  classifies as `knowledge_gap` vs `memory_gap`, re-surfaces the card).
- **Back-to-home arrow** on every feature page header (vocab deck + train form).

## Dev workflow

- **Bind mounts** are configured for `services/gateway/app`, `services/gateway/alembic`,
  and `services/analysis/app`. Python source edits are live in the container —
  just `docker compose restart <service>` to load. Rebuild is only needed when
  `pyproject.toml` or the Dockerfile change.
- **CPU-only torch.** The analysis Dockerfile installs torch from
  `download.pytorch.org/whl/cpu` before pip-installing the project so no NVIDIA
  CUDA libraries get pulled (saves ~3 GB / image). Dockerfile order is
  `COPY app` **before** `pip install .` — without that, setuptools can't
  find the `app` package at install time and the project's own package
  is missing from `site-packages`.
- **Shared image.** `analysis`, `arq-semantic`, and `arq-generation` all reference
  `phase5-analysis:latest`. Only the `analysis` service declares `build:`.
- **Contracts are hand-maintained.** `contracts/contracts.json` is the
  spec. `frontend/lib/contracts.ts` is auto-generated by
  `frontend/scripts/gen-contracts.ts` (which now includes a CI-style
  drift guard: every JSON shape must have a matching TS export, or the
  script exits non-zero). `services/{analysis,gateway}/app/contracts/models.py`
  are **hand-maintained** — service-specific extensions (the gateway's
  `_Strict` base, `GenerationParams`, `replays_budget`, etc.) live
  there. `scripts/gen_contracts.py` writes its output to
  `contracts/reference/pydantic_models_from_json.py` as a diff target,
  never to the live model files (see "Recurring pitfalls").

## Recurring pitfalls (do not repeat)

The 2026-05-30 review surfaced these. They cost real time; future
contributors should treat them as anti-patterns.

- **Never run a code generator that targets live, hand-maintained
  files.** `scripts/gen_contracts.py` used to write directly to
  `services/*/app/contracts/models.py` with a "DO NOT EDIT MANUALLY"
  header, but the live files had drifted to carry service-specific
  extensions the generator didn't know about. One regeneration deleted
  hundreds of lines of working code. Generators should write to a
  `_generated.py` or `reference/` path, and the hand-maintained file
  should `import *` from it (or diff against it). Never overwrite.
- **Default safety flags to opt-in (`"0"`), never opt-out (`"1"`).**
  `USE_MOCKS=1` as the default in `content/generate.py` meant any
  deployment that forgot to set the env var silently served mock
  phrases to real learners with real spend tracking. Every
  `os.getenv("FLAG", "X") == "1"` site must default `"X" = "0"`.
- **Hardcoded creds in `docker-compose.yml` are landmines.** `postgres`
  and `minio` shipped with `interpretit:interpretit` and
  `minioadmin:minioadmin` literals; once deployed publicly, anyone with
  the compose file owned the database and audio store. Use
  `${VAR:?required}` so the stack fails to start without a real value.
- **Beware async resources created at import time.** `db.py` used to
  call `create_async_engine(...)` at module top level, binding the
  pool to whichever asyncio loop happened to import the module first.
  Tests (one loop per test) and arq workers (their own loop) then hit
  "Future attached to a different loop" once concurrency rose. Lazy-
  factory pattern with a per-loop cache (`_loop_key() -> id(loop)`) is
  the right shape.
- **Pure-Python cosine on 1024-d vectors is ~50× slower than numpy.**
  The difficulty ladder ran filter loops on every `segment.request`.
  Hot-path math = numpy or pgvector; the gateway's pyproject.toml now
  lists numpy as a runtime dep.
- **Dimensional analysis matters for any "rate".** `filler_rate =
  filler_count / mean_wpm` gives `fillers · min / word`, which is not
  a rate. Calibrated thresholds against it were meaningless and
  unstable. Any quantity named `*_rate` should be unitless or
  events/time, and the docstring should state the unit.
- **State mutations belong at user commitment, not system intent.**
  The picker used to bump `segment_count` at pick time, so a WS
  failure between commit and `segment.play` silently consumed a plan
  slot. Now the count moves only when an attempt is persisted.
- **`SELECT ... FOR UPDATE` for any read-modify-write on shared rows.**
  `_close_if_ready` reads/writes `mastery_scores`; concurrent
  prosody+semantic POSTs interleave. Use `with_for_update()` on the
  read, or do an atomic conditional UPDATE.
- **Connection pooling is the default, not the optimization.** Every
  Redis publish and boto3 client used to be `from_url(...) + aclose()`
  per call. Module-level cached clients are the floor.
- **N+1 hides in "simple" list endpoints.** `list_learner_sessions`
  did `select(SessionRow).limit(5)` then `select(AttemptRow)` per row
  — six round-trips per dashboard load. Aggregate or `selectinload`
  in one shot.
- **Filler lexicons need linguistic review, not "more entries is
  better".** Korean's original lexicon included `네` (yes), `좀`
  (a little), `약간` (somewhat) — all high-frequency content words.
  Cognitive-load classification was biased toward "overloaded" for
  routinely fluent speakers. Be conservative; extensions need a
  Korean linguist sign-off.
- **Tests that mock the layer they verify add zero value.**
  `test_content_generate.py` mocked both `render_template` and
  `run_template`, so the test only confirmed they were glued
  together. Mock at the trust boundary (LLM API), never at the same
  layer as the code under test.
- **Stop conflating "process alive" with "process making progress".**
  `docker-buildx bake` ran 50 minutes at 0% CPU with flat RSS,
  producing no events. Set explicit timeouts on long-running probes
  and treat idle subprocesses as suspect after a clear threshold.
- **An "auto-generated" header is a contract, not a comment.** If a
  file says "DO NOT EDIT MANUALLY", regenerating must be safe and
  lossless. If it isn't, delete the generator or fix it before
  shipping.

When a future review surfaces a new pitfall, append it here. The
goal is not exhaustive theory — it is "we already paid for this
lesson, don't pay again."

## Compact Instructions
When compacting, always preserve: the stack table, the single-pipeline analysis
flow (Groq → prosody-derive → reference → TTS → evaluate → vocab-extract), the
"no text while interpreting" rule, the contracts.json schema, the Content
generation parameters section, and the Learner-facing surface section.

<!-- PERSONAL SECTION: paste your personal CLAUDE.md component below this line -->
