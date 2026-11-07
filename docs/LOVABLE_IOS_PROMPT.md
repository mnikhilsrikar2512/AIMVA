# AIMVA iOS app: prompts for Lovable

Paste these into Lovable one at a time, in order. Wait for each to finish and check it before pasting the next.
Replace `https://YOUR-AIMVA-SERVER` in Prompt 1 with your hosted backend address.

---

## Prompt 1: foundation, design system, sign-in

Build the iOS app for AIMVA, an AI marketing and voice automation platform. A web portal and a FastAPI backend already exist. This app is a mobile client for that backend, and it must look and behave like the portal, adapted for a phone.

**Hard rules**
- Stack: Vite + React + TypeScript + Tailwind, as a static client-rendered single-page app with no SSR, ready to wrap with Capacitor. Add `capacitor.config.ts` with appId `com.aimva.app`, appName `AIMVA`, webDir `dist`.
- Do NOT use Supabase, Lovable Cloud or any other backend, and do not create database tables. All data comes from the AIMVA API.
- Put the API base URL in one place: `VITE_API_URL`, value `https://YOUR-AIMVA-SERVER`.
- If `VITE_API_URL` is empty, run in demo mode with sample data and a visible "Demo data" badge. Demo mode must never be active when the URL is set.
- Never invent numbers, prices, reviews or results in the UI. Show an empty state when there's no data.
- Never store or show API keys in the app beyond a write-only input.
- Currency is ₹, formatted with `en-IN` grouping. API timestamps are UTC without a timezone suffix, so append `Z` before parsing.

**API client (one file)**
- Send `Authorization: Bearer <token>` on every request. Keep the token in Capacitor Preferences. On a 401, clear it and go to Login.
- Send `X-AIMVA-Client: app` on every request. With that header, `POST /api/auth/login`, `POST /api/auth/verify-email`, `POST /api/auth/reset-password` and `POST /api/auth/change-password` return `{ token }` next to the usual fields. Without it, no token is returned (the web portal uses a cookie). After a password change, replace the stored token with the new one, because old tokens stop working.
- Errors: `detail` is either a string or an array of `{loc, msg}`. Show the string, or join the array as `field: msg`. On a network failure show "Can't reach the AIMVA server."
- Private files at `/api/files/...` need the token, so fetch them as blobs and show object URLs. Don't put them straight into `<img src>`.
- Don't use EventSource. Refresh with polling: unseen leads (`GET /api/leads/unseen`) every 30 s, and the open lead or chat every 15 s.
- The full API schema is at `{VITE_API_URL}/openapi.json`. Follow it if anything below is unclear.

**Design tokens (use these exact values)**
- Canvas `#fbfaf8`, surface `#ffffff`, surface-2 `#f4f2ee`
- Lines `rgb(20 18 31 / .07)`, strong lines `rgb(20 18 31 / .13)`
- Text: strong `#14121f`, ink `#2b2838`, muted `#6b6880`, faint `#9a97a8`
- Brand `#6d5dfc`, brand-2 `#0e9fb8`, peach `#ff9f7a`, lavender `#ece8ff`
- Soft shadow `0 1px 2px rgb(20 18 31/.04), 0 8px 28px -12px rgb(20 18 31/.12)`
- Lift shadow `0 2px 4px rgb(20 18 31/.04), 0 18px 40px -16px rgb(60 40 140/.22)`
- Gradient text `linear-gradient(95deg,#6d5dfc 0%,#b05cf0 45%,#ff8a65 100%)`
- Aura behind page headers: radial glows of `rgb(196 181 253/.55)`, `rgb(255 190 160/.5)`, `rgb(165 243 252/.25)` on the canvas
- Fonts: Inter for body; Plus Jakarta Sans for headings, with tight tracking. Light mode only.
- Tones, as tile background / icon colour: violet `#f5f3ff/#7c3aed`, pink `#fdf2f8/#db2777`, blue `#f0f9ff/#0284c7`, green `#ecfdf5/#059669`, cyan `#ecfeff/#0891b2`, amber `#fffbeb/#d97706`, rose `#fff1f2/#e11d48`, slate `#f8fafc/#475569`

