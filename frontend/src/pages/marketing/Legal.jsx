// Privacy policy, Terms of service, Refund policy and Contact: the pages Meta app review and Razorpay KYC ask for.
// Written to match what the product does today (checked against the backend in Nov 2026). DRAFTS: a lawyer must
// review them before launch. Business details live in components/marketing/legal.js and show as [placeholders]
// until filled in. If the product changes what it collects or who it sends data to, update the matching section.
import { Link } from "react-router-dom";
import { MarketingLayout, useSeo } from "../../components/marketing/Site";
import { LEGAL, LEGAL_PAGES } from "../../components/marketing/legal";

const LABELS = {
  effectiveDate: "date", legalName: "Company legal name", address: "Registered address", supportEmail: "support email",
  phone: "phone number", hours: "support hours", grievanceOfficer: "Grievance Officer name", grievanceEmail: "grievance email",
  courtsCity: "city", serverRegion: "server region",
};

/** A business detail from legal.js, or a highlighted placeholder while it's empty. */
function F({ k }) {
  const v = LEGAL[k];
  if (v) return k.endsWith("Email") ? <a href={`mailto:${v}`} className="text-strong underline underline-offset-2">{v}</a> : <>{v}</>;
  return <mark className="rounded bg-warm-soft px-1 text-warm">[{LABELS[k]}]</mark>;
}

const Us = () => (LEGAL.legalName ? <F k="legalName" /> : <>AIMVA (<F k="legalName" />)</>);

function H({ children }) {
  return <h2 className="mt-12 text-xl font-semibold text-strong">{children}</h2>;
}

function Ul({ items }) {
  return <ul className="mt-3 list-disc space-y-2 pl-5">{items.map((t, i) => <li key={i}>{t}</li>)}</ul>;
}

function LegalPage({ slug, title, description, children }) {
  useSeo(title, description);
  return (
    <MarketingLayout from={slug}>
      <article className="mx-auto max-w-3xl px-4 pb-20 pt-8 text-[15px] leading-relaxed text-ink sm:px-6 sm:pt-14 [&_p]:mt-3">
        {!LEGAL.reviewed && (
          <p role="note" className="!mt-0 mb-8 rounded-lg border border-warm/30 bg-warm-soft px-4 py-3 text-sm text-warm">
            Draft. This page has not been reviewed by a lawyer yet and may change before AIMVA launches.
          </p>
        )}
        <nav aria-label="Legal" className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
          {LEGAL_PAGES.map((p) => (
            <Link key={p.to} to={p.to} aria-current={p.to === `/${slug}` ? "page" : undefined}
              className={p.to === `/${slug}` ? "font-semibold text-strong" : "hover:text-strong"}>{p.label}</Link>
          ))}
        </nav>
        <h1 className="serif-moment mt-6 text-[36px] leading-tight text-strong sm:text-5xl">{title}</h1>
        {slug !== "contact" && <p className="text-sm text-muted">Effective from <F k="effectiveDate" /></p>}
        {children}
      </article>
    </MarketingLayout>
  );
}

const Contact = () => <>write to <F k="supportEmail" /></>;

