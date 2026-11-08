# Team console: design

The console is where the AIMVA team (Owner, Management, Development, Support, Accounts) looks after customers. It sits inside the app at `/app/console`, uses the same design system as the customer app (`frontend/src/index.css`, `design.md`), and appears only for staff. The scope and rules are in the PRD (Claude Doc "AIMVA Team Console PRD"). This file covers how it looks and behaves.

## Principles

1. **Find, see, fix, on record.** Every screen helps someone find a customer, see what's wrong and fix it with a reason. Nothing else.
2. **Calm and compact.** Lists with hairline dividers, not cards. Numbers as plain type. 12px text minimum. One warm accent (`--color-warm`) only for something that needs a person: locked sign-in, past due, failures.
3. **The role decides what's on screen.** Buttons the role can't use are not shown at all (no greyed-out "you can't"). The server checks again anyway.
4. **A change always asks why.** Every action opens a small dialog with a required reason (5+ characters). The dialog says what will happen in one sentence, and that the change is logged.
5. **No customer content.** The console shows counts, never lead names, phone numbers, messages or transcripts.

## Where it lives

- Rail item **Team console** (icon `ShieldCheck`) in the Account group, shown when `user.staff_role` is set.
- Tabs: Overview (Owner, Management), Tasks, Customers, Billing (Owner, Management, Accounts), Activity, Team (Owner). The first tab is Overview for owners and managers, Billing for Accounts, Tasks for everyone else.
- A teammate who is also a client in some agency's workspace still sees the console; it ignores the workspace they're switched into.
- **Quality and usage** (the existing Owner page) shows for roles with `quality.view` (Owner, Management, Development). Template review on that page stays Owner-only.
- `Ctrl/Cmd+K` finds both pages and "Find customer…".
- The page header shows the person's role as a quiet chip ("Support").

## Layout

```
┌ rail ┬───────────────────────────────────────────────────────────────┐
│      │ Team console                                  [Support]       │
│      │ Customers · Activity · Team                                    │
│      ├──────────────────────────────┬────────────────────────────────┤
│      │ [ Search email, name, id  ]  │ Shop Kumar          Trial · 9d │
│      │ All · People · Workspaces    │ shop@… · joined 3 Nov          │
│      │ Any status ▾                 │ ⚠ Sign-in locked (5 tries)     │
│      │──────────────────────────────│ [Unlock] [Credits] [Plan] [⋯]  │
│      │ Shop Kumar      Trial  12 ·2h│────────────────────────────────│
│      │ Smile Dental    Active 40 ·1d│ Usage this period              │
│      │   run by owner@…             │ Pictures   12 / 30             │
│      │ …                            │ Calls       3 / 15 min         │
│      │                              │ Last 30 days                   │
│      │                              │ Leads 12 · Calls 3 (1 failed)  │
│      │                              │ Members · Connected · History  │
└──────┴──────────────────────────────┴────────────────────────────────┘
```

- **Desktop (≥1024px):** list on the left (about 380px), the customer on the right. The selected id is in the URL (`/app/console?c=42`), so a link can be pasted into a chat.
- **Tablet and phone:** the list fills the screen. Tapping a row opens the customer full screen with a back arrow. The actions row becomes one "Actions" button that opens a sheet.

## Overview (Owner and Management)

The first tab for owners and managers. It answers two questions: how is the platform doing, and what is each teammate doing.

- A 7 / 30 day switch.
- One stat strip: active accounts (any lead, picture, page or campaign in the period), new customers, leads captured for customers, paying customers with the past-due count.
- **Needs someone**: warm lines only when non-zero: past due, trials ending within 7 days, locked sign-ins, failed calls, WhatsApp and pictures. Customer-related lines have a "Look" link to Customers.
- **What the team is doing**: one row per person (owners first), with open tasks (doing, overdue in warm), tasks done in the period, changes made in the console with the top three kinds, customers opened, and last active. Under it: "Counts what people do in this console. Work done elsewhere shows only through the tasks they close." It is not time tracking and should not be read as one.

## Tasks (everyone)

- Default tab for Development and Support: **Mine**, the tasks given to me, urgent first, then soonest due.
- Owners and managers also get **Everyone's** with a person filter, and **Assign a task** (title, who, due date, details, urgent). A task can be about a customer: "Assign a task" on the customer pane fills that in.
- Each row: a checkbox to mark it done, the title, Urgent in warm, then "person · about customer · due 12 Nov · from Priya". Overdue dates are warm and bold. A status menu (To do, Doing, Done, Cancelled) and, for owners and managers, a reassign menu.
- The assignee can change status and the details note. Only owners and managers change title, person, priority or due date.
- Every assignment and status change goes in the Activity log.

