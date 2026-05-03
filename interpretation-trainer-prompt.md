# SYSTEM DIRECTIVE: INTERPRETATION TRAINING PLATFORM

## PHASE 0 — WRITE CLAUDE.md FIRST

Before writing any code, create `CLAUDE.md` at the project root. This file is loaded into every Claude Code session and must survive context compaction. Keep it under 150 lines. Use this exact structure:

```markdown
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

```

After writing `CLAUDE.md`, confirm it exists and move to Phase 1. Do NOT begin any implementation code until Phase 1 contracts are approved.

---

## PHASE 1 — BLUEPRINTING & CONTRACTS

### 1.1 System Architecture Document

Agent 1 (Lead Architect) outputs a concise architecture doc covering:

- Directory structure (monorepo layout):
  ```
  /
  ├── CLAUDE.md
  ├── docker-compose.yml
  ├── contracts/
  │   └── contracts.json        # shared data shapes
  ├── frontend/                  # Next.js 15
  │   ├── app/
  │   │   ├── (session)/         # audio-only training mode
  │   │   └── (review)/          # post-session transcript review
  │   └── lib/
  │       ├── ws.ts              # WebSocket client
  │       └── audio.ts           # MediaRecorder + Web Audio
  ├── services/
  │   ├── gateway/               # FastAPI — WS, state machine, difficulty
  │   │   ├── app/
  │   │   │   ├── main.py
  │   │   │   ├── ws/            # WebSocket endpoint handlers
  │   │   │   ├── engine/        # scenario engine, difficulty ladder
  │   │   │   ├── models/        # SQLAlchemy + Pydantic models
  │   │   │   └── db.py
  │   │   ├── alembic/
  │   │   └── tests/
  │   └── analysis/              # FastAPI — ASR, LLM, prosody
  │       ├── app/
  │       │   ├── main.py
  │       │   ├── worker.py      # arq worker
  │       │   ├── asr/           # faster-whisper integration
  │       │   ├── evaluation/    # Claude structured evaluation
  │       │   ├── prosody/       # librosa + silero-vad
  │       │   ├── tts/           # ElevenLabs + Kokoro + splicing
  │       │   └── reference/     # reference generation layer
  │       └── tests/
  └── audio_assets/
      └── disfluencies/          # pre-recorded fillers, breaths, silence
  ```
- REST endpoints (health, session CRUD, learner profile)
- WebSocket message protocol (binary frames for audio, JSON frames for control)
- Database schema (learners, sessions, segments, attempts, mastery_scores)
- How the difficulty ladder state machine transitions work

### 1.2 contracts.json

Agents 1, 2, and 3 collaboratively define `contracts/contracts.json`. This file specifies the exact TypeScript/Pydantic-compatible JSON schemas for every data shape passed between services. At minimum:

```jsonc
{
  // Browser → Gateway (WebSocket binary frame header)
  "AudioSubmission": {
    "segment_id": "uuid",
    "audio_format": "opus/webm",
    "audio_blob": "binary",
    "recorded_at": "iso8601"
  },

  // Gateway → Analysis (arq job payload, via Redis)
  "AnalysisRequest": {
    "attempt_id": "uuid",
    "segment_id": "uuid",
    "audio_path": "string (MinIO key)",
    "source_text": "string",
    "source_lang": "ko | en",
    "target_lang": "ko | en",
    "register": "formal-military | formal-diplomatic | informal",
    "difficulty_level": "integer 1-10",
    "learner_id": "uuid"
  },

  // Analysis → Gateway (arq job result)
  "ProsodyResult": {
    "attempt_id": "uuid",
    "pause_count": "integer",
    "filler_count": "integer",
    "mean_wpm": "float",
    "silence_ratio": "float",
    "cognitive_load_estimate": "low | moderate | high | overloaded",
    "feedback_audio_path": "string (MinIO key)"
  },

  "SemanticResult": {
    "attempt_id": "uuid",
    "transcript": "string",
    "reference_translation": "string",
    "acceptable_paraphrases": ["string"],
    "errors": [
      {
        "type": "semantic_drift | lexical_gap | register_error | omission | tense_shift | precision_loss",
        "source_span": "string",
        "user_span": "string | null",
        "severity": "minor | moderate | critical",
        "explanation": "string"
      }
    ],
    "overall_score": "float 0-1",
    "feedback_text": "string",
    "feedback_audio_path": "string (MinIO key)",
    "followup_exercise": {
      "type": "repeat | rephrase | drill_term | contextual_qa",
      "prompt_text": "string",
      "prompt_audio_path": "string (MinIO key)"
    }
  },

  // Difficulty ladder update
  "MasteryUpdate": {
    "learner_id": "uuid",
    "segment_id": "uuid",
    "domain": "string",
    "old_mastery": "float 0-1",
    "new_mastery": "float 0-1",
    "difficulty_delta": "integer",
    "triggered_by": "prosody | semantic | both"
  }
}
```