export function PrivacyPage() {
  return (
    <LegalPage slug="privacy" title="Privacy policy" description="What AIMVA collects, why, who it is shared with, and how to ask for a copy or deletion.">
      <p>
        This policy explains how <Us />, of <F k="address" />, handles personal data when you use the AIMVA website and app.
        It is written for India's Digital Personal Data Protection Act, 2023 and the rules made under it.
      </p>

      <H>Two kinds of people, two roles</H>
      <p>
        <strong>If you have an AIMVA account</strong> (or are invited into one), we decide how your account data is used. In the
        Act's words we are the <em>Data Fiduciary</em> for it.
      </p>
      <p>
        <strong>If you are a lead</strong>, meaning you filled in a form on a page built with AIMVA, answered an ad, messaged a
        business on WhatsApp or spoke to its call assistant, the business you contacted decides what happens to your details.
        We store and process them for that business, on its instructions. Please contact that business first; if you can't
        reach it, write to our Grievance Officer below and we will help.
      </p>

      <H>What we collect</H>
      <p><strong>About account holders</strong></p>
      <Ul items={[
        "Your name, email address and company, and the answers you give when you sign up (your industry and goals).",
        "Your password, stored only as a one-way hash. We cannot read it.",
        "Team details: who you invite, their email addresses and their role.",
        "What you create or upload: brand details, logos, product photos, reference files, generated images, videos and pages, ad drafts, templates and comments.",
        "Connected accounts: when you connect an ad account, a Facebook page, a WhatsApp number or a phone number, we store the access it grants (encrypted) and the account's name and ID.",
        "Plan and usage: your plan, its renewal date, and counts of what you use (images, call minutes and so on) so we can apply plan limits.",
      ]} />
      <p><strong>About leads, on behalf of the business</strong></p>
      <Ul items={[
        "What the lead submits or says: name, phone number, email, message, preferred date or time, and similar form answers.",
        "Where the lead came from (a page, ad, WhatsApp or a call), the language they wrote in, and the business's notes, stage and deal value.",
        "WhatsApp messages sent and received through AIMVA.",
        "Call transcripts and the answers given to the call assistant's questions. Speech is turned into text during the call; we keep the text, not an audio recording.",
      ]} />
      <p><strong>Technical data</strong></p>
      <Ul items={[
        "IP addresses, kept briefly to limit repeated sign-in, sign-up and form attempts.",
        "Security records such as failed sign-ins.",
        "Error reports from our servers. These are set up not to include email addresses, cookies or IP addresses.",
      ]} />
      <p>
        <strong>Payments.</strong> When paid plans are switched on, payments are handled by our payment processor. We never see
        or store your full card or bank details; we keep your plan, its status and the processor's reference number.
      </p>

      <H>Cookies and browser storage</H>
      <p>
        We use a small number of cookies that the app needs to work: one keeps you signed in, one remembers which workspace you
        are in, and one is set for a few minutes while you connect another account. The app also saves a few preferences in your
        browser, such as how you sort leads and which tips you've dismissed. We do not use advertising or analytics trackers on
        the AIMVA website or app.
      </p>

      <H>Why we use it</H>
      <Ul items={[
        "To run the service you asked for: build pages, write ads and replies, send WhatsApp messages, make calls and keep your lead list.",
        "To send account emails such as verification and password reset codes.",
        "To keep accounts secure and prevent abuse.",
        "To bill you, when paid plans are on, and to meet our legal and tax obligations.",
        "To answer support requests, and to understand overall use (in totals, not about individual leads) so we can improve AIMVA.",
      ]} />
      <p>
        We do not sell personal data. We do not contact your leads for our own purposes. We do not use your content or your
        leads' details to train AI models of our own.
      </p>

      <H>Who we share it with</H>
      <p>Only with the service providers that run parts of AIMVA, and only what each one needs:</p>
      <Ul items={[
        "Server and database hosting.",
        "AI services that write text, create and edit images and videos, and turn text into speech and speech into text. What you ask the AI to do, and lead messages it replies to, are sent to them to produce the result. We use their paid business services, whose terms do not let them train their models on what we send.",
        "A phone-calling service, for the call assistant.",
        "Meta's WhatsApp Business Platform, for WhatsApp messages.",
        "The ad platforms you choose to connect (Meta, Google, LinkedIn), to publish your ads and fetch your ad leads and results.",
        "An email delivery service, for account emails.",
        "An error-monitoring service, for server errors.",
        "A payment processor, once paid plans are on.",
      ]} />
      <p>
        Account holders can ask us for the current list of these providers by name. We may also share data when the law
        requires it, or with a buyer if AIMVA's business is sold, under the same protections as this policy.
      </p>

      <H>Where it is stored</H>
      <p>
        Our servers are in <F k="serverRegion" />. Some of the providers
        above process data outside India, for example in the United States. We only use countries the Government of India has
        not restricted.
      </p>

      <H>How long we keep it</H>
      <Ul items={[
        "Account data: while your account is open. When it is closed we delete it within 30 days, except records we must keep by law, such as invoices for tax purposes.",
        "Leads: until the business deletes them or closes its account.",
        "Verification and reset codes: they expire after 10 minutes.",
        "Rate-limit records (IP addresses): a short time, normally under a day.",
      ]} />

      <H>Your rights</H>
      <p>You can ask us to:</p>
      <Ul items={[
        "Give you a summary of the personal data we hold about you and who it was shared with.",
        "Correct, complete or update it.",
        "Erase it, unless we must keep it by law.",
        "Withdraw consent you gave, for anything that relies on consent. This doesn't affect what was done before.",
        "Nominate someone to exercise these rights for you if you die or become unable to.",
      ]} />
      <p>
        To do any of this, <Contact /> from the email address on your account, or contact the Grievance Officer below. We
        reply within 30 days. If you are a lead, we will pass your request to the business that holds your details and help it
        respond. If you are not satisfied with our answer, you can complain to the Data Protection Board of India.
      </p>

      <H>Security</H>
      <p>
        Passwords are hashed, access to connected accounts is encrypted, traffic is sent over HTTPS, and only people who need
        it can reach the data. No system is perfectly secure. If a breach affects your personal data, we will tell you and the
        Data Protection Board as the law requires.
      </p>

      <H>Children</H>
      <p>AIMVA is a business tool for people aged 18 and over. We do not knowingly collect children's data.</p>

      <H>Changes to this policy</H>
      <p>If we change this policy in a way that matters, we will email account holders before the change takes effect.</p>

      <H>Grievance Officer</H>
      <p>
        <F k="grievanceOfficer" />, <F k="grievanceEmail" />, <Us />, <F k="address" />.
      </p>
    </LegalPage>
  );
}

