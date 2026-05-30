# Handoff — Interpretit Platform

State as of **2026-05-30**, post-review-sweep.
Deployed at `https://interpretit.duckdns.org` (DigitalOcean droplet,
Caddy + basicauth). Local dev stack works via `docker compose -p phase5 up -d`.

## TL;DR — what changed since the last handoff

A full repository code review (see `REVIEW_FINDINGS.md`, gitignored —
ask for a copy if you need it) surfaced 93 findings across security,
concurrency, math, infra, and frontend lifecycle. 9 CRITICAL +
20 HIGH + 30 MEDIUM + 30 LOW addressed in commit `2e01bf6` on `main`.
Live on the droplet. Tests: gateway 80/80, analysis 41/41, frontend
4/4, `tsc --noEmit` clean.

Cross-cutting themes addressed:

- **Security boundary tightened.** WS endpoint now supports
  signed-token auth (gated by `WS_AUTH_REQUIRED`, default off).
  Caddy no longer routes `/internal/*` publicly. `docker-compose.yml`
  refuses to start without `POSTGRES_PASSWORD` and MinIO root creds.
- **Concurrency hardened.** Async engine is lazy + per-loop. Mastery
  RMW uses `FOR UPDATE`. State transitions are conditional UPDATEs.
  Quota counters DECR back on overflow rather than over-counting.
- **Mastery math corrected.** `mean_wpm` denominator uses speech
  duration (not total), `filler_rate` is now unitless
  (`filler_count / word_count`). Korean filler lexicon trimmed from
  16 → 7 entries (high-frequency content words removed).
- **Generation parallelised.** Per-segment TTS+embed+RPC now run in
  `asyncio.as_completed` with `Semaphore(4)` instead of sequentially.
  Embedding batch size 1 → batched single call.
- **Frontend lifecycle hardened.** Level meter shares the recorder's
  stream (no second `getUserMedia`). Pending-replay flag survives
  audio element unmount. Summary timers tracked + cleared on
  component unmount.

See `CLAUDE.md` § "Recurring pitfalls" for the lessons learned —
written specifically so future contributors don't pay the same
debugging cost again.

## Live deployment state

`interpretit.duckdns.org` is on:

- 2 vCPU / 4 GB DO droplet, Falkenstein region (cheapest credible
  option after Hetzner availability checked out).
- Caddy 2.11 fronting everything (Let's Encrypt cert, basicauth
  gate: `admin / 153peers`).
- All 9 services healthy after the 2026-05-30 restart.
- `.env` has the 5 new required keys appended with backward-compatible
  defaults (`POSTGRES_PASSWORD=interpretit`,
  `MINIO_ROOT_USER/PASSWORD=minioadmin`, `MINIO_BUCKET=interpretit`,
  `WS_AUTH_REQUIRED=0`).

## Open follow-ups

Three items deferred from the review sweep. Each is non-blocking for
the current demo but documented here so the next contributor has
context.

### F1. Wire frontend to fetch WS auth tokens (then flip enforcement)

**Current state:** The gateway exposes `GET /sessions/{id}/ws_token`
which mints a 5-minute HMAC-SHA256 token bound to the session_id.
The WS endpoint (`/ws/sessions/{id}`) verifies the token when
`WS_AUTH_REQUIRED=1`. Right now `WS_AUTH_REQUIRED=0` because the
frontend doesn't fetch tokens — flipping it without a frontend
update locks everyone out.

**What needs to change in the frontend:**

1. Before opening the WebSocket in `SessionRunner.tsx` and
   `MemorizationRunner.tsx`, call:
   ```ts
   const res = await fetch(`/sessions/${sessionId}/ws_token`, {
     cache: "no-store",
   });
   const { token } = await res.json();
   ```
