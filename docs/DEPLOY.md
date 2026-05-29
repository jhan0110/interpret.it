# Deployment runbook — single VPS, Caddy, basicauth

Target: **Hetzner CX22** (or any Linux VPS, 4 GB RAM minimum).
Total monthly cost: **~$5 VPS** + free DuckDNS subdomain (or ~$10/year
for a real `.com`/`.dev`).

This runbook walks through a from-scratch deployment of the interpretit
demo to a fresh VPS. All commands are run on the VPS as the `deploy`
user unless otherwise noted.

---

## 1. Provision the VPS

Hetzner Cloud Console → **New Server**:
- **Location**: Falkenstein (DE) or Ashburn (US) — closer to your demo
  audience.
- **Image**: Ubuntu 22.04.
- **Type**: CX22 (2 vCPU / 4 GB RAM / 40 GB SSD, €4.51/mo).
- **SSH key**: add the key whose private half you'll use to connect.
- **Networking**: enable IPv4 (default).
- **Firewall** (optional but recommended): allow inbound on 22 (SSH),
  80 (HTTP, for Let's Encrypt ACME challenge), 443 (HTTPS). Deny
  everything else.

Boot. Copy the public IPv4 address.

## 2. Domain DNS

**Option A — DuckDNS (free):**
1. Sign in at <https://duckdns.org> with GitHub or Google.
2. Create a subdomain — e.g. `interpretit-demo`. Your URL will be
   `interpretit-demo.duckdns.org`.
3. Paste the Hetzner public IP in the IP field → "update ip".
4. From your laptop: `dig +short interpretit-demo.duckdns.org` should
   return the Hetzner IP within 60 seconds.

**Option B — paid domain (Porkbun / Namecheap):**
- Create an `A` record `interpretit.<your-domain>` → VPS public IP.
- TTL 5 minutes.

## 3. Host setup

SSH in as root (Hetzner's default), then create the deploy user:

```bash
ssh root@<vps-ip>

# Create non-root deploy user
adduser --disabled-password --gecos "" deploy
usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys

# Install Docker
curl -fsSL https://get.docker.com | sh
usermod -aG docker deploy
apt install -y docker-compose-plugin

# 1 GB swap (smooths the embedding-model load on a 4 GB box)
fallocate -l 1G /swapfile && chmod 600 /swapfile
mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

exit
```

Reconnect as `deploy` for everything below:

```bash
ssh deploy@<vps-ip>
```

## 4. Clone + configure

```bash
git clone <repo-url> interpretit
cd interpretit

# Copy the template, populate every blank
cp .env.example .env
chmod 600 .env
nano .env
```

Required values in `.env`:

- `OPENROUTER_API_KEY` (from <https://openrouter.ai/keys>)
- `GROQ_API_KEY` (from <https://console.groq.com/keys>)
- `PUBLIC_DOMAIN` — the full domain Caddy serves on (e.g.
  `interpretit-demo.duckdns.org`)
- `CORS_ALLOW_ORIGINS` — `https://<your PUBLIC_DOMAIN>`
- `BASIC_AUTH_USER` — pilot username (any value)
- `BASIC_AUTH_PASSWORD_HASH` — generate with:
  ```bash
  docker run --rm caddy:2-alpine caddy hash-password --plaintext '<password>'
  ```
  **Escape every `$` as `$$`** before pasting into `.env` (compose
  treats single `$` as variable reference).
- `INTERNAL_RPC_SECRET` — `openssl rand -hex 32`

## 5. Remove the local-dry-run cert override

The dev Caddyfile uses `tls internal` (self-signed) so the local dry
run works without real DNS. Production wants Let's Encrypt:

```bash
nano infra/Caddyfile
```

Delete the `tls internal` line inside the site block. Save.

## 6. First boot

```bash
docker compose -p phase5 up -d
```

Watch the Caddy logs to confirm the Let's Encrypt cert acquisition:

```bash
docker compose -p phase5 logs -f caddy
```

Within ~30 seconds you should see lines like:
```
caddy | certificate obtained successfully
```

Apply DB migrations (only on first install or after `alembic` changes):

```bash
docker compose -p phase5 exec gateway alembic upgrade head
```

## 7. Smoke test

From a phone on cellular (not on the same wifi as the VPS):

1. Open `https://<your PUBLIC_DOMAIN>` in Safari/Chrome.
2. Expect a valid TLS padlock + a browser basicauth challenge.
3. Authenticate with `BASIC_AUTH_USER` + the plaintext password.
4. Land on the login page → paste the dev learner UUID
   `00000000-0000-0000-0000-000000000001` → "Open".
5. Pick **Memorization Practice** or **Interpretation Training** →
   start a small session (n=2) → record one attempt → confirm the
   feedback page renders.

If anything fails, check:
```bash
docker compose -p phase5 ps              # all services Up?
docker compose -p phase5 logs --tail 50 gateway
docker compose -p phase5 logs --tail 50 caddy
docker compose -p phase5 logs --tail 50 arq-semantic
```

## 8. Backups

Install the nightly cron:

```bash
mkdir -p /home/deploy/backups
crontab -e
```

Add the line:
```
0 3 * * * BACKUP_DIR=/home/deploy/backups /home/deploy/interpretit/scripts/backup_postgres.sh >> /home/deploy/backups/cron.log 2>&1
```

Test it once manually:

```bash
BACKUP_DIR=/home/deploy/backups /home/deploy/interpretit/scripts/backup_postgres.sh
ls /home/deploy/backups/
```

You should see a `pgdump-<date>.sql.gz` file.

**Restore drill** (do this once before relying on backups):

```bash
# Spin up a scratch DB inside postgres
docker compose -p phase5 exec postgres createdb -U interpretit interpretit_restore_test
gunzip -c /home/deploy/backups/pgdump-*.sql.gz \
  | docker compose -p phase5 exec -T postgres psql -U interpretit interpretit_restore_test
docker compose -p phase5 exec postgres psql -U interpretit interpretit_restore_test -c '\dt'
# Drop the scratch DB once verified
docker compose -p phase5 exec postgres dropdb -U interpretit interpretit_restore_test
```

If you want off-host backups: rsync `/home/deploy/backups/` to a
separate Hetzner storage box, S3, or B2 — out of scope here.

## 9. Adding more pilot users

```bash
docker compose -p phase5 exec caddy caddy hash-password --plaintext '<their-password>'
```

Copy the output. Edit `infra/Caddyfile` and add another line in the
`basicauth` block — one user per line:

```
basicauth {
    {$BASIC_AUTH_USER} {$BASIC_AUTH_PASSWORD_HASH}
    alice $2a$14$...
}
```

(Or move to a basicauth file directive once you have >3 users.)

Reload Caddy without restarting the whole stack:

```bash
docker compose -p phase5 exec caddy caddy reload --config /etc/caddy/Caddyfile
```

## 10. Updating the app

```bash
cd /home/deploy/interpretit
git pull
docker compose -p phase5 build
docker compose -p phase5 up -d
docker compose -p phase5 exec gateway alembic upgrade head   # if migrations
```

## 11. Known limitations

- **Single instance**: a host reboot or container crash interrupts
  any active sessions. The stack auto-restarts on reboot (every
  service has `restart: unless-stopped`); active learners will
  reconnect and resume from where they left off.
- **No off-host backups by default** — local cron only. Set up rsync
  before the data matters.
- **Basicauth is pre-shared credentials** — no per-user identity
  beyond what learner UUID the user pastes after auth. Sharing the
  same basicauth between many users is fine for a demo; for a
  pilot, give each user their own basicauth account so audit logs
  can distinguish them.
- **Audio recordings sit in MinIO unencrypted** beyond the host disk.
  For a real pilot with voice data, encrypt the MinIO data volume
  (LUKS) or migrate to S3 + SSE-KMS.

## 12. Cost monitoring

- OpenRouter dashboard: <https://openrouter.ai/activity> — daily
  spend tracking.
- The app also tracks spend in Redis (`spend:<UTC-date>` key) and
  has a hard ceiling at `MAX_DAILY_USD=$5` (configurable). When the
  ceiling is hit, TTS falls back to mock mode for the rest of the
  day; check `docker compose -p phase5 logs arq-semantic | grep
  "spend.ceiling"`.
- Per-learner daily attempt cap defaults to 100 (1000 for the dev
  learner UUID). Configure with `ATTEMPT_QUOTA_DAILY=`.
