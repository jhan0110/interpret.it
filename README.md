# interpretIt

**Real-time interpretation training for high-stakes settings.**

interpretIt is an audio-first practice platform for interpreters. You hear
a short spoken segment, interpret it aloud after a calibrated delay, and
get layered feedback — first on *how* you spoke (pace, pauses, fillers,
cognitive load), then on *what* you said (accuracy, omissions, register,
terminology). No transcript or subtitle is ever shown while you're
interpreting, so you train from audio alone the way real interpretation
works.

Content is generated on demand as **cohesive scenarios** — a set of
connected phrases that tell one unfolding story in your chosen domain and
difficulty — not random disconnected sentences.

> **Status:** active personal/research project. A gated demo runs at
> `interpretit.duckdns.org`.

---

## Features

- **Audio-only interpreting** — during listening and recording the UI
  shows no text. A full review (transcript, reference, errors, score)
  appears only *after* each attempt.
- **Layered feedback** — prosody lands within milliseconds of your
  recording (derived from word-level ASR timestamps), then the semantic
  evaluation follows.
- **Scenario generation** — pick domain(s), difficulty (1–5), and length;
  the LLM writes a coherent story-shaped set of phrases.
- **Difficulty ladder & mastery model** — performance feeds a per-domain,
  per-direction mastery score that adapts what you get next.
- **Vocabulary deck** — an SM-2 spaced-repetition deck seeded from your
  domains and grown automatically from terms you miss.
- **Memorization mode** — same-language practice (e.g. listen and recall
  in the same language) for retention drills.
- **Spend & rate controls** — per-learner daily attempt caps and a global
  daily API-spend ceiling, both enforced before any paid call.

### Domains
logistics · diplomacy · intelligence · operations · medical (civilian
clinical) · cyber

### Language pairs
**EN ↔ KO**, **EN ↔ ES**, **EN ↔ ZH** (both directions each), plus
same-language memorization.

---

## How it works

When you finish recording a segment, a single analysis pipeline runs:

1. **Transcription** — Groq Whisper returns text + word-level timestamps.
2. **Prosody** — pauses, fillers, pace, and silence are derived from those
   timestamps (no extra audio decode) and pushed to the UI immediately,
   lighting up the cognitive-load indicator.
3. **Reference generation** — the LLM produces a model interpretation
   (cached).
4. **Feedback TTS** — spoken feedback is synthesized.
5. **Evaluation** — the LLM scores register, precision, omissions, and
   tense, and returns a structured result.
6. **Vocabulary extraction** — on weaker attempts, missed terms are pulled
   out and added to your deck.

Audio moves as complete Opus blobs over a single binary WebSocket frame —
you record a whole segment, then ship it; there's no raw PCM streaming.

---

## Architecture

Two FastAPI services behind a shared Caddy gateway, plus one Next.js
frontend:

- **Gateway** (`services/gateway/`) — WebSocket sessions, the session state
  machine, difficulty ladder, and mastery model. Sole database writer.
- **Analysis** (`services/analysis/`) — ASR, LLM evaluation, vocabulary
  extraction, and content generation. Two background workers (`semantic`,
  `generation`) consume Redis queues.
- **Frontend** (`frontend/`) — Next.js App Router + React, Web Audio API.

| Layer            | Tool                                            |
|------------------|-------------------------------------------------|
| Frontend         | Next.js 16, React 19, Web Audio API             |
| Backend          | FastAPI (Python 3.12), Pydantic v2              |
| Transport        | WebSockets, binary Opus blobs                   |
| ASR              | Groq Whisper (`whisper-large-v3`)               |
| LLM + TTS        | Claude (Sonnet) + TTS via OpenRouter            |
| Embeddings       | sentence-transformers (multilingual-e5)         |
| Database         | PostgreSQL 16 + pgvector                        |
| Object store     | MinIO (S3-compatible)                           |
| Task queue       | Redis + arq                                     |
| Reverse proxy    | Caddy (TLS + basic-auth gate)                   |
| Containers       | Docker Compose                                  |

---

## Project writeup

### Problem & insight

Professional interpreting is a cognitively demanding skill — yet almost no
tools exist to practice it. Learners can study vocabulary and grammar, but
the actual task of real-time oral interpretation, under time pressure and
with authentic source material, has no structured training environment.
interpretIt addresses that gap directly: a purpose-built platform that
simulates the conditions of real interpretation work and gives structured,
actionable feedback.

### Evaluation & evidence

To validate the platform, feedback was collected from seven users with
direct interpreter experience: two who served as Korean Army interpreters,
four active interpreters at Cardinal Free Clinics, and one physician who
regularly works with Mandarin-speaking patients. Their responses informed
iteration on the feedback interface, grading criteria, and difficulty
calibration.

### Process, integrity & disclosure

AI was used in both the planning and implementation of this project. All
sources and external tools are credited, and the public repository includes
commit history documenting progress over time.

Two limitations are worth noting. The first is **latency**. Session
generation requires several sequential API calls, which introduces a delay
before the user can begin. A pre-generation buffer is already scaffolded
into the codebase — if two users request a session with identical
parameters, the second simply reuses the first user's generated session.
Feedback delay follows the same logic: by running grading in the background
across all five phrases, the user only waits for the final feedback before
receiving all results at once. The second limitation is **language
coverage**. The current TTS implementation uses OpenAI, which has meaningful
gaps in multilingual support; ElevenLabs would be a stronger long-term
choice and is a planned migration if resources allow.

