# AIMVA design: from sign-up to leads, in one place

Written 2026-11-06. This is the rule book for every screen. When a screen disagrees with it, change the screen or change this file on purpose.

## 1. The one job

A business owner signs up because they want **leads**. Everything AIMVA makes (pages, pictures, videos, ads, call and WhatsApp assistants) is only a way to get there. So the product is judged by one number: **minutes from sign-up to first real lead**. Today that path has 7 checklist steps, a pop-up wizard and 16 sidebar items. The target is 4 steps, no pop-ups, and a sidebar you can read in one glance.

## 2. What "space and freedom" means here

"Freedom" does **not** mean more options on every screen. More controls on screen is what makes work feel cramped. Here it means:

| Principle | What it looks like | What it rules out |
|---|---|---|
| **One primary action per view** | One dark button. Everything else is a ghost button, a link or a ⋯ menu. | Two "Generate" buttons, a row of five equal buttons. |
| **Progressive disclosure** | Start with the 1–4 fields that matter. "More options" opens the rest. Defaults are good enough to ship. | Showing model, seed, provider and negative prompt before the first picture. |
| **The work gets the room** | 52–72px icon rail, slim header, content column up to 72rem. Focus mode (`\`) hides the rail and bell entirely. | Permanent side panels, sticky banners, stat boxes above every page. |
| **Every place is reachable without the sidebar** | `Ctrl/Cmd + K` opens one palette: go anywhere, create anything, find a lead by name, switch client. | Features you can only reach through a menu three levels deep. |
| **Nothing is said twice** | Next steps live only in the bell panel ("For you"). Recent activity lives only on Home. Charts live only in Analytics. | The same "Connect Meta" prompt on Home, Ads and Settings. |
| **Lists, not boxes** | Rows with hairline dividers. Numbers as plain type. Cards only for things you can pick up and move (an image, a campaign). | Grids of stat tiles, cards inside cards. |
| **Undo over confirm** | Delete and "Not now" act at once and show an Undo toast. Confirm dialogs only for money or anything public that cannot be pulled back. | "Are you sure?" on every delete. |
| **Calm and warm** | Warm paper background, one terracotta accent only for urgent things (hot lead, overdue reply), serif only for greetings and celebrations. 12px text floor, 4.5:1 contrast. | Gradients on working UI, red badges on everything. |

## 3. Two kinds of people, one app

The same screens serve both. What changes is **what is open by default**, never what exists.

| | First-time owner (no lead yet) | Familiar owner (leads flowing) |
|---|---|---|
| Home shows | "Your first lead" path: 4 steps, one open at a time, the rest folded to one line. | One sentence of numbers, then **Activity**: every lead, call, page, picture and campaign in one list. Pipeline beside it. |
| Navigation | Same rail. Items they haven't touched yet are not hidden: hiding makes people think features are missing. | Same rail, plus palette (`Ctrl/Cmd + K`), bell (`N`), focus mode (`\`). |
| Forms | Defaults pre-filled from the business profile (industry template). | Same defaults, plus "More options" remembered open if they opened it last time. |
| Help | Inline one-line hints under fields. No tours. | Shortcuts listed in the palette under "Keyboard". |
| Celebrations | Big moment for each first: page live, first visitor lead, first call. | Rarer and bigger thresholds: 10/50/100 leads, first sale, cheaper leads than last month. |

**The switch between the two is data, not a setting.** Home is in "getting started" mode until the first lead exists or the person presses "Skip the guide". Nobody has to find a toggle.

## 4. The journey, step by step

### 4.1 Sign up → Welcome → Home (about 1 minute)
1. Sign up with name, email, password. Verify by email.
2. **Welcome page**: its own calm page, shown once, never a pop-up. **One question per screen**, each answer changes what AIMVA does, any question can be skipped, Back keeps what was typed. 7 or 8 screens depending on the answers, about a minute.

| # | Question | Why we ask (what changes) |
|---|---|---|
| 1 | Who are you setting AIMVA up for? My company / Just me (personal brand) / My clients (agency) / The company I work for | Personal: wording says "you", no team question. Clients: the business step asks for the agency, and Home offers "Add a client". |
| 2 | Business (or your name / agency name), kind of business, what matters most | Pre-writes pages, call script and ad copy from the industry template. |
| 3 | Do you already have a website? (Yes + address / Not yet) | Yes: "Let AIMVA do it from skylinehomes.in" on Home, and the Launch agent reads it. Not yet: the first AIMVA page becomes the website. |
| 4 | Where are you online already? Instagram, Facebook, Google Business, LinkedIn, WhatsApp Business, YouTube, none (+ handles) | Decides which accounts we suggest connecting first, and lets pictures match their look. |
| 5 | How do customers find you today? An agency runs our ads (+ name) / We run ads ourselves / Word of mouth / Just starting | Agency: AIMVA sits alongside them, tracking their leads and calling back. Self: ad drafts and checks. Word of mouth or starting: page and WhatsApp first, no spend. |
| 6 | Roughly what goes into ads each month? (only if they advertise) | Suggested budgets only. Never spent without them. |
| 7 | Who else will use AIMVA? Just me / 2–10 / more (not asked for "Just me") | Team: an "Invite" nudge after setup. Solo: no team UI anywhere. |
| 8 | Brand: logo (colours picked from it), colours, tone of voice, who you sell to, tagline | Saved straight into the Brand kit, so the first picture, page and ad are on-brand. |

Answers 1 and 3–7 are saved with `POST /api/onboarding/answers` (being added by the backend). Until a server has it, they are kept in the browser and sent again on the next save.
3. Land on Home. The greeting sits above the path.

**Every successful sign-in lands on Home**, wherever the person was before. The only exception is an invite link, which has to open to be accepted.

### 4.2 The path to the first lead (on Home, inline)

| # | Step | Done when | Fast path |
|---|---|---|---|
| 1 | **About your business**: name, industry, main goal. Inline, 3 fields. | Industry saved. | Saving also writes a voice assistant script for the industry. |
| 2 | **Your page**: make a landing page with a lead form, then publish it. | A page is published. | "Let AIMVA do it": paste your website or one sentence, and the Launch agent builds the page, ad drafts and the call-back assistant. |
| 3 | **Try your call assistant**: a one-minute practice call in the browser. | One call exists. | Optional: "Skip this step". |
| 4 | **Your first lead**: share the page link (copy button, WhatsApp share). Waiting state listens live. | One lead exists. | "Send yourself a test lead" opens the live page in a new tab. |

Connecting ad accounts, WhatsApp and Sheets is **not** on the path. Those show up as next steps in the bell once the first lead is in, because asking for Facebook permissions before someone has seen value is where people drop off.

Only the current step is open. Done steps fold to one line with a check. Steps can be done in any order (opening Websites from the rail also counts).

### 4.3 First lead → running
When the first lead arrives: the biggest celebration in the product (see section 6), Home switches to running mode, and the bell gets the next three suggestions (call the lead, connect WhatsApp, run an ad).

### 4.4 Running: everything in one place
Home becomes the place where everything that happened shows up:

- **One sentence of numbers**: "12 leads in the last 30 days, 3 hot. ₹420 a lead." Plain type, no boxes. Links to Analytics for charts.
- **Activity**: one list of leads, calls, pages, pictures, videos and campaigns, newest first, filter chips (All, Leads, Calls, Pages…), one action per row (Call, Open, Publish, Finish). Live: a new lead slides in at the top.
- **Pipeline and top leads** in a narrow side column on wide screens, below on phones.
- **Launch something new** is a quiet button in the header, not a big card every visit.

## 5. Navigation

16 items became 11, ordered as the journey runs. Nothing was deleted: the rest is one keystroke away.

```
Home
Leads
— Make —        Pages · Pictures · Videos
— Reach —       Campaigns · Calls · WhatsApp
— See —         Results · Analytics
Settings (bottom)
```

- **Campaigns** is one entry. Meta, Google and LinkedIn are tabs at the top of the page.
- **Hosting** is reached from Pages (⋯ → Domains and deploys) and from the palette.
- **Brand kit** is reached from Settings, Pictures and the palette.
- **Quality and usage** (platform owners only) stays in the palette and the rail for admins.

### Shortcuts (power users)
| Key | Does |
|---|---|
| `Ctrl/Cmd + K` | Palette: go to, create, find a lead, switch client, sign out |
| `N` | Open the bell panel (next steps and updates) |
| `\` | Focus mode: hide rail and bell, the page gets the full width |
| `Esc` | Close any panel |

## 6. Celebrations (the gamified part)

Points, levels and badges were rejected on purpose. A clinic owner does not want a "Lead Hunter Level 3" badge; it reads as a toy, and it trains people to chase the badge instead of the sale. What works is the slot-machine part of games without the arcade look: **real outcomes, unpredictable timing, a rising ladder of intensity**.

### 6.1 Milestones (each fires once, ever, per workspace)
| Milestone | Intensity |
|---|---|
| First page live | Medium |
| First lead | **Big** |
| First call answered by the assistant | Medium |
| First hot lead (score 70+) | Medium |
| First won lead (first sale) | **Big** |
| 10 leads | Medium |
| 50 leads | Big |
| 100, 250, 500, 1000 leads | Big |
| 5 won leads | Medium |
| Setup path finished | Small |

### 6.2 Intensity ladder
- **Small**: a warm toast with a short line. No motion.
- **Medium**: toast plus a short confetti burst from the corner.
- **Big**: a centred moment with a serif headline, full-screen confetti for under 2 seconds, one number ("Your first lead, 2 days after signing up"), and one action (Call them / Share). Closes on any key.

### 6.3 Not every time
- Each milestone fires **once** and is remembered.
- Ordinary repeats (every new lead, every new picture) are **not** celebrated. The live list and the bell already show them.
- At most **one celebration per 4 hours**. Extra ones wait and the bigger one wins.
- Never interrupt work: if a dialog or the editor is open, or focus mode is on, the moment waits until the person is back somewhere calm.
- Wording rotates from a small pool, so the same words never show twice in a row.
- **Existing accounts are not flooded**: the first time this ships, milestones already reached are marked as seen silently.
- `prefers-reduced-motion` turns confetti off; the words stay.

### 6.4 Progress you can feel (without a score)
- The setup path shows "2 of 4".
- On running Home, one faint line under the numbers names the **next** milestone: "8 more leads to 50". It is progress, not a to-do, so it does not break the "next steps only in the bell" rule.

## 7. Working alone or together

Most owners work alone, and the app must never make them feel they are missing a team. Collaboration is **invisible until it is used**, then always one click away.

| | Solo owner | Owner with a team | Agency with clients |
|---|---|---|---|
| Rail | No switcher, no team UI. | Same rail. Team lives in Settings → Team. | Client switcher under the logo. |
| How they get there | — | Settings → Team → Invite (email + role). Also "Invite someone" in the palette. | "Add a client" in the switcher or palette creates a workspace for that business. |
| Bell | Next steps and updates. | Plus: "Priya joined", items waiting for their approval. | Plus: client approvals and change requests. |
| Who did what | Hidden (it's always them). | Activity rows name who did it when it wasn't you. | Same, per client. |

**Roles**, in plain words shown at invite time:
- **Admin**: everything, including team and billing.
- **Editor**: makes and publishes pages, pictures, campaigns; calls leads. No team or billing.
- **Client**: sees their leads, pages and results. Approves or asks for changes. Can't edit.

**Approvals** (agency + client): with "Ask the client before anything goes live" switched on for a workspace, Publish and Launch become "Send for approval". The client sees it in their bell with Approve / Ask for changes (a comment is required for changes). The person who asked sees "Waiting for approval" on the item and a toast when it is decided.

**Backend** (built by the backend thread): `GET /api/workspaces` (first entry is always your own, `active` marks the current one), `POST /api/workspaces/{id}/switch` (cookie `aimva_ws`), `POST /api/workspaces`, `GET /api/workspaces/{id}/members`, `POST .../invites {email, role}`, `/api/approvals`. Client role gets 403 on any write except approvals, auth, workspaces and feedback, so the client view hides every create and edit button and Settings. A 403 "You don't have access to that workspace any more" means they were removed: switch back to their own account and say so.

## 8. Screens still missing (backend exists, no UI yet)
| Endpoint | Where it goes |
|---|---|
| `/api/billing`, `/api/billing/plans`, `/api/billing/checkout` | Settings → Plan. Credits left as one line in the account menu. Billing is switched off today. |
| `/api/sites/{id}/domain`, `/domain/verify` | Pages → ⋯ → Your own web address, with the DNS check inline. |
| `/api/whatsapp/scheduled` | WhatsApp → message composer → "Send later". The 24-hour rule explained in one line. |
| Approvals list | Bell → Next steps, plus a badge on the item. |

## 9. Loading, guardrails, empty states and downloads

**Loading that shows progress, not just a spinner.**
- Lists load as skeleton rows in the shape of the list, so the page never jumps.
- Jobs that take seconds to minutes (pictures, pages, videos) show the step they are probably on ("Writing the headline…"), a timer with "of about 35s", and a bar that only the real result finishes. Past 1.6× the usual time it says "Taking a little longer than usual". Videos say "You can leave this page".
- Any button still working after 8 seconds changes its label to "Still working…".

**Guardrails against repeated clicks.**
- A busy button is disabled. A button whose action returns a promise disables itself until it finishes.
- The same write (same method, address and body) sent again while the first is in flight reuses the first request. Two clicks can never create two campaigns or send two messages.
- Double and triple clicks on any button count once. Controls meant to repeat (Undo, Redo, A+ and A−) opt out.
- An action with nothing to act on (download with no rows, including a filter that matches nothing, or while still loading) is shown disabled and muted, with a tooltip that says why ("Nothing to download yet", "No leads match these filters"). Never hidden, never a click that silently does nothing. Main create actions ("Add lead", "Make my page") stay enabled, because they are how the list stops being empty. Controls that only make sense with data ("Show 12 more", "Copy link", "Clear filters") appear only once there is something to show, copy or clear.

**Empty states.** No box around them. A faint sketch of what will appear (rows, tiles or a chat), a serif line saying what goes here, one line on where it comes from, and one action. A filtered list with no results says "No leads match" and offers "Clear filters" instead.

**Icons.** Familiar extras are icon-only with a tooltip and a screen-reader label: download, delete, edit, copy, refresh/sync, open, more (⋯). Main actions keep their words ("Publish", "Add lead", "Make my page"), because a bare icon for the main job gets misclicked and has to be learned.

**Downloads.** One download icon with a tooltip. If a page has several formats, it opens a small menu; with one format it downloads directly.
| Page | Formats |
|---|---|
| Leads | Excel, PDF, CSV |
| Results | Excel (campaigns and products sheets), PDF |
| Analytics | Excel (per day, sources, pipeline), PDF |
Every format is a real file that lands in Downloads, named like "AIMVA Leads 2026-11-07.pdf". Excel is a real .xlsx made in the browser. The PDF is a report written for the reader, never a picture or print of the page: drawn with jsPDF (loaded only when asked for) by one builder per page in `frontend/src/lib/reports/` on a shared kit (`kit.js`: header, KPI row, takeaways, bar and line charts, callouts, tables, footer).
- Cover header: AIMVA, report name, business or client name, the period (or "as of"), when it was made.
- At a glance: 3–5 big numbers, then 2–5 plain sentences worked out from the data ("Meta brought the most leads: 5 of 18 (28%)"). A sentence the data can't support is left out.
- Leads: by stage and by source as bars, the hot leads to call first, then every lead on screen (filters respected).
- Results: spend, leads, cost per lead, sales won and return; best campaign and the one that needs attention; spend by campaign; every campaign sorted by spend; the next 7 days; what to do next.
- Analytics: leads per day as a line, top sources and the pipeline as bars, visits → leads per page, where the money went.
- Footer on every page: AIMVA, business, report name, page X of Y. Terracotta accents, warm panels, 9–11pt body, Indian number format, and an embedded Noto Sans subset so ₹ prints correctly.
Nothing ever opens the print window. If a file can't be made, an error toast says so.

## 9b. Marketing site (public pages)

Pages: Home `/`, Product tour `/tour`, Use cases `/use-cases` and `/use-cases/:slug` (local businesses, solo founders and freelancers, agencies), 404. All share `components/marketing/Site.jsx` (top bar, footer, `useSeo`, `Heading`, `FinalCta`); use-case content lives in `components/marketing/useCases.js`.
- **Top bar.** Sticky, always with a background (warm paper at 80–90% with blur), a hairline once scrolled, so the page never shows through unreadably. Links: Product tour, Use cases, Features, FAQ, then Log in and Start free; signed-in visitors see "Open app". Phones get a menu sheet (Esc closes it).
- **Each section says something new.** Home: promise, three steps, what's inside (a list, not a card grid), who it's for (a teaser), questions, one closing call to action. The detail lives on the tour and use-case pages, never repeated on Home.
- **Lists over boxes.** Hairline-divided rows, numbers in plain type, single column with room. Fraunces only for big headlines; one terracotta accent.
- **Honest.** No invented logos, testimonials, user counts or prices. Pricing reads "Free while in early access". Mock-ups in the tour are built from the app's own styles and marked "Example"; use-case examples quote the real industry templates.
- **Integrated.** Sign-up links carry `?from=<page>`; use-case links also carry `for=` and `industry=`, so onboarding starts with that answer picked (`lib/signupHint.js`). The app's ⌘K palette has "Product tour".
- **Fast.** Every route is lazy-loaded, so `/` doesn't download the app (≈150 kB gzipped of JavaScript on first load, no three.js). Content never depends on a scroll animation to become visible.
- **Sticky needs `overflow-x: clip`** on html/body, never `hidden` (hidden makes body a scroll container and breaks sticky bars).

## 10. Every-page rules (checklist for review)
- Failed loads say so and offer "Try again". They never look empty.
- Every action available on hover is also available by keyboard and on touch.
- Delete has Undo. Money and public actions have a confirm.
- Empty states say what will appear and give one action.
- Copy is sentence case, no jargon ("Pictures", not "Image Generation"; "Calls", not "AI Voice Agent").
- Money is ₹ everywhere. Never show file names like `.env` or code paths to owners.

## 11. What was built in this pass
- Rail reorganised into the journey order (section 5), with a client switcher that only appears once there is more than one workspace.
- Settings → Team: invite by email with a role, remove members, cancel invites, and the per-client approval switch.
- `Ctrl/Cmd + K` palette and `\` focus mode.
- Home rewritten: inline 4-step path for new owners, one-sentence numbers plus Activity for running owners, no pop-up wizard, Launch moved behind a button.
- Campaigns: Meta, Google, LinkedIn as tabs on one page.
- Celebrations engine (section 6) with confetti that respects reduced motion.
- Welcome page after sign-up (business, then brand into the Brand kit). Every sign-in lands on Home.
- Loading, guardrails, empty states and downloads (section 9).
- Fixed: budgets and spend showed `$` instead of `₹`; Meta and Settings pages showed `backend/.env` to owners.

### Not done yet
- Celebrations remember what was shown in the browser only. Moving that to the server (so a second device doesn't celebrate again) needs a small endpoint.
- Approvals in the bell, Team, Plan, domains and "Send later" screens (section 8).
- Nothing here has been clicked through against a live backend with real data.
