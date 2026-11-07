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
