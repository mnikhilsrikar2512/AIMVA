# AIMVA production checklist

Written 2026-11-07 from the code in `~/Desktop/AIMVA` (TECHSTACK.md, docs/DEPLOY.md, docs/DATABASE.md, design.md, backend/app, deploy/) and the 6 Nov review.

**Read this first.** The slowest items on this list aren't code. Meta app review and business verification, Google Ads developer-token approval, LinkedIn Marketing API access, Razorpay KYC, and TRAI-compliant calling in India all take days to weeks, and only you can apply for them. Start them today. If you wait until the code is done, they will hold up the launch, not the code.

Confidence tags: **[Certain]** I checked it in the code or docs. **[Likely]** strong inference. **[Guessing]** check before relying on it (mostly the legal items. Get a lawyer to read section C.)

Owner: **You** = only you can do it (accounts, money, legal, real devices). **Claude** = I can do it in a thread. **Both** = you provide access, I do the work.

---

## A. Launch blockers: nothing public until these are done

### A1. Safety net

| # | Item | Owner | Why / evidence |
|---|---|---|---|
| 1 | Create a private GitHub repo, push the Mac folder, and connect it to this project | You create the repo, Claude pushes | [Certain] The Mac folder has no git. Backups are tarballs, so there's no rollback. Your friend's repo might not have the latest changes. Treat the Mac as the source and don't merge from that repo blindly. |
| 2 | CI on every push: backend tests on SQLite **and** Postgres, plus `npm ci && npm run build` | Claude | [Certain] TECHSTACK item 3. Tests have only run on Postgres by hand. |
| 3 | Clean up the repo before the first push: delete `_backup_*`, `_tmp_stage`, `_samples` (if they hold customer-like data), `__pycache__`, `frontend/dist`, `frontend/node_modules`, `.DS_Store`, `backend/data/` | Claude (needs your OK to delete) | [Certain] All of these are in the folder now. `backend/data/.secret_key` must never be committed. |

### A2. Secrets and the legacy app

| # | Item | Owner | Why / evidence |
|---|---|---|---|
| 4 | **Rotate the fal.ai key** that's written in `legacy/image-generation.html` and `legacy/video-generation.html` | You | [Certain] Treat that key as leaked. The project-files copy also has it. |
| 5 | Take the Google Apps Script web app offline, then delete `legacy/` | You take it offline, Claude deletes | [Certain] `legacy/google-sheets-auth.gs` and the sheet behind it hold plaintext passwords. DEPLOY.md already lists this as a prerequisite. |
| 6 | Keep a separate offline copy of `SECRET_KEY` (a password manager is fine) and **never rotate it casually** | You | [Certain] `security.py` derives the Fernet key that encrypts stored OAuth and WhatsApp tokens from `SECRET_KEY`. If you lose or change it, every connected Meta/Google/LinkedIn account and every session is gone, and a database backup can't bring them back. |
| 7 | Fill `deploy/.env`: `SECRET_KEY`, `POSTGRES_PASSWORD`, `META_APP_SECRET`, your own `WHATSAPP_VERIFY_TOKEN`, SMTP, `ADMIN_EMAILS`, `SENTRY_DSN`. Production won't start without most of these. | You | [Certain] `config.problems()` blocks startup on an empty SECRET_KEY, SQLite, a non-https PUBLIC_URL, COOKIE_SECURE off, ALLOW_PRIVATE_PROVIDERS on, an empty META_APP_SECRET, the default verify token, or no SMTP. |
| 8 | **Set `FREE_AI=false`** and use a paid `GEMINI_API_KEY` | You | [Certain] `deploy/.env.example` ships `FREE_AI=true`. That sends customer prompts to a free public service at about 1 reply every 30 s for the whole server. I'd also flip the default in `config.py` and `.env.example` to false, and add it to `problems()` (Claude). |

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
| 34 | Sarvam for Indian-language voice | Claude | [Certain] Calls are English-only Twilio `<Say>` today. This is your pitched differentiator, so it shouldn't wait long. |
| 35 | Per-ad results (not per-campaign), and ad-to-sale tracking via Meta Conversions API | Claude | [Certain] memory: results are per-campaign only. |
| 36 | Uploads to object storage (R2/S3), before a second server | Claude | [Certain] TECHSTACK item 4. |
| 37 | Monthly restore drill, plus a short incident runbook (who to call, how to roll back, how to tell customers) | Both | [Certain] DEPLOY.md recommends the monthly restore. There's no runbook yet. |
| 38 | Basic product analytics (sign-up → first lead → first reply) so the pilot gives you numbers, not feelings | Claude | [Likely] Nothing measures the journey in design.md today. |
| 39 | Security pass: dependency audit (`pip-audit`, `npm audit`) in CI, plus a review of auth, webhooks and file serving | Claude | [Likely] There's been no audit since the 6 Nov review. |
| 40 | Upgrade Vite 5, and remove stale `cpython-310` pycache files | Claude | [Certain] TECHSTACK item 7. Do this after launch, not before. |

---

## Suggested order

1. **Today (you):** rotate the fal key (4), take the Apps Script offline (5), create the GitHub repo (1), and start Meta verification (21) and the Twilio/Indian calling check (23).
2. **This week (Claude):** repo + CI (2, 3), FREE_AI default (8), STOP opt-out (15), account deletion/export (19), consent record (28), call-hours guard (29), legal page drafts (25), hide untested modules (17).
3. **When you have a domain + VPS:** staging deploy, HTTPS, Postgres tests, backups + restore, monitoring (9 to 14).
4. **Then:** the full Meta ad (16), live end-to-end tests (18), real devices (20), and the lawyer's review of section C.
5. **Pilot** with 3 to 5 businesses. Section D runs alongside it.

**Done means:** one real business uses it for two weeks, leads reach them through WhatsApp within 60 s, nobody who replied STOP gets another message, and you never had to fix data by hand.