**Components**
- Card: radius 24px, white, soft shadow, separated by shadow rather than borders, 20px padding.
- Primary button: pill, background `#14121f`, white semibold text, scales to .97 on press. Ghost button: white with a strong-line ring. Subtle and danger (rose) variants too. Minimum touch height 44px.
- Input: radius 16px, white, strong-line ring, 2px brand ring on focus, 44px high. Use 16px text so iOS doesn't zoom. Label: 12px semibold muted, above the field.
- Chip: pill, 12px medium. Pills for single and multi choice: selected `#14121f` with white text, otherwise surface-2.
- Stat tile: label, large value, small sub-line, tone icon.
- Toasts for results. Bottom sheets in place of the portal's modals and side panels.
- Icons: lucide-react. Motion: framer-motion, used for meaning only (rise-in lists, count-up numbers, sparkline wipes). Respect reduced motion.

**App shell**
- Bottom tab bar: Home, Leads, Command, Create, More. Respect iPhone safe areas top and bottom. The page never scrolls sideways. Use native-feeling push navigation with a back button, and pull to refresh on lists.
- Leads tab shows the unseen count as a badge.
- Create opens: Launch with AIMVA, Website Builder, Image Generation, Video Generation, Brand Kit.
- More opens: Meta Ads, Google Ads, LinkedIn Ads, AI Voice Agent, WhatsApp, Hosting, Analytics, Settings.

**Screens in this prompt: sign-in and onboarding**
- Sign up: name, email, password, company → `POST /api/auth/signup {name,email,password,company}`.
- Verify: 6-digit code → `POST /api/auth/verify-email {email,code}`, with resend via `POST /api/auth/resend-code {email}`.
- Log in: `POST /api/auth/login {email,password}`. Show the server's message on a 423 lockout.
- Forgot password: `POST /api/auth/forgot-password {email}`, then `POST /api/auth/reset-password {email,code,password}`.
- Welcome wizard when `GET /api/onboarding` says `needs_profile`: `POST /api/onboarding/profile {company, industry, goal}`.
  - Industry: real_estate "Real estate", healthcare "Clinic / healthcare", education "Education / coaching", saas "SaaS / software", retail "Retail / e-commerce", services "Local services", other "Something else".
  - Goal: more_leads "Get more leads", book_visits "Book visits & appointments", sell_online "Sell online", support "Answer customers faster".
- Settings: profile `PATCH /api/auth/profile {name,company}`, change password `POST /api/auth/change-password {current_password,new_password}`, log out `POST /api/auth/logout`.
- Delete account: a clear button with a typed confirmation, `DELETE /api/auth/account`. Apple requires this.

Build the shell with placeholder screens for the other tabs. I'll send those next.

---

## Prompt 2: Home, Leads, WhatsApp

Now build these, using the same design system and API client.

**Home (Dashboard)**
- Greeting with the date and first name.
- **Launch with AIMVA** card at the top: rocket tile in a brand gradient, then the text "Paste your website or describe what you sell. AIMVA builds the landing page, ad drafts, call-back assistant and follow-ups for you."
  - Fields: one box (a URL goes in `url`, anything else in `description`, max 1000 characters), brochure picker from `GET /api/references?kind=document` (`reference_id`), monthly ad budget in ₹ (`monthly_budget`), platform pills Meta / Google / LinkedIn (`platforms`), checkbox "Put the page live straight away (ads always wait for you)" (`publish`). Button: "Do it for me".
  - `POST /api/agents/launch` returns a job. Poll `GET /api/agents/jobs/{id}` every 3 s while status is queued or running. Show each step with a tick (done), dash (skipped) or cross (failed), plus its detail. When done, show `result.next` under "Left for you" as links. On opening Home, resume the latest launch from `GET /api/agents/jobs?kind=launch&limit=1` if it's running or under 15 minutes old.
