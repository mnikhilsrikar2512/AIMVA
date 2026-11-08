# AIMVA production checklist

Written 2026-11-07 (testing items 41 to 43 and lead-reply items 44 to 47 added the same day) from the code in `~/Desktop/AIMVA` (TECHSTACK.md, docs/DEPLOY.md, docs/DATABASE.md, design.md, backend/app, deploy/) and the 6 Nov review.

**Read this first.** The slowest items on this list aren't code. Meta app review and business verification, Google Ads developer-token approval, LinkedIn Marketing API access, Razorpay KYC, and TRAI-compliant calling in India all take days to weeks, and only you can apply for them. Start them today. If you wait until the code is done, they will hold up the launch, not the code.

Confidence tags: **[Certain]** I checked it in the code or docs. **[Likely]** strong inference. **[Guessing]** check before relying on it (mostly the legal items. Get a lawyer to read section C.)

Owner: **You** = only you can do it (accounts, money, legal, real devices). **Claude** = I can do it in a thread. **Both** = you provide access, I do the work.

---

## A. Launch blockers: nothing public until these are done

### A1. Safety net

| # | Item | Owner | Why / evidence |
|---|---|---|---|
| 1 | Create a private GitHub repo, push the Mac folder, and connect it to this project | You create the repo, Claude pushes | [Certain] The Mac folder has no git. Backups are tarballs, so there's no rollback. Your friend's repo might not have the latest changes. Treat the Mac as the source and don't merge from that repo blindly. |
| 2 | ✅ **CI runs on every push:** frontend build, backend tests on Postgres, backend tests on SQLite. All three must pass before a release. | Claude | [Certain] Set up and green on every push so far. Keep it running on the new repo. |
| 3 | Clean up the repo before the first push: delete `_backup_*`, `_tmp_stage`, `_samples` (if they hold customer-like data), `__pycache__`, `frontend/dist`, `frontend/node_modules`, `.DS_Store`, `backend/data/` | Claude (needs your OK to delete) | [Certain] All of these are in the folder now. `backend/data/.secret_key` must never be committed. |

### A2. Secrets and the legacy app

| # | Item | Owner | Why / evidence |
|---|---|---|---|
| 4 | **Rotate the fal.ai key** that's written in `legacy/image-generation.html` and `legacy/video-generation.html` | You | [Certain] Treat that key as leaked. The project-files copy also has it. |
| 5 | Take the Google Apps Script web app offline, then delete `legacy/` | You take it offline, Claude deletes | [Certain] `legacy/google-sheets-auth.gs` and the sheet behind it hold plaintext passwords. DEPLOY.md already lists this as a prerequisite. |
| 6 | Generate `TOKEN_ENCRYPTION_KEYS` (`scripts/db.py tokens new-key`) and keep offline copies of it and `SECRET_KEY` (a password manager is fine) | You | [Certain] Done in code (Claude): stored OAuth, WhatsApp and AI-key tokens now use their own key, with rotation (`tokens rotate`, docs/DEPLOY.md "Keys and rotating them"). Changing `SECRET_KEY` now only signs everyone out. Losing `TOKEN_ENCRYPTION_KEYS` still means every connected account must reconnect, and a backup needs the keys in use when it was taken. |
| 7 | Fill `deploy/.env`: `SECRET_KEY`, `TOKEN_ENCRYPTION_KEYS`, `POSTGRES_PASSWORD`, `META_APP_SECRET`, your own `WHATSAPP_VERIFY_TOKEN`, SMTP, `ADMIN_EMAILS`, `SENTRY_DSN`. Production won't start without most of these. | You | [Certain] `config.problems()` blocks startup on an empty SECRET_KEY, SQLite, a non-https PUBLIC_URL, COOKIE_SECURE off, ALLOW_PRIVATE_PROVIDERS on, an empty META_APP_SECRET, the default verify token, no SMTP, FREE_AI on, or an empty TOKEN_ENCRYPTION_KEYS. |
| 8 | Use a paid `GEMINI_API_KEY` (FREE_AI is now off in production) | You | [Certain] Done in code (Claude): `FREE_AI` defaults to false when `ENVIRONMENT=production`, and production refuses to start if it's set to true. Development keeps it on. |

### A3. Infrastructure

