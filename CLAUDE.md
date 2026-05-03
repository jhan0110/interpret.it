# Interpretation Training Platform

## Project Summary
Real-time interpretation training app for military/classified/research environments.
Users hear audio segments, interpret them aloud after a calibrated delay, and receive
layered feedback (prosody first, then semantic). No text shown during active sessions.

## Architecture
Two FastAPI services behind a shared gateway, one Next.js frontend.

- **Gateway service** (`services/gateway/`): WebSocket connections, session state machine,
  difficulty ladder, learner mastery model. Async-native, IO-bound.
- **Analysis service** (`services/analysis/`): ASR transcription, LLM evaluation,
  prosody extraction. CPU-heavy, runs behind a Redis (arq) task queue.
- **Frontend** (`frontend/`): Next.js 15 App Router + React 19. Two route groups:
  `(session)` for audio-only training mode, `(review)` for post-session transcripts.

## Stack
| Layer              | Tool                                    |
|--------------------|-----------------------------------------|
| Frontend           | Next.js 15, React 19, Web Audio API     |
| Backend            | FastAPI (Python 3.12), Pydantic v2      |
| Audio transport    | WebSockets, binary Opus blobs           |
| ASR                | faster-whisper (large-v3)               |
| TTS (cloud)        | ElevenLabs API (flash_v2_5)             |
| TTS (offline)      | Kokoro TTS or F5-TTS                    |
| LLM                | Claude Sonnet via Anthropic API         |
| Embeddings         | sentence-transformers (multilingual-e5) |
| NLP/syntax         | spaCy (ko_core_news_lg, en_core_web_trf)|
| Prosody/audio      | librosa, silero-vad, pydub              |
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
- **Parallel analysis paths.** When a user finishes recording, two pipelines
  fire simultaneously:
  1. **Fast path** (prosody): silero-vad + librosa on raw audio → pause/filler/pace
     metrics → immediate cognitive load feedback via TTS (target: <2s latency).
  2. **Full path** (semantic): faster-whisper transcription → Claude structured
     evaluation → pedagogical feedback → TTS (target: <12s latency).
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

## Compact Instructions
When compacting, always preserve: the stack table, the two parallel analysis
paths, the "no text during sessions" rule, and the contracts.json schema.

<!-- PERSONAL SECTION: paste your personal CLAUDE.md component below this line -->