- **Done for you** feed: `GET /api/agents/jobs?limit=6`, showing title, agent and time ago. Dots: launch violet, concierge green, autopilot sky, weekly_report amber, page_fixer pink, failed rose.
- **What needs you today:** top 3 of `GET /api/command/overview?days=7` → `recommendations`.
- Setup checklist from `GET /api/onboarding`, hidden with `POST /api/onboarding/dismiss {dismissed:true}`.
- Stats from `GET /api/analytics/overview?days=30`: leads with change, hot leads with average score, voice calls with sentiment, ad spend with cost per lead. Then a leads-over-time area chart in `#8b7bff`, the pipeline, top leads and `GET /api/analytics/insights`.

**Leads**
- Concierge control at the top ("Lead Concierge: Welcomes every new lead on WhatsApp within seconds, then follows up on day 2 and day 7 until they reply."). On/off via `GET /api/agents` and `PUT /api/agents/concierge {enabled}`.
- List `GET /api/leads?q=&source=&stage=` with search and filters, showing name, source chip, stage and score. Opening the tab calls `POST /api/leads/seen`. Add a lead with `POST /api/leads {name,email,phone,message,source:"manual",value}`.
- Sources and chip tones: website pink, meta blue, google green, linkedin cyan, whatsapp green, voice violet, manual slate.
- Stages and dots: new `#38bdf8`, contacted `#a78bfa`, qualified `#fbbf24`, won `#10b981`, lost `#cbd5e1`. A score of 70 or more is hot.
- Lead detail as a full-height sheet from `GET /api/leads/{id}`:
  - Header with avatar, name, source, age and score. Phone with copy.
  - Actions: AI call `POST /api/leads/{id}/call {agent_id?}`, WhatsApp, Note `POST /api/leads/{id}/notes {body}`.
  - Follow-ups card from `GET /api/agents/leads/{id}/follow-ups`: Day-2 and Day-7 with date, "Sent", or the skip reason.
  - Stage pills and deal value via `PATCH /api/leads/{id} {stage,value}`.
  - Timeline from `timeline`, with filters All / WhatsApp / Calls / Forms & ads / Notes. Item kinds: created, form, ad, note, whatsapp, call. Calls expand to show the transcript.
- Composer quick messages, using exactly these words:
  - Schedule visit: "Hi {first name}! Thanks for your interest. Would you like to schedule a visit? Reply with a day and time that suits you."
  - Follow up: "Hi {first name}, just following up on your enquiry. Do you have any questions I can help with?"
  - Share pricing: "Hi {first name}, happy to share pricing options that fit your budget. When is a good time to talk?"
- Sync: `POST /api/leads/sync/{target}`. Download `GET /api/leads/export.csv` through the iOS share sheet.

**WhatsApp**
- Inbox `GET /api/whatsapp/conversations`, chat `GET /api/whatsapp/messages/{contact}` as chat bubbles, send `POST /api/whatsapp/send {to,body,name}`. Outgoing bubbles use an emerald tint.
- Template picker from `GET /api/templates?module=whatsapp`, replacing `{name}` with the contact's first name.
- Concierge message editor: `PUT /api/agents/concierge {config:{messages:{welcome,day2,day7}}}`. Defaults, using these words:
  - welcome: "Hi {name}, thanks for your enquiry with {business}! {next} Reply here any time with questions."
  - day2: "Hi {name}, just following up on your enquiry with {business}. Do you have any questions I can help with?"
  - day7: "Hi {name}, we're still happy to help with {business}. Should we keep you posted, or is now not the right time? Reply STOP and we won't message again."

---

## Prompt 3: Command Center, ads and their previews

