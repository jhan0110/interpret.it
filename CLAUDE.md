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
- **No text during sessions.** The `(session)` route group must never render
  transcripts, subtitles, or any textual representation of audio content.
  All text review is gated behind session completion in `(review)`.
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
  CUDA libraries get pulled (saves ~3 GB / image).
- **Shared image.** `analysis`, `arq-semantic`, and `arq-generation` all reference
  `phase5-analysis:latest`. Only the `analysis` service declares `build:`.

## Compact Instructions
When compacting, always preserve: the stack table, the single-pipeline analysis
flow (Groq → prosody-derive → reference → TTS → evaluate → vocab-extract), the
"no text during sessions" rule, the contracts.json schema, the Content
generation parameters section, and the Learner-facing surface section.

<!-- PERSONAL SECTION: paste your personal CLAUDE.md component below this line -->
