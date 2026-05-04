# interpretit — System Architecture (Phase 1)

Companion to `CLAUDE.md` and `contracts/contracts.json`. This document is
prescriptive: deviations require a contract bump.

## 1. Directory Structure

Adopted as-specified in §1.1 of the system directive, plus the
following additions/clarifications:

```
/
├── CLAUDE.md
├── ARCHITECTURE.md                # this file
├── docker-compose.yml
├── contracts/
│   ├── contracts.json             # canonical schema (jsonc)
│   └── README.md                  # generation rules
├── frontend/                      # Next.js 15, React 19
│   ├── app/
│   │   ├── (session)/             # audio-only — no text
│   │   └── (review)/              # post-session transcript review
│   └── lib/
│       ├── ws.ts                  # WS client (binary + JSON frames)
│       ├── audio.ts               # MediaRecorder wrapper (Opus/WebM)
│       └── contracts.ts           # TS types generated from contracts.json
├── services/
│   ├── gateway/                   # FastAPI — WS, state machine, ladder
│   │   ├── app/
│   │   │   ├── main.py
│   │   │   ├── ws/                # WebSocket endpoint handlers
│   │   │   ├── engine/            # scenario engine, difficulty ladder
│   │   │   ├── models/            # SQLAlchemy + Pydantic models
│   │   │   ├── contracts/         # Pydantic models from contracts.json
│   │   │   ├── api/               # REST routers (health, sessions, learners)
│   │   │   └── db.py
│   │   ├── alembic/
│   │   └── tests/
│   └── analysis/                  # FastAPI — ASR, LLM, prosody, TTS
│       ├── app/
│       │   ├── main.py
│       │   ├── worker.py          # arq worker, queues: prosody + semantic
│       │   ├── asr/               # faster-whisper
│       │   ├── evaluation/        # Claude structured eval
│       │   ├── prosody/           # librosa + silero-vad
│       │   ├── tts/               # ElevenLabs + Kokoro + splicing
│       │   ├── reference/         # reference generation
│       │   └── contracts/         # Pydantic models from contracts.json
│       └── tests/
└── audio_assets/
    └── disfluencies/              # pre-recorded fillers, breaths, silence
```

**Deviations from §1.1:**
- Added `contracts/` Pydantic mirrors in each service rather than a
  shared library, to keep services independently deployable.
- Added `services/gateway/app/api/` since REST endpoints aren't trivial
  enough to leave in `main.py`.

## 2. REST Endpoints (Gateway)

All payloads conform to shapes in `contracts.json` (`REST.*` keys).

| Method | Path                              | Request body                | Response body                     |
|--------|-----------------------------------|-----------------------------|-----------------------------------|
| GET    | `/health`                         | —                           | `REST.HealthResponse`             |
| POST   | `/sessions`                       | `REST.PostSessionRequest`   | `REST.PostSessionResponse` (=Session) |
| GET    | `/sessions/{id}`                  | —                           | `REST.GetSessionResponse` (=Session) |
| POST   | `/sessions/{id}/complete`         | —                           | `REST.CompleteSessionResponse`    |
| GET    | `/learners/{id}`                  | —                           | `REST.GetLearnerResponse` (=Learner) |
| GET    | `/learners/{id}/mastery`          | —                           | `REST.GetLearnerMasteryResponse`  |

`/health` runs shallow checks against Postgres, Redis, and MinIO and
reports per-dependency status. Returns 200 unless `status == "down"`.

## 3. WebSocket Protocol

Endpoint: `GET /ws/sessions/{session_id}` (Gateway). Auth via signed
session token query param (out of scope for Phase 1).

**Frame discipline:**
- All control + result traffic is JSON envelopes:
  `{ "type": "<message_type>", "ts": "<iso8601>", "payload": {...} }`
- Binary frames carry **only** Opus/WebM bytes.
- A binary frame is **always** preceded by exactly one
  `audio.submit_header` JSON envelope on the same connection. The
  gateway pairs them by recency on that socket.

**Why header-then-binary (vs. multipart, or metadata-in-blob):**
A WebSocket binary frame has no native metadata channel. The two
alternatives were (a) base64 the audio inside the JSON, which inflates
~33% and burns CPU on a hot path, or (b) prepend a length-prefixed JSON
header inside the binary frame, which forces every consumer to
hand-parse bytes. Header-then-blob keeps audio as raw bytes (no copy),
keeps metadata in normal JSON, and is trivially testable.

### Message catalog

