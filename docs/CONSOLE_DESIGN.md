# Team console: design

The console is where the AIMVA team (Owner, Management, Development, Support) looks after customers. It sits inside the app at `/app/console`, uses the same design system as the customer app (`frontend/src/index.css`, `design.md`), and appears only for staff. The scope and rules are in the PRD (Claude Doc "AIMVA Team Console PRD"). This file covers how it looks and behaves.

## Principles

1. **Find, see, fix, on record.** Every screen helps someone find a customer, see what's wrong and fix it with a reason. Nothing else.
2. **Calm and compact.** Lists with hairline dividers, not cards. Numbers as plain type. 12px text minimum. One warm accent (`--color-warm`) only for something that needs a person: locked sign-in, past due, failures.
3. **The role decides what's on screen.** Buttons the role can't use are not shown at all (no greyed-out "you can't"). The server checks again anyway.
4. **A change always asks why.** Every action opens a small dialog with a required reason (5+ characters). The dialog says what will happen in one sentence, and that the change is logged.
5. **No customer content.** The console shows counts, never lead names, phone numbers, messages or transcripts.

## Where it lives

- Rail item **Team console** (icon `ShieldCheck`) in the Account group, shown when `user.staff_role` is set.
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

## Customers

**List row** (one line on desktop, two on phone): name, then a muted line with email or "run by agency@…". On the right: plan status word, lead count, last activity ("2h"). Status colours: active is plain ink, trial is muted, past due and expired use warm. A staff account gets a small "Team" chip.

**Filters:** a segmented control (All, People, Workspaces) and one status menu. The search box filters after typing pauses (300ms). Fifty rows per page, then "Show more".

**Customer pane**, top to bottom:

1. Name, email, joined date, plan and days left.
2. Alerts, only if any: locked sign-in, not verified, past due, failures in the last 30 days. One warm line each.
3. Actions the role allows: Unlock (only if locked), Credits, Plan, and under ⋯ Sign out everywhere.
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

Plain words for each action: `customer.view` "opened", `credits.grant` "granted", `plan.change` "moved … from Trial to Growth", `signin.unlock` "unlocked sign-in for", `signin.revoke` "signed … out everywhere", `team.add` "added … as Support", `team.role` "changed … to Management", `team.remove` "removed … from the team", `template.publish` / `template.dismiss`.

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
