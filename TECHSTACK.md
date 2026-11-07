# AIMVA tech stack (locked 2026-11-07)

Source of truth: the Mac folder `~/Desktop/AIMVA`. The copies in the project files (`AIMVA/`, `aimva-backend-prod/`) are older snapshots. Nothing there is newer than the Mac.

Rule: no framework changes before the pilot. The suite passes on this stack (464 passed, 3 skipped, 2026-11-07).

## Layers

| Layer | Choice | Why |
|---|---|---|
| API | Python 3.13, FastAPI 0.128, Pydantic 2, Uvicorn (2 workers) | Already built and tested. Async enough for webhooks and SSE. |
| Database | Postgres 16 in production, SQLite only on a laptop. SQLAlchemy 2 + Alembic (10 migrations, run on startup under a lock) | Production refuses to start on SQLite (`config.problems()`). |
| Live updates | SSE, fanned out with Postgres LISTEN/NOTIFY (big payloads go through `live_events`) | Works across workers without Redis. |
| Background jobs | In-process scheduler with a DB lease | One server is enough for a pilot. No Celery or Redis. |
| Web app | React 18.3 + Vite 5.4, React Router 6, Tailwind v4 | Built and tested. |
| UI parts | Radix (`radix-ui` 1.8) + cmdk in shadcn-style wrappers, lucide icons, sonner toasts, framer-motion, recharts | Accessible menus and dialogs without a big kit. |
| Hosting | One Docker image (web build + API), docker compose with Postgres, Caddy (auto HTTPS) and nightly `pg_dump`. See `docs/DEPLOY.md` | A single VPS is cheapest and simplest for a pilot. |
| Files | Local volume `backend/data/uploads` | Fine on one server. |
| AI (text) | Gemini (`GEMINI_API_KEY`); Pollinations free tier as fallback when `FREE_AI=true` | |
| AI (image/video/edit) | fal.ai main key. Users can also bring their own fal, Replicate, OpenAI-compatible or ComfyUI connection | Models are swappable with `EDIT_MODEL_*`. |
| Voice | Twilio calls with `<Say>` | Sarvam was chosen for Indian-language voice but isn't wired in yet. |
| Messaging | WhatsApp Cloud API (Meta), with signed webhooks | |
| Ads | Meta, Google Ads, LinkedIn APIs | Only Meta has been touched for real. |
| Email | SMTP (`SMTP_USER`/`SMTP_PASSWORD`) | |
| Payments | Razorpay, switched off (`BILLING_ENFORCE`) | |
| Auth | Argon2 passwords, JWT cookie (Bearer token for the app), email code | |
| Monitoring | Sentry (`SENTRY_DSN`) + JSON logs + `/api/health` | |

## Changed today (backup: `_backup_2026-11-06/before_techstack.tgz`)

- `backend/requirements.txt` now holds runtime packages only. Test tools (pytest, pytest-cov, coverage, respx, pluggy, iniconfig, Pygments) moved to `backend/requirements-dev.txt`. The Docker image no longer installs the test tools.
- Removed `tomli` and `exceptiongroup`. They only matter on Python below 3.11.
- README and `docs/DATABASE.md` now say `pip install -r requirements-dev.txt` for local setup.
- `.dockerignore` now leaves out `_tmp_stage` and `docs`, so they don't go into the build.

## Won't hold up in production yet

0. **A fal.ai key is written in plain text** in `legacy/image-generation.html` and `legacy/video-generation.html`. Rotate that key now, and remove `legacy/` before launch.
1. **No git, no CI.** This is the biggest gap. You have no history, no rollback and no automatic test run. Backups are tarballs.
2. **`FREE_AI` defaults to true.** In production that sends customer prompts to a free public service that allows about 1 reply every 30 s for the whole server. Set `FREE_AI=false` and use a paid Gemini key.
3. **The tests run on SQLite.** Production runs on Postgres. Run the suite once with `TEST_DATABASE_URL=postgresql+psycopg://...` before launch.
4. **Uploads sit on the server's disk.** That's fine for one server. Move them to S3-compatible storage before you run two servers.
5. **Indian-language voice is Twilio `<Say>`.** Sarvam is the plan, but it isn't built.
6. **Not tested live:** fal, Google Ads, LinkedIn, Razorpay, HTTPS, real DNS.
7. **Vite 5 is an older major version.** It's fine for the pilot. Upgrade after launch, not before.

## Remove (only with your OK)

- `@react-three/drei`. It's in `package.json` but nothing imports it. This is held until the frontend thread is done with `npm install`.
- `legacy/` (with the Apps Script that exposes plaintext passwords). It stays until launch, by your choice, and must be removed before launch.
- The old snapshots in the project files (`AIMVA/`, `aimva-backend-prod/`), so nobody edits the wrong copy.
- `_backup_2026-11-06/before_techstack.tgz` and `_tmp_stage/`, once git exists. The other Nov 6 backups were deleted on 2026-11-07 at your request.
- Stale `__pycache__/*cpython-310*` files from an old Python.