export function TermsPage() {
  return (
    <LegalPage slug="terms" title="Terms of service" description="The agreement between you and AIMVA when you use the website and app.">
      <p>
        These terms are an agreement between you (or the business you sign up for) and <Us />. By creating an account or using
        AIMVA you accept them. If you sign up for a business, you confirm you're allowed to accept them for it.
      </p>

      <H>1. Who can use AIMVA</H>
      <p>You must be 18 or older and using AIMVA for a business or profession, not as a consumer for personal use.</p>

      <H>2. Your account</H>
      <p>
        Give accurate details and keep your password private. You are responsible for what happens in your account, including
        what people you invite do there. Tell us straight away if you think someone else has got in.
      </p>

      <H>3. The service, and early access</H>
      <p>
        AIMVA helps you build pages, make images and videos, run ads, reply to leads on WhatsApp and by phone, and keep your
        leads in one list. During early access AIMVA is free, features may change or be switched off, and some depend on
        connected accounts or approvals from other companies. We will tell you before we start charging.
      </p>

      <H>4. Your content and your leads</H>
      <p>
        You own what you upload and what AIMVA makes for you, as far as the law allows. You give us permission to store,
        process and display it only to run the service for you. You confirm you have the right to use everything you upload,
        including photos, logos and the likeness of any person shown.
      </p>
      <p>
        Your leads are yours. For their personal data, you are the Data Fiduciary and we process it for you. We will:
      </p>
      <Ul items={[
        "process it only to provide AIMVA to you and as you instruct through the app;",
        "keep it confidential and protect it with reasonable security;",
        "use only the kinds of service providers listed in our Privacy policy, and tell you before adding a new kind;",
        "help you answer requests from your leads to see, correct or delete their data;",
        "tell you without undue delay if a breach affects your leads' data;",
        "delete it when you delete it or close your account, apart from what the law requires us to keep.",
      ]} />
      <p>
        You are responsible for having a lawful basis, normally consent, to collect your leads' details and to contact them by
        WhatsApp, phone or email, and for giving them your own privacy notice.
      </p>

      <H>5. Messages and calls</H>
      <p>When you use AIMVA to send WhatsApp messages or make calls, you must follow:</p>
      <Ul items={[
        "TRAI's commercial communication rules, including DLT registration, the Do Not Disturb list and permitted calling hours;",
        "WhatsApp's Business and Commerce policies;",
        "any other law that applies to your business, such as rules on medical, financial or property advertising.",
      ]} />
      <p>Contact only people who agreed to hear from you, and stop when someone asks you to. We may pause messaging or calls on an account that causes complaints or puts the shared numbers at risk.</p>

      <H>6. AI-generated content</H>
      <p>
        AI can be wrong, out of date or unsuitable. Check pages, ads, images, messages and call scripts before you publish or
        send them. You are responsible for what you publish and for the claims in your ads. We don't promise any number of
        leads, sales or results.
      </p>

      <H>7. What you must not do</H>
      <Ul items={[
        "Break the law, or help anyone else break it.",
        "Send spam, mislead people, or pretend to be someone else.",
        "Create images, video or voice of a real person without their permission.",
        "Upload malware, try to get into accounts or systems that aren't yours, or overload the service.",
        "Copy, resell or rebuild AIMVA, except as an agency running workspaces for your own clients.",
      ]} />

      <H>8. Other companies' platforms</H>
      <p>
        When you connect Meta, Google, LinkedIn, WhatsApp or a phone provider, their terms also apply, and charges they make
        (ad spend, WhatsApp conversation charges, call charges) are between you and them. We are not responsible for their
        decisions, such as rejecting an ad or limiting a number.
      </p>

      <H>9. Plans and payment</H>
      <p>
        Paid plans are billed monthly in advance in Indian rupees, plus GST, and renew automatically until you cancel. New
        accounts start with a free trial. We will give you at least 30 days' notice before a price change applies to you.
        Refunds follow our <Link to="/refund" className="text-strong underline underline-offset-2">Refund policy</Link>.
      </p>

      <H>10. Ending the agreement</H>
      <p>
        You can stop using AIMVA and ask us to close your account at any time. We may suspend or close an account that breaks
        these terms, putting it right where we reasonably can and telling you why unless the law stops us. Before your account
        is closed you can ask us for a copy of your data, including your leads.
      </p>

      <H>11. Disclaimers and liability</H>
      <p>
        AIMVA is provided as it is and as available. We work to keep it running but don't promise it will be uninterrupted or
        error-free. To the extent the law allows, we are not liable for indirect or consequential loss, such as lost profits or
        lost leads, and our total liability to you is limited to the fees you paid us in the 12 months before the claim. Nothing
        here limits liability that cannot be limited by law.
      </p>

      <H>12. Indemnity</H>
      <p>
        If someone makes a claim against us because of your content, your ads or messages, or your breach of these terms or
        the law, you will cover our reasonable costs and losses from that claim.
      </p>

      <H>13. Law and disputes</H>
      <p>These terms are governed by the laws of India. Courts in <F k="courtsCity" /> have jurisdiction.</p>

      <H>14. Changes</H>
      <p>If we change these terms in a way that matters, we will email you at least 15 days before. Continuing to use AIMVA after that means you accept the new terms.</p>

      <H>Contact</H>
      <p>Questions about these terms: <F k="supportEmail" />.</p>
    </LegalPage>
  );
}