**Gate:** Do not proceed to Phase 2 until Agent 1 explicitly approves the contracts and architecture doc. If any agent identifies a missing data shape or an ambiguity, resolve it now.

---

## PHASE 2 — PARALLEL COMPONENT DEVELOPMENT

All agents work in parallel, each in their own worktree. Use `isolation: worktree` in agent frontmatter or pass `--worktree` when dispatching.

### Agent 1: Lead Architect
**Domain:** Gateway service, database, state machine, Docker.
- Stand up PostgreSQL schema with Alembic migrations.
- Implement the session state machine (states: `idle → listening → recording → analyzing → feedback → next_segment | complete`).
- Implement the difficulty ladder: mastery-weighted segment selection using spaced repetition principles. Consume `MasteryUpdate` to adjust.
- Write `docker-compose.yml` with services: `frontend`, `gateway`, `analysis`, `arq-worker`, `postgres`, `redis`, `minio`.
- WebSocket endpoint on gateway that accepts `AudioSubmission`, uploads blob to MinIO, enqueues `AnalysisRequest` via arq, and pushes results back to the client as they arrive (prosody first, semantic second).

### Agent 2: Systems & Frontend Engineer
**Domain:** Frontend, audio I/O, segment delivery.
- Scaffold Next.js 15 app with two route groups: `(session)` and `(review)`.
- `(session)`: full-screen audio-only UI. Controls: play segment, wait (with visible timer for working memory delay), record, stop. NO TEXT anywhere. Use Web Audio API for visualization (waveform/volume meter only).
- `(review)`: unlocked after session completion. Shows transcripts, error annotations (from `SemanticResult.errors`), playback of original + user audio side by side, mastery progression chart.
- `lib/ws.ts`: WebSocket client that handles binary frames (audio) and JSON frames (control messages, results). Reconnection logic with exponential backoff.
- `lib/audio.ts`: `MediaRecorder` wrapper. Capture as `audio/webm;codecs=opus`. Return `Blob`. No raw PCM.
- Working Memory Trainer: configurable delay (2s–15s) between hearing a segment and the record button activating. Timer visible but NO transcript.

### Agent 3: AI/ML Pipeline Engineer
**Domain:** Analysis service, ASR, LLM evaluation, reference generation.
- `asr/`: faster-whisper integration. Accept MinIO audio path, return word-level timestamped transcript. Handle both Korean and English.
- `reference/`: Call Claude Sonnet to generate a canonical reference translation + 3–5 acceptable paraphrases, constrained by register and domain. Use structured output (tool_use) to enforce the schema.
- `evaluation/`: Call Claude Sonnet with the reference, paraphrases, and user transcript. Return a structured `SemanticResult` with typed errors. The prompt must explicitly ask for: register analysis, key-term coverage, temporal precision, omissions, and an overall 0–1 score.
- `tts/`: ElevenLabs integration for generating feedback audio and scenario playback. Save to MinIO. Include a `generate_feedback_audio(text, voice_id) -> minio_path` utility.
- Arq worker that listens for `AnalysisRequest` jobs, orchestrates the full pipeline (ASR → reference → evaluation → TTS feedback), and returns `SemanticResult`.
- **Mock first.** Before implementing real API calls, create mock responses that match the contract schemas exactly. Push mocks so Agent 2 can integrate the frontend immediately.