**Command Center** (`GET /api/command/overview?days=7|30|90`)
- Autopilot control: Off / Suggest / Fix safely (`PUT /api/agents/autopilot {enabled,mode}`, where mode is `suggest` or `auto`). Text: "Checks every campaign each morning. Suggest lines fixes up here; Fix safely pauses money-wasters and trims overspend itself, never raising budgets."
- KPIs (spend, leads, revenue won), `summary`, and an optional AI brief from `GET /api/command/brief`.
- Next steps from `recommendations`: priority dots high rose, medium amber, low sky. Show title, why, impact, notes and the action label. Buttons: accept, snooze, dismiss via `POST /api/command/recommendations/{key}/decide {decision:"accepted"|"snoozed"|"dismissed",note,alt}`. `alt:true` takes the alternative action. Show the returned `result`.
- Products: `GET/POST /api/products`, `PUT/DELETE /api/products/{id}`, with fields name, kind (product/service/offer), price, target_cpl, monthly_budget, status (active/paused/archived), notes. Show each with its campaigns, health, budget meter and pages. Link with `POST /api/products/link {kind:"campaign"|"site",id,product_id}`.
- Enter results: `POST /api/campaigns/{id}/results {spend,impressions,clicks,mode:"add"|"total",day,since}`.
- Decisions log from `decisions`, and the "Next 7 days" plan from `plan`.

**Ads** (one screen per platform: meta, google, linkedin)
- List `GET /api/campaigns?platform=`, create `POST /api/campaigns`, edit `PATCH /api/campaigns/{id}`, delete, publish `POST /api/campaigns/{id}/publish`, sync `POST /api/campaigns/{id}/sync`.
- Fields: name, objective (leads/traffic), daily_budget, product_id, creative {headline max 120, text max 600, cta max 30, image_url}, targeting {locations, age_min 13–65, age_max 13–65, interests}, lead_form {fields: full_name, email, phone_number, city, company_name, job_title}.
- Template strip from `GET /api/templates?module=ads`. "Write with AI" via `POST /api/content/ad-copy {product,audience,platform,tone}`. Image picker from `GET /api/content/assets?kind=image`.
- **Ad previews must look exactly like the real apps**, inside a phone frame with iOS status bar, Dynamic Island and home indicator. Auto-rotate every 4.2 s with pause and progress segments. After 1.5 s the feed scrolls by itself so the CTA shows. Use the Brand Kit logo as the avatar.
  - Facebook: wordmark `#0866ff`; round `#e4e6eb` buttons; top tab row; post with "Sponsored · globe", "See more", image, link bar `#f0f2f5` with uppercase domain, headline and `#e2e5e9` CTA; reaction bubbles; Like / Comment / Share.
  - Instagram feed: "Instagram" wordmark in the Grand Hotel font; gradient avatar ring; handle and "Sponsored"; 4:5 image; `#0095f6` CTA bar with chevron; heart, comment, send, bookmark; likes, caption with "more", "View all comments"; bottom tab bar.
  - Instagram Story: full screen on black with progress bars, avatar, "Sponsored", headline, bouncing chevron, white pill CTA with link icon, "Send message" row.
  - Google Search: coloured Google logo, search pill, All/Images/Maps/News/Videos tabs with `#1a73e8` underline, bold "Sponsored", favicon and URL, `#1a0dab` headline, `#4d5156` description, sitelinks. This one doesn't auto-scroll.
  - LinkedIn: search bar, square logo, followers, "Promoted", "+ Follow" `#0a66c2`, link bar `#eef3f8`, outlined CTA pill, Like/Comment/Repost/Send, bottom tabs.
  - Show Meta placements (Facebook, Instagram feed, Story) on Meta campaigns, Google on Google, LinkedIn on LinkedIn, and also any platform connected per `GET /api/integrations`. Use the same `brand`, `handle` and `domain` for all of them.

---

## Prompt 4: Website Builder, Hosting, Brand Kit