export function RefundPage() {
  return (
    <LegalPage slug="refund" title="Refund and cancellation policy" description="How cancelling an AIMVA plan works and when you get money back.">
      <p>
        <strong>Today AIMVA is free while in early access, so there is nothing to refund.</strong> This policy applies once paid
        plans start. We will tell you before that happens.
      </p>

      <H>Free trial</H>
      <p>New accounts start with a free trial. No card is needed, and nothing is charged when it ends unless you choose a plan.</p>

      <H>Cancelling</H>
      <p>
        You can cancel a monthly plan at any time; <Contact /> from your account's email address. Cancelling stops the next
        renewal. You keep your plan until the end of the month you've paid for, and you won't be charged again.
      </p>

      <H>When we refund</H>
      <p>We refund the payment in full if:</p>
      <Ul items={[
        "you were charged twice for the same period;",
        "you were charged after you cancelled;",
        "AIMVA was unavailable through our fault for more than 72 hours in a row during the period you paid for.",
      ]} />
      <p>
        Otherwise we don't refund part of a month, or credits and plan allowances you didn't use. If something else went wrong,
        write to us anyway; we look at every request.
      </p>

      <H>Charges that aren't ours</H>
      <p>
        Ad spend goes from your ad account straight to Meta, Google or LinkedIn. WhatsApp conversation charges and phone call
        charges billed to your own accounts are between you and those companies. We don't receive this money, so we can't
        refund it; ask the company that charged you.
      </p>

      <H>How to ask for a refund</H>
      <p>
        Write to <F k="supportEmail" /> within 30 days of the charge, from your account's email address, with the payment date
        and amount. We reply within 3 working days. Approved refunds go back to the original payment method within 5 to 7
        working days; your bank may take a few more days to show it.
      </p>
    </LegalPage>
  );
}

export function ContactPage() {
  return (
    <LegalPage slug="contact" title="Contact us" description="How to reach the AIMVA team for support, billing or privacy questions.">
      <p>We read every message.</p>
      <dl className="mt-8 divide-y divide-line border-y border-line">
        {[
          ["Support and billing", <><F k="supportEmail" /><br /><F k="phone" />, <F k="hours" /></>],
          ["Privacy and grievances", <><F k="grievanceOfficer" />, Grievance Officer<br /><F k="grievanceEmail" /></>],
          ["Company", <><Us /><br /><F k="address" /></>],
        ].map(([t, d]) => (
          <div key={t} className="grid gap-1 py-5 sm:grid-cols-[12rem_1fr] sm:gap-6">
            <dt className="font-semibold text-strong">{t}</dt>
            <dd>{d}</dd>
          </div>
        ))}
      </dl>
    </LegalPage>
  );
}
