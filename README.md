# AIMVA — AI Marketing & Voice Automation

One portal for content creation, ad campaigns, landing pages and hosting, WhatsApp, an AI voice agent, lead sync and analytics, all sharing one lead database.

```
backend/   FastAPI + SQLite (auth, modules, integrations)
frontend/  React + Vite + Tailwind
docs/      Integration setup guide
legacy/    The original HTML prototype (kept for reference)
```

## Run it

```bash
./start.sh
```

Then open http://localhost:5173. The script starts the API on :8000 and the web app on :5173.

First-time setup (already done on this Mac):

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cd ../frontend && npm install
```

Node.js lives in `~/.local/node`. Add it to your PATH with `export PATH=$HOME/.local/node/bin:$PATH`.

## Tests

```bash
cd backend && .venv/bin/python -m pytest
```

About 880 tests run against a throwaway database with all third-party APIs and DNS mocked (respx), so no keys or network are needed, on any date. They cover:
- auth security
- per-user data isolation
- every module's API
- the OAuth flow
- webhook handling and signature checks (WhatsApp, Twilio)
- database migrations
- failure paths (provider errors, timeouts, bad input)

Add `--cov=app` for a coverage report.

## Command Center

**Command Center** (`/app/command`) shows every product, campaign and landing page in one place:
- **Products** group what you sell. Campaigns (Meta, Google, LinkedIn or offline) and pages are linked to them.
- **Attribution:** leads from ad lead forms are linked automatically. For landing pages, use each campaign's tracking link (`…/s/<page>?aimva_c=<campaign id>`).
- **Results:** Google, LinkedIn and offline results can be entered by hand. Running totals are spread over the days the campaign ran.
- **Next steps** are plain rules that show the numbers behind them: pause, scale, move budget, trim to budget, refresh creative, fix the page, call hot leads, follow up. Accept, snooze or dismiss each one. Safe actions (pause, budgets, voice-agent calls) run in one click, and every decision is logged.

## Agents that do the work for you

Five work agents (`backend/app/agents/`) take the busy work off people. There's no separate Agents page: each shows up where its work lands, and every run is logged step by step (`/api/agents/jobs`).
- **Launch Agent** (Dashboard → *Launch with AIMVA*): from a website link, a brochure or one sentence it reads the facts, creates the Command Center product, builds the landing page, runs the Page Fixer, drafts Meta/Google/LinkedIn campaigns with copy and a tracked link, sets up a call-back voice assistant and turns on the Lead Concierge. Ads always stay drafts until you press Publish, and the page goes live only if you tick *Put the page live*.
- **Lead Concierge** (switch on the Leads page): every new form or ad lead gets a WhatsApp welcome within seconds, then follow-ups on day 2 and day 7. They stop as soon as the lead replies, or is marked qualified, won or lost. Without a connected WhatsApp number nothing is faked: each message is drafted on the lead, ready to send. The message texts can be changed (`PUT /api/agents/concierge`).
- **Campaign Autopilot** (switch in Command Center): checks campaigns every morning using the Command Center's own suggestions. *Suggest* changes nothing. *Fix safely* pauses campaigns spending with no leads and trims overspend by itself, at most 3 actions a day. It never raises budgets unless you allow it (capped at +20%) and never places calls. Every action appears in the decision log.
- **Weekly Report**: Monday morning summary of leads, spend and next steps, emailed when SMTP is set up and always on the Dashboard feed.
- **Page Fixer**: fixes the safe launch issues on every new page (mobile viewport tag, title, search description, image alt text, empty links, unreadable button text, form labels). Wording, prices and claims are always left for you. It only reports a fix it actually made.
- **Page score** (`backend/app/page_score.py`): every new page is marked out of 10 on six parts: the offer is clear, visitors know what to do next, nothing a visitor could doubt, works on a phone, easy for everyone to use, looks and sounds like the brand. A page passes at an average of 8 with nothing under 7, and fails however high it scores if it shows a number or quote the owner never gave, a broken picture, or breaks a rule the owner set (their brand colours, a word they never use). Pages left on the default colours take the Brand Kit colours. If a page the AI wrote still fails after the safe fixes, the writer gets up to three rewrites aimed at exactly what's missing, and a rewrite is kept only when the score rises and adds no must-fix problem. Showcase pages are never rewritten. The score shows in the page's checks panel (`GET /api/sites/{id}/audit`). Each rewrite is one extra AI call.
- **Scheduler:** one background thread runs follow-ups every minute, Autopilot daily after 9:00 and the report on Mondays (`AGENTS_SCHEDULER`, `TZ_OFFSET_MINUTES` in `.env`).

## AI engine (no API key needed)

All AI writing goes through `backend/app/ai_engine.py`, one task each: page writer, site reader, copywriter, prompt artist, call assistant, analyst and template curator.
- **Engine chain:** each task tries your own provider, then the owner's shared key (`GEMINI_API_KEY`), then **AIMVA free AI** (keyless Pollinations text, `FREE_AI=true`), then built-in rules, which always work.
- **Free AI limits:** it's shared by the whole server (about one reply every 30 s unless `POLLINATIONS_TOKEN` is set), so tasks skip it when it's busy instead of making people wait.
- **Memory:** answers are remembered per user for 7 days, so the same request never calls an API twice. Live calls never wait on the free tier.

## Brand book

One page per project that says how the business looks and sounds (`backend/app/brand_book.py`). Pictures, videos, ad copy, landing pages (colours and fonts) and WhatsApp replies all read it, so they agree.
- **Built, not filled in:** it's assembled from what the owner already gave: setup answers, the Brand Kit and their latest page. With no kit and no page yet, it uses the colours and fonts proven for that kind of business. Owner edits win over everything, and are stored in `onboarding_answers["brand_book"]` (no extra table).
- **One question:** the Brand Kit page shows what was found as plain lines and asks only for *words you never use*, which are kept out of every ad, page and reply. Everything the backend can work out is never asked.
- **API:** `GET/PUT /api/brand/book`, and `GET /api/brand/book.md` downloads it as a Markdown file to share with a designer.

## Showcase landing pages

The **Showcase** design (`backend/app/site_showcase.py`) is built to match premium project microsites. It's the default for real estate and restaurants whenever there's a real photo.
- **Hero:** a full-bleed photo with a serif headline, fact chips, an indicative-price card and a stat strip.
- **Sections:** overview, configurations, amenities with icons, a captioned gallery, nearby places with a Maps link, three visit steps, FAQs and an enquiry form.
- **Enquiry form:** asks for interest, timeline, preferred date and best time to call, with a consent box and a honeypot against bots.
- **Lead capture:** a gated brochure download, a sticky mobile Call / WhatsApp / Enquire bar, an announcement bar, approvals and disclaimers.
- **SEO:** JSON-LD structured data.
- **Where the facts come from:** the **Project details** tab in the brief, or the site importer. Any block without facts is left out, never invented. With AI on, the layout stays fixed and the AI writes only the words.

## How the app looks and moves

- **Make screens** (pictures, videos, pages, campaigns, calls) start from one prompt, already written from the business profile. The box sits at the bottom of the screen, chat-style, with the mascot and "what you'll get" above it. Asked from Home, a prompt runs straight away.
- **The mascot** (`frontend/src/components/Mascot.jsx`) is one body with drawn eyes and real hand shapes; its mood changes the eyes and hands, never the picture. It works while something is being made, then asks a question with quick chips. It is never cheeky when a customer is waiting, money is involved, or something failed.
- **Landing page** (`frontend/src/components/marketing/SkyHero.jsx`): a bright sky with AIMVA's own work floating in it (a WhatsApp reply, an ad, a lead, a call, a page, a rupee coin) around the headline, lifting away at different depths as you scroll, then a strip of the languages replies go out in, a scroll-driven story, the mascot on a call, and a sky finale. Laptops and tablets get everything plus smooth scrolling (Lenis); phones get the same sky with fewer objects and native scroll. Reduced motion keeps it all still.

## Templates

Every module starts from a template: image, video, website, ads, voice agent and WhatsApp.
- **Library:** 44 built-in templates in `backend/app/templates_catalog.py`, tagged by industry. Your industry's templates come first, and `{business}`/`{tagline}` fill in from your profile.
- **Your own:** picking a template only fills the form, so everything stays editable. Save your own with **Save as template**.
- **Template review agent** (`backend/app/template_agent.py`):
  - **For each business** (Templates → Suggest templates for me): versions with the edits you always make, your lowest cost-per-lead campaign, your best-converting page layout, images you rated 👍, your best call script, and industry gaps. With an AI writer connected it also drafts new ideas.
  - **For owners** (Quality & usage → Templates): what's used, which fields people change most, custom templates several businesses made independently (anonymised), and industries without templates. You publish or dismiss each suggestion.
- **Safety:** every suggestion is validated against its module's schema before it's saved, and dismissed suggestions don't come back.

## Owner settings (`backend/.env`)

- `ADMIN_EMAILS`: comma-separated owner emails that can open **Quality & usage**. It shows first-time-right rate, regenerates, feedback reasons, provider failures and the most active users.
- `POLLINATIONS_TOKEN`: optional. The keyless free image tier allows about one image every 45 seconds for the whole server. AIMVA stores each free image once and explains the limit instead of saving an error picture.

## Bring your own AI providers

Users can add any number of AI providers under **Settings → AI providers**. AIMVA checks every key when it's added and stores it encrypted.

| Kind | Supported |
|---|---|
| Text (landing pages, ad copy, voice replies, insights) | OpenAI, Anthropic Claude, Google Gemini, Groq, OpenRouter, Together, DeepSeek, Mistral, xAI, Ollama (local), any OpenAI-compatible API |
| Images | Free FLUX (Pollinations), any fal.ai model, OpenAI Images, Together FLUX, Replicate (any model), Stability AI, ComfyUI, any OpenAI-compatible image API |
| Video | Any fal.ai model (LTX-2, Veo 3, Kling, Luma, Wan…), Replicate (any model), ComfyUI / FreeVideo (self-hosted) |

For ComfyUI or FreeVideo:
1. Export your workflow with **Save (API format)**.
2. Put `{{prompt}}` where the prompt text goes. Optional placeholders: `{{negative_prompt}}`, `{{seed}}`, `{{width}}`, `{{height}}`, `{{duration}}`.

Guardrails:
- **Server addresses:** user-supplied addresses can't reach the server's private network. They must use https://, except local servers when `ALLOW_PRIVATE_PROVIDERS=true`, which is the default only when `PUBLIC_URL` is localhost.
- **Downloads:** every redirect hop is re-checked against the same rules, files are size-capped, and they're verified as real images or videos.
- **Errors:** provider failures map to clear messages (bad key, no credit, rate limit, unknown model, timeout).

## Configure email (verification codes)

1. Turn on 2-Step Verification for your Google account.
2. Create an App Password at https://myaccount.google.com/apppasswords.
3. Copy `backend/.env.example` to `backend/.env`, then set `SMTP_USER` and `SMTP_PASSWORD`.
4. Restart the backend.

Until SMTP is configured, the app runs in **dev mode**: codes are printed in the backend console and shown as a toast in the browser.

## How accounts and passwords are stored

- Passwords are hashed with **argon2id** (`argon2-cffi`). Nobody can read them, including you.
- Email codes are 6 digits and stored as HMAC hashes. They expire after 10 minutes, allow 5 attempts, and can be resent after 60 seconds.
- Sessions use a signed JWT in an `httpOnly`, `SameSite=Lax` cookie. Changing or resetting a password signs out every other session.
- Accounts lock for 15 minutes after 8 failed logins, and requests are rate-limited per IP. Rate limits are stored in the database, so they hold across server processes.
- The mobile app sends the same signed token as `Authorization: Bearer`. It's only returned in response bodies when the request carries `X-AIMVA-Client: app`.
- WhatsApp and Twilio webhooks are rejected unless their signatures check out (`META_APP_SECRET`, the Twilio auth token).
- Third-party tokens and keys are encrypted at rest with Fernet and never sent back to the browser.
- The database is `backend/data/aimva.db`. Set `DATABASE_URL` to point at Postgres in production.

The two users in the old Google Sheet can't be migrated: their passwords were stored in plain text. Ask them to sign up again.

## Modules

| Module | Works with no keys | Needs keys for |
|---|---|---|
| Image generation | Yes: free FLUX via [Pollinations](https://github.com/pollinations/pollinations) | fal.ai models (FLUX Pro, SD 3.5) |
| Video generation | — | fal.ai (Luma Ray 2, Kling, LTX-Video) |
| Website builder | Yes: built-in responsive template with a lead form | Gemini (AI-written pages) |
| Hosting | Yes: served at `/s/<slug>` | Netlify / Vercel tokens |
| Meta / Google / LinkedIn Ads | Draft campaigns, AI copy, lead forms, true-to-app previews (Facebook, Instagram feed & Story, Google Search, LinkedIn) | OAuth apps (see docs) |
| AI Voice Agent | Yes: browser test calls (Web Speech API), sentiment via [VADER](https://github.com/cjhutto/vaderSentiment), handoff | Twilio (real phone calls), Gemini (smarter replies) |
| WhatsApp | Sandbox inbox and simulated inbound messages | WhatsApp Cloud API number |
| Leads & Sync | Deduping, scoring, CSV export | Google (Sheets), Microsoft (OneDrive) |
| Analytics | KPIs, funnel, sources, rule-based insights | Gemini (AI insights) |

Add a free Gemini key (`GEMINI_API_KEY`, from https://aistudio.google.com/apikey) to switch on the AI writing features.

See [docs/INTEGRATIONS.md](docs/INTEGRATIONS.md) to connect each provider.

## Database migrations

The schema is managed by Alembic (`backend/migrations`). The app runs `upgrade head` on startup. A database created before migrations existed is topped up and stamped automatically, and no data is dropped.

After changing `app/models.py`:

```bash
cd backend && .venv/bin/alembic revision --autogenerate -m "what changed"
```

Review the generated file, then restart. `tests/test_migrations.py` fails if models and migrations drift apart.

## Production

```bash
cd frontend && npm run build
cd ../backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --timeout-graceful-shutdown 5
```

Live updates (new-lead toasts, badges, counts) stream over Server-Sent Events from `/api/events`. The background agents and rate limits are safe with several workers: only the process holding the database lease runs the scheduler. The live-update hub in `backend/app/live.py` is still per process, so with several workers a browser only gets events published by the worker it's connected to. Run one worker, or swap the hub for Redis pub/sub before scaling out. Always pass `--timeout-graceful-shutdown`: open live-update streams never close by themselves, so without it restarts wait forever. If you use a reverse proxy, turn off response buffering for `/api/events`; the stream already sends `X-Accel-Buffering: no` for nginx.

When `frontend/dist` exists, FastAPI serves it. Then set `PUBLIC_URL` and `FRONTEND_URL` to your domain, and `COOKIE_SECURE=true` behind HTTPS.