| # | Item | Owner | Why / evidence |
|---|---|---|---|
| 9 | Buy the domain, rent one VPS (2 GB, Ubuntu 24.04, ideally in an India region), and point the A record at it | You | [Certain] DEPLOY.md assumes this. An India region keeps lead data in India. That isn't strictly required by DPDP today [Likely], but it's an easy answer when customers ask. |
| 10 | First deploy on a **staging** subdomain. Check `/api/ready`, then verify that Caddy issues HTTPS | Both | [Certain] The Caddyfile has never been validated (Docker Hub rate limit) and HTTPS has never run. |
| 11 | Run the full suite against that real Postgres once (`TEST_DATABASE_URL`) | Claude | [Certain] TECHSTACK item 3. Use 127.0.0.1, not localhost (see DATABASE.md). |
| 12 | Off-server backups: rclone `deploy/backups/` to Backblaze/S3/R2 daily, then **do one real restore** on a spare server | Both | [Certain] DEPLOY.md: "A backup on the same disk is not a backup." No restore has run outside the container test. |
| 13 | Uptime check on `/api/health` (UptimeRobot / Better Stack), plus a Sentry project and an alert that emails you | You | [Certain] The code is ready (`observability.py`). The accounts don't exist yet. |
| 14 | Run `scripts/db.py unseed` on production, or never seed it at all. The demo password `Demo-pass-2026!` is public in docs. | Claude | [Certain] DATABASE.md. |

### A4. Things that would hurt a paying customer on day one

| # | Item | Owner | Why / evidence |
|---|---|---|---|
| 15 | **Honor "STOP"** on WhatsApp: an opt-out flag on the lead, checked by the concierge, scheduled sends and every agent | Claude | [Certain] The day-7 message promises "Reply STOP and we won't message again", but no code reads STOP. `whatsapp.py` and `concierge.py` have no opt-out handling, and `Lead` has no opt-out field. Breaking that promise is a WhatsApp Business Policy violation [Likely] and gets numbers banned. |
| 16 | **Meta publish has to create a full ad** (campaign, ad set, creative, ad), or the button has to say "Create draft campaign" | Claude, then you test with a real ad account | [Certain] `campaigns.py:164` only POSTs `/campaigns`. Today a customer clicks publish and gets an empty campaign. |
| 17 | Decide what's in the pilot, and **hide what isn't live-tested**: Google Ads, LinkedIn, Razorpay | You decide, Claude hides | [Certain] `ad_platforms.py` has only ever run against mocks. I recommend Meta + WhatsApp + sites + images for the pilot and hiding the rest behind "coming soon". |
| 18 | Live end-to-end test with your own accounts: sign-up email, a WhatsApp inbound lead, the 60 s reply, a Twilio call, a fal image edit, a site on a custom domain | Both | [Certain] None of these has run for real (memory, TECHSTACK item 6). Mocked tests can't catch wrong API fields. |
| 19 | Account deletion and a data export (for the user and the leads they hold) | Claude | [Certain] No delete-account or export endpoint exists. DPDP requires erasure on request (section C). |
| 20 | Real-device pass: iPhone Safari, Android Chrome, desktop Firefox | You (devices), Claude fixes | [Certain] Only Chromium emulation and desktop Safari 26.5 have been tested. Bottom sheets and safe areas often break only on a real iPhone. |
| 41 | **Test the admin view.** ✅ *Tested locally on 7 Nov with the demo owner (`ADMIN_EMAILS=owner@aimva-demo.example.com` in `backend/.env`): the owner sees the AI providers tab, the AIMVA engines under Accounts and real errors; `solo@` and `client.dental@` see no tab, no supplier names on any page or API response, get 404/403 from `/api/providers` and neutral errors. Still to do: set your real email(s) on the server and repeat on staging.* Set `ADMIN_EMAILS` to your own email(s) in `backend/.env` locally, or in `deploy/.env` on the server, then restart. Sign in as the owner and check that Settings shows the AI providers tab and Accounts lists the platform engines. Then sign in as a normal user and as a client, and check that neither sees that tab, any vendor name or any key. Format: comma-separated, e.g. `ADMIN_EMAILS=you@yourdomain.com,cofounder@yourdomain.com`; keep the list short, since these people see the owner screens and real error text. Also check that a normal user's errors read like "The voice service is busy…" and that `/api/providers` answers 404 for them (automated in `tests/test_discreet.py`). | You test, Claude fixes | [Certain] `ADMIN_EMAILS` gates `providers.py`, `integrations.py`, `feedback.py` and the image-upload connections in `content.py`. If it's left empty, nobody is admin. |
| 42 | **Fill in the platform keys** from `docs/AI_KEYS.md`: `SARVAM_API_KEY`, `FAL_KEY` (the new one, after rotating per item 4) and `GEMINI_API_KEY`. Or use the per-task `*_PROVIDER` + `*_API_KEY` pairs. Keep `FREE_AI=false` in production (item 8). | You | [Certain] Without keys, each task falls back to the free tier or to rules (`docs/AI_KEYS.md` table). |
| 43 | **Make one real Hindi call and one real Telugu call** once the Sarvam key is set, to check the voice, the transcript and the reply speed | You call, Claude fixes | [Certain] Sarvam speech and transcription are built on the backend but have only been tested with mocks. |
| 44 | **Have a native speaker check the ready-made lead replies** in `backend/app/lead_reply.py` (`READY`): Hindi, Hinglish, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Marathi, Punjabi and Odia. They're sent when no AI writer is available, and the auto-welcome uses them too. Start with Hindi, Tamil and Telugu. | You find speakers, Claude fixes | [Certain] Claude wrote these translations on 7 Nov and nobody fluent has read them. A clumsy first message in someone's own language does more harm than a clean English one. |
| 45 | **Get WhatsApp message templates approved and enter their names in AIMVA.** In WhatsApp Manager, create a first-message template that starts with the lead's first name as `{{1}}` (e.g. `lead_welcome`), plus a follow-up one if you want day-2/day-7 follow-ups, in English and every language you serve (`en`, `hi`, `ta`...). Once approved, enter the names under WhatsApp → Approved templates. | You | [Certain] WhatsApp only delivers free text within 24 hours of the customer's last message. A form or ad lead has never messaged you, so without an approved template the 60-second welcome can't be sent. AIMVA drafts it on the lead instead. Needs Meta verification (item 21). |
| 46 | **Test the lead reply end to end on a real number:** fill your page form, check the approved template arrives within 60 s, reply from that phone in Hindi, then open the lead, check the draft is in Hindi (with the real AI writer, item 42) and send it. Also check the lead's place in the "Waiting first" list before and after you reply. | You test, Claude fixes | [Certain] Built on 7 Nov and tested only with mocks and demo data. It has never run against real WhatsApp or a real AI writer. |
| 47 | **Run migration 0011 on every database** (local, staging, production): `backend/scripts/db.py migrate`. It adds the lead's language. | You (or the deploy) | [Certain] The app migrates itself on startup too, but check `db.py check` says the schema is up to date. |