2. Append the token to the WS URL:
   ```ts
   const wsUrl = `${proto}//${location.host}/ws/sessions/${sessionId}?token=${token}`;
   ```
3. On reconnect (the existing exponential-backoff path in
   `lib/ws.ts`), re-mint the token before each connect attempt.
   The 5-minute window covers a short disconnect but not a long
   outage.

**Then on the droplet:** edit `.env` to set `WS_AUTH_REQUIRED=1`
and `docker compose restart gateway`. Verify in browser console
that the WS URL carries `?token=...`.

**Why this matters:** Without auth, anyone who knows or guesses a
session UUID can join an active session, listen to prosody/semantic
events, inject `session.complete`, or upload audio that counts
against another learner's daily quota. Currently mitigated by
basicauth on the Caddy gate, but that's a single-credential demo
posture — not a real auth boundary.

### F2. MinIO TTS cache key migration (orphaned objects)

**Current state:** As of commit `2e01bf6`, the TTS cache key shape
in `services/analysis/app/tts/elevenlabs_tts.py` changed from
`tts/<model-tag>/<hash>.mp3` to one that mixes in a prompt-version
salt (`_OPENAI_TTS_SYSTEM_PROMPT_VERSION = "v2"`):

```python
salt = f"{voice_id}:{_OPENAI_TTS_SYSTEM_PROMPT_VERSION}:{text}"
h = hashlib.sha256(salt.encode()).hexdigest()[:16]
return f"{prefix}/{_model_cache_tag()}/{h}.mp3"
```

**Consequence:** Audio cached before the change still lives in MinIO
under the old hash path. New requests for the same text+voice will
miss the cache and regenerate. The old files are orphaned but not
deleted.

**What to do:**

1. **Nothing urgent.** The orphans take ~10–50 KB each; even
   thousands of them are negligible against MinIO's available
   storage. They'll be re-cached on demand under the new key.
2. **If you want to clean up,** SSH to the droplet:
   ```bash
   docker compose exec minio mc alias set local http://minio:9000 \
     "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}"
   docker compose exec minio mc ls local/interpretit/tts/oa-gpt-audio/ | head
   ```
   Inspect first; only delete entries whose names match
   `^[0-9a-f]{16}\.mp3$` (the old 16-char hex from the pre-v2
   schema). Audit-then-delete; the bucket has no versioning.
3. **Future prompt edits:** bump `_OPENAI_TTS_SYSTEM_PROMPT_VERSION`
   in the same commit that changes the system prompt. The bump is
   what invalidates the cache; failing to bump means edits silently
   serve stale audio under the same key.

### F3. Rate-limit counter state survives restarts

**Current state:** Attempt and generation quotas (in
`app/attempt_quota.py` and `app/quota.py`) use Redis counters keyed
by `<learner_id>:<UTC-date>` with 24h TTL. As of the sweep, the
clients are module-level and cached, with `DECR` rollback on
rejection.

**Implication after a restart:** Existing counters in Redis are
intact. A user mid-session when gateway restarted doesn't lose
quota state. The TTL continues from where it left off — if a counter
was set with 25h remaining 30 min ago, it now has 24h 30min.

**Edge case worth knowing:** If you ever need to reset a learner's
quota intra-day (e.g., to debug a 429), the keys are:
```
attempt_quota:<learner_uuid>:YYYY-MM-DD
gen_quota:<learner_uuid>:YYYY-MM-DD
```
Delete with `docker compose exec redis redis-cli DEL <key>`. The
global spend ceiling has a different shape (`spend:YYYY-MM-DD`,
no learner segment) — see `services/analysis/app/spend.py`.

### F4. Off-host backup destination not configured

`scripts/backup_postgres.sh` dumps to `/backups/pgdump-<date>.sql.gz`
on the droplet itself, with 14-day retention. A droplet-wide failure
loses everything. The script's own comment says "untested backups
are not backups" — and currently backups also fail the geographic
test.

**To fix:** pick a destination (Backblaze B2 ~$6/TB-month, R2 free
egress, or S3 Standard) and add an `rclone copy` step at the end of
the script. Test with a fresh restore on a throwaway DB before
declaring done. Documented in DEPLOY.md as TODO; needs operator
decision on provider.

### F5. Korean filler lexicon trim is conservative

`H8` trimmed Korean fillers from 16 → 7 entries because the original
list included content words (`네`, `좀`, `약간`, etc.). The new list
is high-confidence-only (`어`, `음`, `아`, `그러니까`, `뭐냐`,
`그래서`, `그냥`). It may **under**-count fillers for some learners
and miss real disfluencies.

**To fix properly:** have a Korean linguist review against real
learner transcripts. Specific candidates worth re-evaluating:
- `이제` (now / well) — discourse marker but also temporal adverb
- `뭐` (what) — interrogative but also a stalling token
- `막` (just / about to) — strong filler reading in casual speech
Add entries only when both senses dominate-filler in interpretation
audio. Document the reasoning in the commit message.

## Quick orientation (unchanged from prior handoff)

- **What it is.** Real-time interpretation training for
  military/classified/research learners. Audio-only sessions,
  layered feedback (prosody first, then semantic).
- **Stack.** FastAPI gateway + FastAPI analysis (arq workers) +
  Next.js 16 frontend. Postgres 16 + pgvector + Redis (arq +
  pub/sub) + MinIO.
- **Contracts.** `contracts/contracts.json` is canonical.
  `frontend/lib/contracts.ts` is regenerated from JSON by
  `frontend/scripts/gen-contracts.ts` (with a built-in drift guard).
  `services/{analysis,gateway}/app/contracts/models.py` are
  **hand-maintained** — service-specific extensions live there.
  `scripts/gen_contracts.py` writes to
  `contracts/reference/pydantic_models_from_json.py` for diff
  purposes only, never to the live models (see CLAUDE.md §
  "Recurring pitfalls" for why).
- **Working agreements.** See `CLAUDE.md`. Notable rules:
  no text during `(session)` route, gateway is single DB writer,
  prompt templates re-read from disk on every call.

## Phase history

| Phase | Scope | State |
|---|---|---|
| 0 | Directive + `CLAUDE.md` | merged |
| 1 | `ARCHITECTURE.md` + contracts | merged |
| 2 | Gateway + Analysis services | merged |
| 3 | Frontend scaffold + integration tests | merged |
| 4 | Docker compose + perf + dashboard + seed | merged |
| 5 | Ladder picker + multi-segment + embeddings + paraphrase seeding | merged |
| 6 | Content generation (Claude+TTS pipeline, quota, WS progress, frontend params) | merged |
| 7 | Vocab deck + learner hub + memorization | merged |
| 8 | Production deployment (DO droplet, Caddy, DuckDNS, basicauth) | merged |
| 9 | **Review-sweep hardening — 93 findings, 63 files** | **merged (2026-05-30)** |

## Critical commands (cheatsheet)

```bash
# Local dev
docker compose -p phase5 up -d
docker compose -p phase5 restart gateway analysis arq-semantic arq-generation