## Billing (Owner, Management, Accounts; read-only)

The first tab for Accounts. Nothing on it changes data; plan changes and credits stay with Management and Owners.

- While payments aren't live, an amber notice says the numbers are list prices from each plan, not money received, and that AIMVA has no GST invoices yet.
- Stat strip: monthly revenue (active paid plans at list price), past due (₹ and accounts), on trial (and expired), invoiced by you (active plans with no card).
- A table of every account with a plan: customer, plan, monthly ₹, status, billed by (Invoice, card processor, or none), period end. A status filter. Clicking a customer opens them in Customers.
- Credits given away in the last 30 / 90 / 365 days, with the reason.
- **Excel** downloads both lists as one workbook (sheets "Plans" and "Credits").

## Customers

**List row** (one line on desktop, two on phone): name, then a muted line with email or "run by agency@…". On the right: plan status word, lead count, last activity ("2h"). Status colours: active is plain ink, trial is muted, past due and expired use warm. A staff account gets a small "Team" chip.

**Filters:** a segmented control (All, People, Workspaces) and one status menu. The search box filters after typing pauses (300ms). Fifty rows per page, then "Show more".

**Customer pane**, top to bottom:

1. Name, email, joined date, plan and days left.
2. Alerts, only if any: locked sign-in, not verified, past due, failures in the last 30 days. One warm line each.
3. Actions the role allows: Unlock (only if locked), Credits, Plan, Sign out everywhere, and for owners and managers "Assign a task".
4. **Usage this period**: one line per meter, with "used / limit" and a thin bar. Unlimited shows "no limit".
5. **Last 30 days**: leads, calls, WhatsApp, pages, campaigns, pictures and videos, with failures in warm.
6. **Members** (workspace) or **Workspaces** (person), with roles. Pending invites are muted.
7. **Connected**: names only, as chips.
8. **Credits**: active grants with expiry and note.
9. **History**: the last 20 staff actions on this customer, as in the Activity list.

## Action dialogs

All dialogs use the same layout: a one-sentence title, the fields, a **Reason** textarea (required, with the placeholder "What happened? This goes in the log."), then Cancel and the action button.

| Action | Fields | Button | Notes |
|---|---|---|---|
| Credits | What (meter menu), how many, for how long (days) | Grant | Support sees "Up to 50, for up to 30 days" and the inputs are capped |
| Plan | Plan menu with ₹ price per month | Change plan | Says "Invoiced by you, no card needed" |
| Unlock sign-in | — | Unlock | Says how many wrong tries |
| Sign out everywhere | — | Sign out everywhere | Danger style. Says "They'll sign in again with their password" |

After an action: a toast ("Granted 20 pictures to Shop Kumar"), the pane refreshes, and the new line shows at the top of History.

## Activity

A single list, newest first. Each row: when ("2h"), who and their role, what in plain words ("granted 20 pictures to shop@…"), and the reason in muted text under it. Filters: action type and person. A row with a customer links to that customer. Support sees only customer actions.

Plain words for each action: `customer.view` "opened", `credits.grant` "granted", `plan.change` "moved … from Trial to Growth", `signin.unlock` "unlocked sign-in for", `signin.revoke` "signed … out everywhere", `team.add` "added … as Support", `team.role` "changed … to Management", `team.remove` "removed … from the team", `task.assign` "assigned “…” to", `task.status` "marked “…” done", `template.publish` / `template.dismiss`.

## Team (Owner only)

- **Owners**: emails from the server, each with state. A note says "Owners are set on the server (ADMIN_EMAILS)."
- **Teammates**: email, name, role menu (Management, Development, Support), state ("Active", "Not verified", "Hasn't signed up"), and a remove icon. A role change takes effect at once and asks for no reason (the log records it).
- **Add teammate**: an email field and a role menu in one line.
- Under the list, a collapsed "What each role can do" with the permission table from the PRD.

## States

- Loading: `ListSkeleton` rows in the list, a skeleton in the pane.
- Empty search: "No one matches “xyz”." plus a Clear button.
- No customer selected (desktop): a quiet line, "Pick someone on the left."
- Error: the same `Notice` pattern as the rest of the app, with Retry.
- 403 (role removed while the page is open): toast "Your role changed. Ask an owner." and go Home.

## Copy rules

- Say "customer" for a person, "client workspace" for an agency's client. Say "AI" or "pictures", never a vendor name, except Owner-only views.
- Money in ₹ with Indian grouping (₹12,999).
- Dates are relative under a week ("2h", "3d"), then "3 Nov".