---

## B. Accounts and approvals: start now, they run in parallel

| # | Item | Owner | Lead time |
|---|---|---|---|
| 21 | Meta Business verification + app review for `ads_management`, `pages_*`, `leads_retrieval`, `whatsapp_business_messaging` / `management`. Also a production WhatsApp number and display-name approval. | You | [Likely] 1 to 4 weeks. App review needs a privacy policy URL and a screencast of the live app, so A10 and C25 come first. |
| 22 | WhatsApp message templates (welcome, day-2, day-7, any broadcast) submitted for approval | You submit, Claude drafts | [Likely] Hours to days each. The 24 h rule is in the code, but templates outside the 24 h window must be pre-approved. |
| 23 | Twilio in India: outbound calls to Indian numbers with a non-Indian caller ID often get blocked or flagged. Get an Indian number, or use an Indian provider (Exotel/Plivo India), and check TRAI/DLT registration for commercial calls | You | [Likely] Weeks. This can quietly kill the voice feature. [Guessing] on the exact current DLT voice rules, so confirm with the provider. |
| 24 | Razorpay KYC (only if you charge at launch). Razorpay asks for live Terms, Privacy, Refund/Cancellation and Contact pages. Get GST registration if you'll cross the threshold or sell B2B. | You | [Likely] 3 to 10 days. Billing can stay off for a free pilot. |
| — | Google Ads developer token (basic access) and LinkedIn Marketing Developer Platform | You | [Likely] Weeks. Only needed once those modules come back (item 17). |

---

## C. Legal and compliance (India). Have a lawyer read this section.