# Run tests
docker run --rm -v "$PWD/services/gateway:/work" -w /work phase5-gateway:latest \
  sh -c "pip install pytest pytest-asyncio --quiet; PYTHONPATH=/work python -m pytest tests/ -q"
docker run --rm -v "$PWD/services/analysis:/work" -w /work phase5-analysis:latest \
  sh -c "pip install pytest pytest-asyncio --quiet; PYTHONPATH=/work python -m pytest tests/ -q"
cd frontend && npx vitest run
cd frontend && npx tsc --noEmit

# Regenerate frontend contracts after editing contracts.json
cd frontend && npm run gen-contracts
# (CI drift guard runs automatically; fails loudly if a JSON shape
#  lacks a matching TS export.)

# Diff the Python contract reference against live hand-maintained models
python3 scripts/gen_contracts.py  # writes contracts/reference/
diff contracts/reference/pydantic_models_from_json.py \
     services/gateway/app/contracts/models.py | less

# Deploy to droplet
git push origin main
ssh deploy@167.172.153.228 'cd ~/interpretit && git pull && \
  docker compose restart gateway analysis arq-semantic arq-generation'

# Inspect production logs
ssh deploy@167.172.153.228 'cd ~/interpretit && \
  docker compose logs --tail 100 gateway'
```
