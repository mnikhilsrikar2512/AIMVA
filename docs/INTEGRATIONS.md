# Connecting integrations

There are two kinds of connection:

- **App-level** credentials (OAuth client IDs and secrets) go in `backend/.env`. You set these up once, for the whole platform.
- **User-level** connections happen in the app under **Settings → Integrations**: OAuth sign-in or a pasted API key. Each user connects their own accounts.

OAuth redirect URIs follow the pattern `{PUBLIC_URL}/api/integrations/<provider>/callback`. For local testing that means `http://localhost:8000/api/integrations/meta/callback`, and so on.

Webhooks (WhatsApp, Twilio) need a public URL. Locally, use `cloudflared tunnel --url http://localhost:8000` or ngrok, and set `PUBLIC_URL` to the tunnel address.

## Meta (Facebook & Instagram Ads, Lead Ads)

1. Go to https://developers.facebook.com, create an app (type **Business**), and add **Facebook Login for Business** and **Marketing API**.
2. Add the redirect URI shown above, then put `META_APP_ID` and `META_APP_SECRET` in `.env`.
3. In AIMVA: **Settings → Integrations → Meta → Connect**, then go to Meta Ads and click **Choose ad account**.
4. To pull leads into AIMVA, paste a Lead Ads form ID into a campaign and click **Sync**.
5. Scopes requested: `ads_management, ads_read, leads_retrieval, pages_show_list, pages_manage_ads, business_management`. Using them with accounts you don't own requires Meta App Review.

## Google (Ads + Sheets)

1. At https://console.cloud.google.com, create OAuth credentials (type **Web application**) with the redirect URI.
2. Enable the **Google Sheets API** and **Google Ads API**.
3. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.
4. Sheets sync works right away: connect your account, then paste the sheet ID under Leads & Sync.
5. Publishing Google Ads campaigns also needs a developer token (`GOOGLE_ADS_DEVELOPER_TOKEN`), with Basic access approved by Google (apply in the Google Ads API Center of a manager account; a test-only token works only with test accounts).
6. Each user saves their Google Ads customer ID (10 digits) as `ads_customer_id`, plus `ads_login_customer_id` when they reach the account through a manager account, via `PATCH /api/integrations/google/meta`.
7. Publish creates a budget and a **paused** Search campaign. The owner adds ad groups, keywords and ads in Google Ads and switches it on there or in AIMVA. Sync pulls lifetime spend, impressions and clicks. Override the API version with `GOOGLE_ADS_API_VERSION` (default `v21`) when Google retires it.

## LinkedIn (Campaign Manager)

1. At https://www.linkedin.com/developers, create an app and request the **Advertising API** product.
2. Add the redirect URI, then set `LINKEDIN_CLIENT_ID` and `LINKEDIN_CLIENT_SECRET`.
3. Publishing campaigns requires approved Advertising API access.
4. Each user saves `ad_account_id`, `currency` (for example `INR`) and `default_geo_urns` (for example `["urn:li:geo:102713980"]` for India) via `PATCH /api/integrations/linkedin/meta`. A campaign can override locations with `targeting.linkedin_geo_urns`.
5. Publish creates a campaign group and a **draft** campaign; the owner adds creatives in Campaign Manager. Sync pulls lifetime spend, impressions and clicks. Set `LINKEDIN_API_VERSION` (default `202510`, format YYYYMM) when LinkedIn retires a version, roughly yearly.

## Microsoft (OneDrive lead sync)

1. In Azure Portal, go to **App registrations → New**, choose **Accounts in any org + personal**, and use **Web** as the redirect type.
2. Create a client secret, then set `MICROSOFT_CLIENT_ID` and `MICROSOFT_CLIENT_SECRET`.

## WhatsApp Cloud API

1. In your Meta app, add the **WhatsApp** product. Copy the **Phone number ID** and create a **permanent access token**: a System User token in Business Settings.
2. In AIMVA, go to **Settings → Integrations → WhatsApp** and paste both values.
3. Set up the webhook in the Meta dashboard:
   - Callback URL: `{PUBLIC_URL}/api/public/whatsapp/webhook`
   - Verify token: the value of `WHATSAPP_VERIFY_TOKEN` in `.env`
   - Set `META_APP_SECRET` in `.env` to your Meta app's **App secret** (App settings → Basic). Every incoming webhook is checked against it (`X-Hub-Signature-256`). Without it, a public server rejects all WhatsApp webhooks. Only a localhost `PUBLIC_URL` accepts unsigned ones, for trying things out.
   - Subscribe to `messages`
4. Inbound messages create leads automatically.

## Twilio (voice agent phone calls)

1. At https://www.twilio.com, buy a voice-capable number.
2. In AIMVA, go to **Settings → Integrations → Twilio** and paste the Account SID, Auth token and from-number.
3. `PUBLIC_URL` must be reachable from the internet, because Twilio calls `/api/public/voice/twilio/...`. It must also be exactly the address Twilio uses, because every call webhook is checked against Twilio's signature (`X-Twilio-Signature`), which covers the full URL. Requests with a missing or wrong signature get a 403.
4. Calls use Twilio speech recognition and text-to-speech in the agent's language. They transfer to the agent's handoff number when the caller asks for a person or sounds upset.

**For a fully open-source voice stack later:** the dialogue engine in `backend/app/routers/voice.py` (`_process_turn`) is transport-agnostic. You can put [Pipecat](https://github.com/pipecat-ai/pipecat) or [LiveKit Agents](https://github.com/livekit/agents) in front of it, with Whisper for speech-to-text and Piper for text-to-speech, instead of Twilio speech.

## fal.ai (image & video models)

Create a key at https://fal.ai/dashboard/keys and paste it in **Settings → Integrations → fal.ai**. You can also set `FAL_KEY` in `.env` to give every user a shared default key.

## Netlify / Vercel (hosting)

Create a personal access token, paste it in **Integrations**, then use **Hosting → Deploy**.

Cloudflare Pages and GitHub Pages tokens can be stored too. Their deploy buttons are not wired yet.


## Razorpay (plans and payments) — built, switched off

1. Create a Razorpay account, then under **Subscriptions → Plans** create one monthly plan per paid AIMVA plan (Starter, Growth, Agency).
2. Set `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, and `RAZORPAY_PLAN_STARTER` / `RAZORPAY_PLAN_GROWTH` / `RAZORPAY_PLAN_AGENCY` (the plan ids).
3. Add a webhook at `{PUBLIC_URL}/api/public/billing/razorpay/webhook` for the `subscription.*` events and set its secret as `RAZORPAY_WEBHOOK_SECRET`.
4. Limits are only enforced with `BILLING_ENFORCE=true`. Until then usage is counted and shown, nothing is blocked.
5. Plan names, prices and limits live in `backend/app/billing.py` (`PLANS`). Platform owners can put an invoiced customer on a plan or grant extra credits with `POST /api/admin/billing/{user_id}/plan` and `/credits`.
