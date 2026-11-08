# Deploying AIMVA

One server runs everything: the app (API + web app in one Docker image), Postgres, Caddy for HTTPS, and a nightly
backup job. This was tested end to end on 2026-11-06: build, start, migrations, live updates across workers, backup
and restore. Caddy's HTTPS step could not be tested without a real domain.

## Before you start

- A Linux server with Docker (Ubuntu 24.04, 2 GB RAM is enough to start; Hetzner, DigitalOcean, AWS Lightsail…).
- A domain, with an **A record** pointing at the server's IP (for example `app.yourbrand.com`).
- Ports 80 and 443 open.
- Take the legacy Google Apps Script offline first: it stores plaintext passwords (see `legacy/`).

## First deploy

```sh
git clone <your repo> aimva && cd aimva/deploy     # or copy the folder to the server
cp .env.example .env && nano .env                 # fill in every value; see the comments
docker compose up -d --build
docker compose logs -f app                        # watch it start
```

If a setting is unsafe the app refuses to start and lists each problem. Open `https://<DOMAIN>/api/ready`: it should
answer `{"ok": true, "database": true}`. Then set up an uptime check (UptimeRobot, Better Stack) on `/api/health`.

## What runs where

| Piece | What it does |
| --- | --- |
| `app` | API and web app, `WEB_CONCURRENCY` worker processes. Migrations run on start under a lock. |
| `db` | Postgres 16, data in the `pgdata` volume. |
| `caddy` | HTTPS certificates (Let's Encrypt) for `DOMAIN` and for customers' verified custom domains. |
| `backup` | Database dump + uploads tarball every day at `BACKUP_HOUR_UTC`, kept `BACKUP_KEEP_DAYS` days in `deploy/backups/`. |

Several workers are safe: the agent scheduler runs on one at a time (database lease), rate limits live in the database,
and live updates reach every worker through Postgres `LISTEN/NOTIFY`.

## Backups

- Copy `deploy/backups/` off the server every day (rclone to S3/Backblaze, or your host's snapshots). A backup on the same disk is not a backup.
- Backup now: `docker compose exec backup sh /backup.sh once`
- Restore (replaces all data, asks you to type RESTORE): `./restore.sh backups/aimva-<stamp>.dump backups/uploads-<stamp>.tgz`
- Test a restore once a month on a spare server.

## Keys and rotating them

Two secrets, with different jobs. Keep an offline copy of both (a password manager is fine).

| Setting | Protects | If you change or lose it |
| --- | --- | --- |
| `SECRET_KEY` | Sign-in sessions, email codes, OAuth sign-in links | Everyone is signed out once. Nothing else is lost. |
| `TOKEN_ENCRYPTION_KEYS` | Stored tokens: Meta, Google, LinkedIn, WhatsApp, users' own AI keys | Rotate as below and nothing is lost. **Lose it** and every connected account must reconnect. |

Production won't start without `TOKEN_ENCRYPTION_KEYS`. It's a comma-separated list: the first key encrypts, the
others only decrypt, so you can rotate without anyone being cut off.

```sh
docker compose exec app python scripts/db.py tokens new-key   # prints a new key
# in deploy/.env: TOKEN_ENCRYPTION_KEYS=<new key>,<old key>   (first deploy: just <new key>)
docker compose up -d app                                      # restart with the new list
docker compose exec app python scripts/db.py tokens rotate    # re-encrypt every stored token with the new key
docker compose exec app python scripts/db.py tokens check     # 0 on an older key = done
# then remove the old key from the list and restart again
```

Servers set up before this key existed encrypted tokens with a key derived from `SECRET_KEY`. Those still open, so
the first deploy with `TOKEN_ENCRYPTION_KEYS` breaks nothing; run `tokens rotate` once, and from then on `SECRET_KEY`
can change without touching connected accounts. A database backup holds encrypted tokens only: restoring one needs
the keys that were in use when it was taken, so keep old keys until backups older than the rotation have expired
(`BACKUP_KEEP_DAYS`).

## Upgrades

```sh
git pull && cd deploy && docker compose up -d --build app
```

Migrations run automatically. Before a big upgrade, take a backup first.

## Error tracking and logs

- Set `SENTRY_DSN` (free tier at sentry.io, or self-hosted GlitchTip). No emails, cookies or IPs are sent.
- Logs are JSON lines: `docker compose logs app`. Every response has an `X-Request-ID`, and server errors show the same id to the user, so you can find the exact log line and Sentry event.

## Custom domains for customers' sites

Customers add a domain to a site, point a CNAME (or an A record for a bare domain) at your `DOMAIN`, and click Verify.
Caddy then gets a certificate on the first visit. Caddy asks AIMVA first, so it only does this for verified domains.

## Known limits

- Uploads live on the `appdata` volume, so this is one server. Before adding a second server, move uploads to object storage (S3, R2).
- The API docs (`/docs`) are off in production.