| Direction      | type                    | payload shape                  |
|----------------|-------------------------|--------------------------------|
| C→S            | `session.start`         | `{ session_id }`               |
| C→S            | `segment.request`       | `{ session_id }`               |
| C→S            | `recording.begin`       | `{ session_id, segment_id, attempt_id }` |
| C→S            | `audio.submit_header`   | `AudioSubmission`              |
| C→S (binary)   | _(no type — raw Opus)_  | bytes                          |
| C→S            | `session.complete`      | `{ session_id }`               |
| S→C            | `segment.play`          | `{ segment_id, audio_url, duration_ms, difficulty_level, delay_ms }` |
| S→C            | `audio.ack`             | `{ attempt_id, audio_path }`   |
| S→C            | `prosody.result`        | `ProsodyResult`                |
| S→C            | `semantic.result`       | `SemanticResult`               |
| S→C            | `mastery.update`        | `MasteryUpdate`                |
| S→C            | `state.change`          | `{ session_id, from, to, reason }` |
| S→C            | `session.complete_ack`  | `{ session_id, attempts_count, mean_score }` |
| S→C            | `error`                 | `{ code, detail, attempt_id?, session_id? }` |

## 4. Database Schema (PostgreSQL 16 + pgvector)

Owned by Gateway; Analysis is read-only against the same DB except for
writing into `attempts.prosody_result` / `attempts.semantic_result` via
internal Gateway RPC (Analysis never holds a DB write lock).

```
learners
  id              UUID PK
  display_name    TEXT NOT NULL
  primary_lang    TEXT NOT NULL CHECK (primary_lang IN ('ko','en'))
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()

segments
  id                UUID PK
  source_text       TEXT NOT NULL
  source_lang       TEXT NOT NULL CHECK (source_lang IN ('ko','en'))
  target_lang       TEXT NOT NULL CHECK (target_lang IN ('ko','en'))
  register          TEXT NOT NULL
  domain            TEXT NOT NULL
  difficulty_level  SMALLINT NOT NULL CHECK (difficulty_level BETWEEN 1 AND 10)
  audio_path        TEXT NOT NULL                -- MinIO key
  embedding_id      UUID NULL REFERENCES paraphrase_embeddings(id)
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
  INDEX (domain, difficulty_level)
  INDEX (target_lang, source_lang)

sessions
  id                  UUID PK
  learner_id          UUID NOT NULL REFERENCES learners(id)
  state               TEXT NOT NULL                -- see state machine
  domain              TEXT NOT NULL
  source_lang         TEXT NOT NULL
  target_lang         TEXT NOT NULL
  started_at          TIMESTAMPTZ NOT NULL DEFAULT now()
  completed_at        TIMESTAMPTZ NULL
  segment_count       INTEGER NOT NULL DEFAULT 0
  current_segment_id  UUID NULL REFERENCES segments(id)
  INDEX (learner_id, started_at DESC)

attempts
  id               UUID PK
  session_id       UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE
  segment_id       UUID NOT NULL REFERENCES segments(id)
  learner_id       UUID NOT NULL REFERENCES learners(id)
  audio_path       TEXT NOT NULL                -- MinIO key
  recorded_at      TIMESTAMPTZ NOT NULL
  prosody_result   JSONB NULL                   -- ProsodyResult
  semantic_result  JSONB NULL                   -- SemanticResult
  closed_at        TIMESTAMPTZ NULL
  INDEX (session_id, recorded_at)
  INDEX (learner_id, segment_id, recorded_at DESC)   -- recency lookup

mastery_scores
  learner_id       UUID NOT NULL REFERENCES learners(id)
  domain           TEXT NOT NULL
  mastery          REAL NOT NULL CHECK (mastery BETWEEN 0 AND 1)
  attempts_count   INTEGER NOT NULL DEFAULT 0
  last_attempt_at  TIMESTAMPTZ NOT NULL
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now()
  PRIMARY KEY (learner_id, domain)

paraphrase_embeddings                            -- pgvector
  id          UUID PK
  segment_id  UUID NOT NULL REFERENCES segments(id) ON DELETE CASCADE
  paraphrase  TEXT NOT NULL
  embedding   VECTOR(1024) NOT NULL              -- multilingual-e5-large
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
  INDEX USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)
  INDEX (segment_id)
```

`pgvector` powers spaced-repetition retrieval: when choosing the next
segment, the engine fetches the learner's last N attempts' embeddings
and excludes nearest neighbors above a similarity threshold.

## 5. Session State Machine