**Website Builder**
- History `GET /api/sites` and detail. Preview in a sandboxed iframe using `srcDoc` from `html`. New page from `POST /api/sites`, regenerate `POST /api/sites/{id}/regenerate`, versions `GET /api/sites/{id}/versions` with restore, delete.
- "Have a website?" import: `POST /api/sites/import {url}`, then fill the form from `brief`.
- Template strip `GET /api/templates?module=website`. Record usage with `POST /api/templates/use {ref,module,applied,final}`.
- Coach: `POST /api/sites/review-brief` before generating; ask for any missing high-importance facts. Three design options via `POST /api/sites/directions`.
- Brief form as a step-by-step flow, keeping these exact field names and limits:
  - **Content:** business (required, 2–120), industry 80, audience 160, offer 160, headline 200, subheadline 300, features (one per line, up to 8), contact_mode voice_agent (default) / own_phone / both, phone 30 (asked only when not voice_agent), whatsapp 30, voice_agent_id, country_code default +91, cta default "Get a free quote" (max 60), contact_email 120, address 200.
  - **Design:** layout auto "Fresh for me", showcase "Showcase", split "Split", centered "Centred", immersive "Full-bleed photo", editorial "Editorial", bento "Bento grid". decor auto/blobs/grid/dots/plain. page_type lead_gen/product/service/event/real_estate/restaurant/portfolio/app. look modern/minimal/bold/elegant/playful/corporate. theme light/dark. font jakarta/inter/serif/rounded/grotesk. primary default #6366f1, accent default #22d3ee. hero_image (https link or `asset:`/`brand:`/`ref:` id). include_logo, whatsapp_button.
  - **Project details** (intro: "These fill the Showcase design. Leave anything blank and that block is simply left out."): location_line 80, approvals 80, price_from 40, price_note 80, announcement 140, palette auto/brand/emerald/navy/charcoal/forest/plum/slate, chips (one per line, up to 5), amenities (one per line, up to 24), stats [{value 20, label 40}] up to 5, configurations [{name 60, area 60, details 240, price 40}] up to 6, distances [{place 80, time 30}] up to 12, map_url (https), brochure (a reference document id), gallery_captions.
  - **Sections:** features, about, gallery, testimonials, pricing, faq, contact_info. about 2000, gallery up to 8, testimonials [{name,quote}] up to 6 with the note "only real ones you enter are shown", pricing [{name,price,features,highlight}] up to 4, faqs [{q,a}] up to 10.
  - **Form & SEO:** form_fields name, phone, email, message, city, budget, preferred_date, company (must include phone or email), form_title 80, thank_you default "Thanks! We'll be in touch shortly.", seo_title 70, seo_description 170, meta_pixel_id, ga4_id.
  - **AI writer:** use_ai, writer from `GET /api/providers/options?kind=text`, language default English, references (document ids).
- Checks before publishing: `GET /api/sites/{id}/audit`, grouped into blockers, warnings and tips. A Page Fixer run is `POST /api/agents/page_fixer/run {site_id}`. Show `auto_fixed` from create as a toast.

**Hosting**
- Publish: `POST /api/sites/{id}/publish {name,slug,target:"aimva"|"netlify"|"vercel",custom_domain,seo_title,seo_description}`. Slug: lowercase letters, numbers and hyphens. Show visits, URL with copy and share, and redeploy via `POST /api/sites/{id}/deploy {target}`.

**Brand Kit**
- `GET/PUT /api/brand`: name 160, tagline 200, colors (hex, up to 8), voice friendly/professional/bold/playful/luxury, voice_notes 1000, style (up to 12), audience 300, avoid 1000.
- Assets: `POST /api/brand/assets` as multipart with `file` and `kind` (logo/image), set primary, delete, palette. Use the iOS photo picker and camera.
- Reference files: `GET/POST /api/references` (multipart `file`), `DELETE /api/references/{id}`.

---

## Prompt 5: content creation, voice agent, analytics, settings

