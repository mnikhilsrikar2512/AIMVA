# Legal pages: notes for the owner and the lawyer

The app has four public pages: `/privacy`, `/terms`, `/refund`, `/contact` (`frontend/src/pages/marketing/Legal.jsx`).
They are linked from the public site footer and under the sign-up button. They are **drafts written by an AI, not
legal advice**. A lawyer must read them before launch.

## Before launch

1. Fill in the business details in `frontend/src/components/marketing/legal.js` (company name, address, emails,
   phone, hours, Grievance Officer, courts city, server region, effective date). Empty values show on the pages as
   highlighted `[placeholders]`.
2. Have a lawyer review Privacy, Terms and Refund. Then set `reviewed: true` in the same file to remove the "Draft"
   banner.
3. Use `https://<your domain>/privacy` as the privacy policy URL in Meta app review, and the four URLs for Razorpay KYC.

## Promises in the pages that you must keep true

Each of these is true of the code today (checked Nov 2026) or is a promise you must be able to honour.

| Promise | Status |
|---|---|
| AI providers don't train on what we send ("paid business services") | **Only true with paid API keys.** Google's free Gemini API tier may use inputs to improve its products. Check each provider's API terms. |
| No advertising or analytics trackers on the AIMVA site/app | True today. If you add analytics (GA, Meta pixel, Clarity), update the Cookies section. |
| Calls keep a transcript, not an audio recording | True today (no Twilio recording is turned on). |
| Error reports exclude emails, cookies and IPs | True: Sentry runs with `send_default_pii=False`. |
| Account data deleted within 30 days of closing | **No delete feature yet** (separate work in progress). Until it ships, deletion is a manual job. |
| Copy of your data on request, including leads | **No export feature yet** (separate work in progress). Manual until it ships. |
| Reply to rights requests within 30 days; refund replies within 3 working days | Your process, not code. |
| Email account holders before material changes | Your process. There is no "accepted version" record in the database yet. |

## Choices made in the drafts that a lawyer should look at

- **Service providers are listed by kind, not by name** (hosting, AI services, calling, email, error monitoring,
  payments), following the rule that vendor names stay hidden from users. Meta, Google and LinkedIn are named because
  users connect them themselves. The pages offer the named list on request. Agencies and a DPDP audit may expect the
  names published. The current list: the VPS host, Google (Gemini), fal.ai, Sarvam AI, Twilio, Meta (WhatsApp Cloud
  API), Google Ads, LinkedIn, the SMTP provider (Gmail), Sentry or GlitchTip, Razorpay.
- **Sign-up shows "By creating an account you agree to the Terms…"** under the button, not a checkbox. DPDP asks for
  a clear affirmative act for consent; a lawyer may prefer a checkbox, and a record of which version was accepted.
- **Lead data:** the customer business is described as the Data Fiduciary and AIMVA as its processor. The Terms carry
  a short processing clause (section 4) in place of a separate Data Processing Agreement. Agency customers may ask for
  a full DPA.
- **Customer sites' lead forms** ask "I agree to be contacted about this enquiry" but don't link a privacy notice, and
  the consent isn't stored on the lead. The business needs its own notice there. Not changed here.
- **STOP replies** aren't mentioned, because opting out by replying STOP doesn't work yet. Add a line to the Privacy
  page once it does.
- Liability cap = fees paid in the last 12 months; refund window 30 days; outage refund after 72 hours in a row.
  These are business choices; change freely.
- Meta's app review crawler may not run JavaScript. These pages are rendered by the app, so if Meta rejects the URL,
  the fix is a static HTML copy of `/privacy`.
