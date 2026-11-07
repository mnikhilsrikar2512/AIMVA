# Database: connect, migrate, seed, test

Everything runs from the `backend` folder with one script, `scripts/db.py`. It reads the same `backend/.env` as the app,
so whatever `DATABASE_URL` says is the database it works on. Nothing here changes the schema by hand: the schema comes
only from the Alembic migrations in `backend/migrations` (currently up to `0010`).

| Command | What it does | Safe on real data? |
|---|---|---|
| `scripts/db.py check` | Connects, shows the server version, checks migrations are at the newest, every table and column exists, the user can write, and whether demo data is loaded. Exit code 0 = ready. | Yes, read-only |
| `scripts/db.py migrate` | Applies migrations (`alembic upgrade head`) the same way the app does on startup. | Yes |
| `scripts/db.py seed` | Loads the demo agency, client workspaces and people in every role (below). Runs once; `--fresh` reloads it. | Adds demo rows only |
| `scripts/db.py unseed` | Removes only the demo accounts and everything they own. Real accounts are untouched. | Yes |
| `scripts/db.py reset --confirm <dbname>` | **Drops every table in that database**, migrates from scratch. Add `--seed` to load demo data after. | **No** |

On the Mac, prefix each with `.venv/bin/python`, for example `.venv/bin/python scripts/db.py check`.

## 1. Point AIMVA at the database

In `backend/.env` (copy from `.env.example` if it doesn't exist):

```
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME
```

Hosted Postgres (Neon, Supabase, Render, RDS) hands out `postgres://...` or `postgresql://...`. Both work as they are;
AIMVA switches them to its driver itself. If the host requires SSL, add `?sslmode=require` at the end.
Leave `DATABASE_URL` empty to use the local SQLite file (`backend/data/aimva.db`).

No Postgres yet? A local one with Docker:

```
docker run -d --name aimva-pg -p 5432:5432 -e POSTGRES_USER=aimva -e POSTGRES_PASSWORD=aimva -e POSTGRES_DB=aimva postgres:16-alpine
# DATABASE_URL=postgresql://aimva:aimva@localhost:5432/aimva
```

## 2. First run on a new database

```
cd backend
.venv/bin/pip install -r requirements-dev.txt   # runtime deps (incl. the Postgres driver, psycopg) plus test tools
.venv/bin/python scripts/db.py check        # expect: connected, "no migrations applied yet"
.venv/bin/python scripts/db.py migrate      # empty database -> 0010
.venv/bin/python scripts/db.py seed         # prints the demo logins
.venv/bin/python scripts/db.py check        # expect: "Ready for testing."
```

Then start the app as usual (`./start.sh`) and sign in with a demo account.

## 3. The demo data

All demo people share one password, `Demo-pass-2026!` (change it with `--password` or `DEMO_PASSWORD`).
Their emails end in `@aimva-demo.example.com`, a reserved domain with no real inbox, which is also how `unseed` finds them.

| Sign in as | Who | What they can do |
|---|---|---|
| `owner@aimva-demo.example.com` | Priya Sharma, agency owner (Brightline Digital) | Owns all 3 client workspaces, plan `agency` |
| `admin@aimva-demo.example.com` | Rahul Verma | Admin in all 3 workspaces |
| `editor@aimva-demo.example.com` | Sneha Iyer | Editor in Smile Dental and Greenleaf, **not** BrightPath |
| `client.dental@aimva-demo.example.com` | Dr. Arjun Mehta | Client in Smile Dental: view-only, decides approvals |
| `client.realty@aimva-demo.example.com` | Kavya Reddy | Client in Greenleaf Realty |
| `solo@aimva-demo.example.com` | Imran Khan, Khan's Fitness Studio | Small business on its own, no agency |
| `empty@aimva-demo.example.com` | Neha Kapoor, Kapoor Interiors | Signed up two days ago, no data: for testing empty states |

Every business below has a brand kit, products, three pages (two published, one draft) with visits, three campaigns
(Meta active for 55 days, Google paused after 35, LinkedIn draft) with daily stats, leads spread over the last 60
days in every stage and source with history and won deals, WhatsApp threads plus follow-ups scheduled for the next
days, a voice agent with calls whose transcripts are in English, Hindi, Telugu or Tamil, four branded pictures
(drawn locally, no network), and two campaign decisions. Lead messages mix English, Hinglish, Hindi, Telugu and Tamil.

- **Smile Dental Clinic** (healthcare, 40 leads). Requires client approval: the first page is approved; the LinkedIn campaign and the second offer page are waiting for approval.
- **Greenleaf Realty** (real estate, 55 leads). Pending invite for `newhire@aimva-demo.example.com` as editor: sign up with that email to test accepting an invite.
- **BrightPath Coaching** (education, 30 leads).
- **Brightline Digital**, the agency owner's own account (28 leads), so `owner@` has data before switching to a client.
- **Khan's Fitness Studio**, `solo@` (22 leads).

`owner@`, `solo@` and `empty@` have onboarding answers. Public pages: `/s/demo-dental`, `/s/demo-realty`,
`/s/demo-coaching`, `/s/demo-solo`, `/s/demo-brightline`, plus `-2` for each second page. The same `--random-seed`
(default 42) always gives the same names and numbers. `unseed` also deletes the seeded pictures from `data/uploads`.

For the owner-only screens locally, put `ADMIN_EMAILS=owner@aimva-demo.example.com` in `backend/.env`.

What it does not include: connected Meta/Google/WhatsApp/Twilio accounts, real AI-generated pictures or videos, and AI
keys. Those need real keys and are tested by connecting them.

## 4. Things worth testing with it

- Switch between workspaces as the owner: leads, pages and campaigns must never mix.
- Editor can't open BrightPath; client can view but every change returns "view-only".
- Smile Dental: publishing the LinkedIn campaign is blocked until the client approves it.
- Accepting the invite, the trial/plan banner, analytics charts over 30 days, lead timelines, CSV export.

## 5. Starting over

```
.venv/bin/python scripts/db.py seed --fresh                     # demo data only, keeps everything else
.venv/bin/python scripts/db.py reset --confirm aimva --seed     # wipe the whole database (here named aimva)
```

`reset` refuses to run unless you type the database's name, refuses on `ENVIRONMENT=production` even with flags, and
refuses a database that isn't on this machine or in Docker unless you also pass `--remote`. It drops **every** table in
that database, including ones that aren't AIMVA's, so give AIMVA its own database.
`seed` and `unseed` refuse on `ENVIRONMENT=production` unless you pass `--allow-production` (for a staging server).

## 6. Running the automated tests against Postgres

The test suite uses its own throwaway SQLite file by default. To run it on Postgres, use a separate, empty database
(the tests drop and recreate every table):

```
TEST_DATABASE_URL=postgresql+psycopg://aimva:aimva@localhost:5432/aimva_pytest .venv/bin/python -m pytest -q
```

`tests/test_db_scripts.py` checks the demo data through the real API (sign-in for each role, workspace isolation,
view-only clients, approvals, invites, public pages) and that `unseed` leaves real accounts alone.

## 7. Production

Production uses the Docker stack in `deploy/` (see `docs/DEPLOY.md`): migrations run when the app starts, and backups
run nightly. Don't seed production. To check a production database from the server:
`docker compose exec app python scripts/db.py check`.