**Image Generation** (`/api/content`)
- Template strip from `GET /api/templates?module=image`.
- `POST /image`: prompt 3–2000, model default `pollinations/flux` (options from `GET /models`), provider, size 1:1 / 4:5 / 9:16 / 16:9 / 1.91:1, count 1–4, negative_prompt, seed, style photographic/cinematic/illustration/3d_render/flat/minimal_product/watercolor/anime/neon, reference, use_brand, add_logo, logo_position bottom-right/bottom-left/top-right/top-left.
- "Enhance" via `POST /enhance {prompt,kind,use_brand,for_ad}`. Library `GET /assets?kind=image`, delete, save to Photos. Ad set: `GET /ad-sizes` and `POST /image/{id}/adset`.
- Thumbs up/down: `POST /api/feedback {kind,id,rating,reason,note}`.

**Video Generation**
- `POST /video`: prompt, aspect_ratio 16:9 / 9:16 / 1:1 / 4:3 / 3:4 / 21:9, duration default 5s, resolution 480p–2160p, negative_prompt, seed, camera static/push_in/pull_out/pan_left/pan_right/orbit/drone/handheld/tilt_up, style, use_brand, start_image_id, start_asset_id.
- Poll `GET /video/{id}` while it renders. Add sound: `POST /video/{id}/sound {prompt}`. Native video player.

**AI Voice Agent**
- Agents: `GET/POST /api/voice/agents`, `PUT/DELETE /api/voice/agents/{id}`, with fields name, language (from `GET /api/voice/languages`: en-US, en-IN, hi-IN, te-IN, ta-IN, es-ES, fr-FR, de-DE, ar-SA), greeting, instructions, questions (at least 2), handoff_number.
- Defaults, using these exact words:
  - Greeting: "Hi! Thanks for your interest. I'm here to ask a few quick questions so we can help you better."
  - Instructions: "You are a friendly, concise sales assistant. Keep replies under 2 sentences."
  - Questions: "May I have your full name?", "What's the best phone number or email to reach you?", "What are you looking for, and what's your budget?", "When would be a good time for a visit or demo?"
- Script templates from `GET /api/templates?module=voice` (Property enquiry qualifier, Appointment booking, Admissions counsellor, B2B demo qualifier, Service quote, Website call-back). Always load these from the API rather than hardcoding them. Applying one fills the form and stays editable. "Save as template": `POST /api/templates`.
- Practice call: `POST /api/voice/agents/{id}/calls`, each turn `POST /api/voice/calls/{id}/turn {text}`, end `POST /api/voice/calls/{id}/end`. Use the iOS microphone and speech recognition with typing as a fallback, and speak replies aloud. Add the microphone and speech permission text to Info.plist.
- Real call: `POST /api/voice/agents/{id}/dial {to}`. Call history `GET /api/voice/calls` with status, sentiment and transcript.

**Analytics**
- `GET /api/analytics/overview?days=` with 7 / 30 / 90 tabs, and insights.

**Settings**
- Tabs for profile, integrations, AI writers and agents.
- Integrations from `GET /api/integrations`: show connected status, disconnect via `DELETE /api/integrations/{provider}`, and save key-based ones via `POST /api/integrations/{provider}/key {values,account_name}` using write-only inputs. For sign-in-based connections (Meta, Google, LinkedIn, Microsoft) show "Connect on the web portal", which opens the portal in the system browser.
- AI writers: `GET/POST /api/providers`, presets from `GET /api/providers/presets`, test and delete.
- Agents: Weekly Report on/off, Page Fixer on/off, "Run now" (`POST /api/agents/weekly_report/run`).

**iOS finish**
- App icon and splash on `#fbfaf8` using the AIMVA gradient mark.
- Status bar with dark text. Keyboard must never cover the focused field. Haptics on success.
- Friendly offline state, and a final pass so every screen fits a 375pt-wide iPhone with no sideways scrolling.
- Do not build the portal's owner-only "Quality & usage" page, the marketing landing page, or the desktop visual and HTML page editors.