### Agent 4: Prosody & Audio Analytics
**Domain:** Prosody analysis, disfluency injection, speaker simulation.
- `prosody/`: Accept MinIO audio path. Run silero-vad for voice activity detection + librosa for tempo/RMS analysis. Return `ProsodyResult` with: pause count, filler count (cross-reference Whisper word-level timestamps with a filler lexicon for ko/en), mean WPM, silence ratio, cognitive load classification.
- This runs as a **separate arq job** from the semantic pipeline. Gateway enqueues both simultaneously. Prosody results return first.
- `tts/disfluency.py`: Waveform splicing engine. Accept a clean TTS audio file + a disfluency spec (list of `{timestamp_ms, type, duration_ms}`) and produce a modified audio file with spliced-in fillers/pauses/breaths from `audio_assets/disfluencies/`. Use pydub.
- `tts/speaker_profiles.py`: Define speaker simulation profiles (pace, accent, disfluency frequency) that map to difficulty levels. Level 1 = slow, clear, no disfluencies. Level 10 = fast, accented, frequent fillers, topic switches.
- Populate `audio_assets/disfluencies/` with placeholder silence clips of varying durations (200ms, 500ms, 1s, 2s) and a few filler sounds. Real assets can be recorded later.

---

## PHASE 3 — INTEGRATION & QA

Agent 1 orchestrates integration testing:

1. **End-to-end trace.** Agent 2 sends a mock audio blob from the browser through the WebSocket. Trace the payload:
   `AudioSubmission → MinIO upload → two parallel arq jobs → ProsodyResult arrives (~1-2s) → SemanticResult arrives (~8-12s) → both pushed to client via WS → UI updates`

2. **Contract validation.** Every JSON payload crossing a service boundary must validate against the Pydantic models in `contracts/`. If any field is missing or mistyped, the sending agent fixes it.

3. **No-text audit.** Agent 2 confirms that the `(session)` route group contains zero `<p>`, `<span>`, `<h*>`, or any element rendering text content derived from transcripts or translations. Timer numbers and button labels are allowed.

4. **Latency budget check.**
   - Prosody fast path: audio received → `ProsodyResult` + feedback TTS pushed to client. Target: <2 seconds.
   - Semantic full path: audio received → `SemanticResult` + feedback TTS pushed to client. Target: <12 seconds.
   - If either path exceeds target, identify the bottleneck (Whisper? LLM? TTS generation?) and propose a fix.

5. **Difficulty ladder smoke test.** Simulate 10 sequential attempts with varying scores. Confirm mastery updates correctly, difficulty increments/decrements, and segment selection avoids recently-seen segments.

---

## ORCHESTRATION INSTRUCTIONS

### How to run this

**Prerequisites:**
- Claude Code v2.1.142+
- Enable agent teams: `export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`
- tmux recommended for per-agent visibility

**Launch:**
```bash
claude agents --permission-mode plan --model opus --effort high
```

Then paste:
```
Create an agent team for the Interpretation Training Platform.

Read the system directive in this repo. Execute Phase 0 first (write CLAUDE.md),
then Phase 1 (architecture + contracts), then Phase 2 (parallel build), then Phase 3
(integration).

Team lead = Agent 1 (Architect): gateway service, DB, state machine, Docker, reviews all code.
Teammate 2 (Frontend): Next.js, WebSocket client, audio I/O, session/review UI.
Teammate 3 (ML Pipeline): analysis service, ASR, LLM evaluation, reference generation, TTS.
Teammate 4 (Audio): prosody analysis, disfluency splicing, speaker simulation.

All teammates use worktree isolation. Phase 2 is fully parallel.
Do not start Phase 2 until I approve the Phase 1 contracts.
```

### Naming sessions
Use `/rename` immediately after dispatch:
- `architect-lead`
- `frontend-audio`
- `ml-pipeline`
- `prosody-audio`

This makes agent view readable.