---

## Getting started

### Prerequisites
- Docker + Docker Compose
- API keys: an **OpenRouter** key (Claude + TTS) and a **Groq** key
  (Whisper ASR; free tier is fine)

### 1. Configure the environment

```bash
cp .env.example .env
```

Then fill in `.env`. The required values for any run:

| Variable | What it is |
|----------|------------|
| `POSTGRES_PASSWORD` | Database password (no default — must be set) |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | Object-store credentials |
| `OPENROUTER_API_KEY` | Claude + TTS |
| `GROQ_API_KEY` | Whisper ASR |
| `INTERNAL_RPC_SECRET` | Gateway ↔ analysis bearer (`openssl rand -hex 32`) |
| `PUBLIC_DOMAIN` | Domain Caddy serves (e.g. `interpretit.local`) |
| `BASIC_AUTH_USER` / `BASIC_AUTH_PASSWORD_HASH` | Caddy gate (bcrypt hash) |
| `CORS_ALLOW_ORIGINS` / `MINIO_PUBLIC_ENDPOINT` | The browser-facing URL |

> Generate the basic-auth hash with
> `docker run --rm caddy:2-alpine caddy hash-password --plaintext '<pass>'`,
> then escape every `$` as `$$` in `.env` (see the comments in
> `.env.example`).
>
> To try the full flow without spending on APIs, set `USE_MOCKS=1` —
> the pipeline returns silent audio and fixed responses.

### 2. Bring up the stack

```bash
docker compose up -d
```

### 3. Run database migrations

```bash
docker compose exec gateway alembic upgrade head
```

### 4. Open the app

Visit `https://<PUBLIC_DOMAIN>/` and sign in with the basic-auth
credentials. (For local use, point `PUBLIC_DOMAIN` at a hostname that
resolves to your machine, e.g. add `interpretit.local` to `/etc/hosts`.)

---

## Using the app

1. **Log in** (`/login`) — enter a learner ID. It's remembered in your
   browser; this is a stand-in for real auth.
2. **Home** (`/learner/<id>`) — pick your working language pair, see your
   streak, minutes interpreted, and per-domain mastery, and jump into a
   feature.
3. **Start training** — choose **topic(s)**, **difficulty** (1–5),
   **direction**, and **length** (short / medium / long). The platform
   generates a coherent scenario (drawing from a shared pool, only calling
   the LLM when it needs fresh material).
4. **Interpret** — for each segment you'll hear the audio, then a calibrated
   pause, then record your interpretation aloud. No text is shown while you
   work.
5. **Review** — after each attempt (and at the end of the session) you get
   the transcript, a reference interpretation, flagged errors, and a score.
6. **Vocabulary deck** (`/vocab/<id>`) — review flashcards on an SM-2
   schedule; cards seed from your domains and from terms you miss.

---

## Local development

Source for `services/gateway/app`, `services/gateway/alembic`, and
`services/analysis/app` is bind-mounted into the containers, so Python
edits are live after a `docker compose restart <service>`. The frontend
is a built image — rebuild it to pick up changes.

Run pieces individually:

```bash
# Frontend
cd frontend && npm run dev                       # http://localhost:3000

# Gateway API
cd services/gateway && uvicorn app.main:app --reload --port 8000

# Analysis API
cd services/analysis && uvicorn app.main:app --reload --port 8001

# Background worker
cd services/analysis && arq app.worker.WorkerSettings

# Just the data stores
docker compose up postgres redis minio -d
```

### Tests & checks

```bash
# Python services (run inside the built images, or with a local venv)
pytest services/ --tb=short

# Lint / format
ruff check . && ruff format --check .

# Frontend
cd frontend && npx tsc --noEmit
```

---

## Configuration notes

- **Mock mode** — `USE_MOCKS=1` serves a deterministic fake pipeline (no
  paid API calls). Defaults to `0` (real).
- **WebSocket auth** — `WS_AUTH_REQUIRED=1` requires a short-lived signed
  token on the session socket; off by default.
- **Rate limits** — `ATTEMPT_QUOTA_DAILY` (per learner/day) and
  `MAX_DAILY_USD` (global spend ceiling) gate external-API traffic. The
  defaults are dev-friendly; tighten them for production.

## Project layout

```
services/gateway/    FastAPI — sessions, state machine, mastery (DB writer)
services/analysis/   FastAPI + arq workers — ASR, LLM eval, generation, vocab
frontend/            Next.js App Router frontend
contracts/           contracts.json — the canonical API schema
infra/               Caddyfile and deploy assets
docker-compose.yml   Full stack
```

`contracts/contracts.json` is the source of truth for API shapes;
`frontend/lib/contracts.ts` is generated from it
(`cd frontend && npm run gen-contracts`).

---

## Security

This is a training tool, not a hardened production system. The demo is
gated only by Caddy basic-auth. Never commit `.env` or any secret-bearing
file — keys for OpenRouter, Groq, and the data stores live there and are
gitignored. See `.env.example` for the full configuration surface.