| # | Item | Owner | Notes |
|---|---|---|---|
| 25 | **Privacy policy, Terms of Service, Refund policy, and a Contact/Grievance page**, linked from the site footer, sign-up and every customer site's lead form | You approve, Claude drafts and adds pages | [Certain] The frontend has no `/privacy`, `/terms` or `/refund` routes (`App.jsx`). Meta review and Razorpay both reject apps without them. |
| 26 | DPDP Act 2023 + DPDP Rules 2025: you're a **Data Fiduciary** for your own users, and a **Data Processor** for the leads your customers collect. You need a clear consent notice, a named grievance contact, breach notification to the Data Protection Board and to the people affected, erasure on request (item 19), and deletion once the purpose is over. | You (lawyer), Claude builds the product parts | [Likely] Most obligations phase in by about mid-2027, but agencies will ask now. [Guessing] on the exact dates, so check. |
| 27 | A Data Processing Agreement in the ToS for customers: they own their leads, you process them on their instructions, and you list your sub-processors (Google Gemini, fal.ai, Meta, Twilio, Sentry, your VPS host, the email provider) | You (lawyer), Claude drafts the list | [Likely] Lead data goes out of India to US AI providers. Say so in the privacy policy. |
| 28 | Consent on lead forms: the checkbox exists, so keep it required. Store **what** they agreed to and **when** (consent text and timestamp on the lead). Add "WhatsApp and calls" to the wording, because the concierge and voice agent use both. | Claude | [Certain] `site_showcase.py:150` has "I agree to be contacted about this enquiry", but nothing records that the box was ticked, and leads from Meta forms come in without it. |
| 29 | Calling rules: no automated calls before 9 am or after 9 pm IST, honor DND / NCPR for promotional calls, and add a "talk to a human" option | Claude (time guard), you (DND registration with the provider) | [Likely] TRAI TCCCPR. The voice agent has no time-of-day guard today [Likely, from a grep]. |
| 30 | AI-generated content: label AI images/videos where required, and only use commercially licensed models | Claude | [Certain] From the model research: FLUX dev, Qwen-Image-2.1, XTTS-v2, F5-TTS and Wav2Lip are non-commercial, so don't ship them. [Guessing] on India's synthetic-media labelling rules: they've been proposed or amended, so check what's in force. |

---

## D. Soon after launch (first 2 to 6 weeks)

| # | Item | Owner | Why |
|---|---|---|---|
| 31 | Move billing from per-workspace to per-agency account before any agency pays. Set real prices (Starter ₹1,999 / Growth ₹4,999 / Agency ₹12,999 are placeholders in `billing.py`). | You (prices), Claude (code) | [Certain] memory + `billing.py:10`. |
| 32 | Turn on `BILLING_ENFORCE` and wire `charge()` into the costly modules (images, video, calls) | Claude, with your OK | [Certain] It's off on purpose today. Until it's on, one user can run up your fal/Gemini bill. Rate limits help (`img` 30/5 min, `vid` 10/10 min) but they aren't a budget. |
| 33 | A hard monthly spend cap in the fal.ai, Gemini and Twilio dashboards | You | [Likely] Five minutes of work, and it saves you from a runaway agent or abuse. |
| 34 | Sarvam for Indian-language voice | Claude | [Certain] Built on the backend on 2026-11-07, with the keys kept on the server (`SARVAM_API_KEY`), and tested only with mocks. The real-call test is item 43. |
| 35 | Per-ad results (not per-campaign), and ad-to-sale tracking via Meta Conversions API | Claude | [Certain] memory: results are per-campaign only. |
| 36 | Uploads to object storage (R2/S3), before a second server | Claude | [Certain] TECHSTACK item 4. |
| 37 | Monthly restore drill, plus a short incident runbook (who to call, how to roll back, how to tell customers) | Both | [Certain] DEPLOY.md recommends the monthly restore. There's no runbook yet. |
| 38 | Basic product analytics (sign-up → first lead → first reply) so the pilot gives you numbers, not feelings | Claude | [Likely] Nothing measures the journey in design.md today. |
| 39 | Security pass: dependency audit (`pip-audit`, `npm audit`) in CI, plus a review of auth, webhooks and file serving | Claude | [Likely] There's been no audit since the 6 Nov review. |
| 40 | Upgrade Vite 5, and remove stale `cpython-310` pycache files | Claude | [Certain] TECHSTACK item 7. Do this after launch, not before. |

---

## Suggested order

1. **Today (you):** rotate the fal key (4), set `ADMIN_EMAILS` to your email (41), take the Apps Script offline (5), create the GitHub repo (1), and start Meta verification (21) and the Twilio/Indian calling check (23).
2. **This week (Claude):** repo + CI (2, 3), FREE_AI default (8), STOP opt-out (15), account deletion/export (19), consent record (28), call-hours guard (29), legal page drafts (25), hide untested modules (17).
3. **When you have a domain + VPS:** staging deploy, HTTPS, Postgres tests, backups + restore, monitoring (9 to 14).
4. **Then:** the full Meta ad (16), live end-to-end tests (18), real devices (20), the admin view, keys and a real Sarvam call (41 to 43), and the lead-reply checks (44 to 47), and the lawyer's review of section C.
5. **Pilot** with 3 to 5 businesses. Section D runs alongside it.

**Done means:** one real business uses it for two weeks, leads reach them through WhatsApp within 60 s, nobody who replied STOP gets another message, and you never had to fix data by hand.