```
                       session.start
                            │
                            ▼
   ┌──── complete ◀──── idle ──── segment.request ──▶ listening
   │                     ▲                                │
   │                     │  next segment selected         │ audio finished +
   │                     │                                │ delay elapsed
   │                next_segment                          ▼
   │                     ▲                            recording
   │                     │                                │
   │              mastery.update emitted                  │ audio.submit_header
   │                     │                                │ + binary blob
   │                  feedback ◀── prosody+semantic ── analyzing
   │                     │              done
   │                     │
   └──── session.complete (any state) ───────────────────────────▶ complete
```

### Transitions

| from           | trigger                       | guard                              | to              | emitted WS                          |
|----------------|-------------------------------|------------------------------------|-----------------|-------------------------------------|
| —              | `session.start`               | session row exists, not complete   | `idle`          | `state.change`                      |
| `idle`         | `segment.request`             | next segment selectable            | `listening`     | `state.change` + `segment.play`     |
| `listening`    | client reports playback done  | working-memory delay elapsed       | `recording`     | `state.change`                      |
| `recording`    | `audio.submit_header`+binary  | blob size > 0, format=opus/webm    | `analyzing`     | `state.change` + `audio.ack`        |
| `analyzing`    | first of prosody/semantic     | result valid                       | `analyzing`     | `prosody.result` or `semantic.result` |
| `analyzing`    | both pipelines closed         | attempt persisted                  | `feedback`      | `state.change` + `mastery.update`   |
| `feedback`     | client requests next          | session.segment_count < target     | `next_segment`  | `state.change`                      |
| `feedback`     | client requests next          | session.segment_count ≥ target     | `complete`      | `state.change` + `session.complete_ack` |
| `next_segment` | engine picks segment          | always                             | `listening`     | `state.change` + `segment.play`     |
| any            | `session.complete`            | session not already complete       | `complete`      | `state.change` + `session.complete_ack` |
| any            | exception                     | —                                  | unchanged       | `error`                             |

The gateway persists state on every transition; reconnection re-emits
the current state to the client.

## 6. Difficulty Ladder

### 6.1 Mastery update formula

For an attempt that closes with prosody and semantic results:

```
score        = 0.7 * semantic.overall_score
             + 0.3 * prosody_score(prosody)
prosody_score(p) = 1.0                        if p.cognitive_load == "low"
                 = 0.75                       if "moderate"
                 = 0.40                       if "high"
                 = 0.10                       if "overloaded"

# EMA with α tied to attempts_count (more weight per attempt early on)
α            = max(0.15, 1.0 / (1 + attempts_count))
new_mastery  = clamp01(old_mastery + α * (score - old_mastery))
```

`difficulty_delta` for the next-segment selector:

```
delta = +1 if new_mastery > old_mastery and new_mastery >= 0.80
      = -1 if new_mastery < old_mastery and new_mastery <  0.50
      =  0 otherwise
```

A `MasteryUpdate` is emitted with `triggered_by = both` after both
results land. If only one result arrives within the per-attempt timeout
(default 30s), `triggered_by` reflects which path closed and the missing
score defaults to `old_mastery` (neutral contribution).

### 6.2 Next-segment selection

`difficulty_level` is bounded `[1, 10]`. Target level for the next
segment:

```
target_level = clamp(1, 10, current_level + difficulty_delta)
```

Candidate pool: segments matching `(domain, source_lang, target_lang,
register)` with `difficulty_level == target_level`. Apply filters in
order:

1. **Recency penalty.** Exclude segments attempted by this learner in
   the last 24h (lookup via `attempts` index `(learner_id, segment_id,
   recorded_at DESC)`).
2. **Semantic novelty.** Drop candidates whose `paraphrase_embeddings`
   cosine-similarity to any of the learner's last 5 attempts' segment
   embeddings exceeds 0.92.
3. **Mastery-weighted sampling.** From the survivors, sample weighted
   by `1 - segment_mastery_proxy`, where the proxy is the learner's
   rolling average score on that segment (or 0.5 if never attempted).
   This biases toward weaker areas without ever fully starving easier
   ones.
4. **Fallback.** If the pool empties, relax filter (2), then (1), then
   widen to `target_level ± 1`. Surface an `error` frame only if all
   relaxations fail.

Bounds: a learner cannot exceed `difficulty_level` 10 or drop below 1.
Promotion above level 8 additionally requires `attempts_count ≥ 3` at
the current level with mean score ≥ 0.75 (anti-fluke).

---

**Status:** implementable as drawn. No external dependencies beyond
those already in the stack table.
