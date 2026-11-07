// Product tour: the real journey, one step at a time, with small live mock-ups built from the app's own styles.
// Tabs work with the mouse, arrow keys and links (/tour#reply). Example data is labelled as such.
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, ArrowRight, Check, Download, FileText, Mail, PhoneCall } from "lucide-react";
import { ease } from "../../components/Motion";
import { FinalCta, Heading, MarketingLayout, cx, signupHref, useSeo } from "../../components/marketing/Site";

/* ---- mock-ups (example data, app styles) ---------------------------------------------------------- */
const Frame = ({ title, children, className }) => (
  <div className={cx("overflow-hidden rounded-2xl bg-surface shadow-[var(--shadow-lift)]", className)}>
    <div className="flex items-center gap-1.5 border-b border-line px-4 py-2.5">
      <span className="size-2.5 rounded-full bg-line-strong" /><span className="size-2.5 rounded-full bg-line-strong" /><span className="size-2.5 rounded-full bg-line-strong" />
      <span className="ml-3 truncate text-xs text-faint">{title}</span>
      <span className="ml-auto rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">Example</span>
    </div>
    <div className="p-5 sm:p-6">{children}</div>
  </div>
);
const Fake = ({ label, value }) => (
  <div><p className="text-xs font-medium text-muted">{label}</p><div className="mt-1 rounded-lg bg-surface-2/70 px-3 py-2 text-sm text-strong">{value}</div></div>
);

function MockSignup() {
  return (
    <Frame title="aimva · Create your account">
      <p className="text-lg font-semibold text-strong">Create your account</p>
      <div className="mt-4 grid gap-3"><Fake label="Full name" value="Meera Rao" /><Fake label="Work email" value="meera@skylinehomes.in" /></div>
      <div className="mt-5 border-t border-line pt-5">
        <p className="flex items-center gap-2 text-sm text-muted"><Mail className="size-4" /> We sent a 6-digit code</p>
        <div className="mt-3 flex gap-2">{"482916".split("").map((d, i) => <span key={i} className="grid size-10 place-items-center rounded-lg bg-surface-2 font-mono text-lg text-strong">{d}</span>)}</div>
      </div>
    </Frame>
  );
}

function MockWelcome() {
  return (
    <Frame title="aimva · Welcome">
      <p className="text-xs text-muted">1 of 7</p>
      <p className="serif-moment mt-2 text-2xl leading-tight text-strong">Who are you setting AIMVA up for?</p>
      <div className="mt-4 space-y-2">
        {[["My company", true], ["Just me", false], ["My clients", false]].map(([t, on]) => (
          <div key={t} className={cx("flex items-center gap-3 rounded-xl px-3.5 py-3 text-sm", on ? "bg-strong text-white" : "bg-surface-2/70 text-strong")}>
            <span className={cx("grid size-4 place-items-center rounded-full", on ? "bg-white text-strong" : "ring-1 ring-line-strong")}>{on && <Check className="size-3" />}</span>{t}
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs text-faint">Every question can be skipped. Back keeps what you typed.</p>
    </Frame>
  );
}

function MockPage() {
  return (
    <Frame title="skylinehomes.in · your page">
      <div className="rounded-xl bg-gradient-to-br from-[#fbe3d3] to-[#f3e9dc] p-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-warm">Skyline Homes</p>
        <p className="mt-2 text-xl font-bold leading-tight text-strong">2 & 3 BHK near the metro</p>
        <p className="mt-1 text-sm text-ink">Free site visit this weekend</p>
        <ul className="mt-3 space-y-1 text-xs text-ink">{["RERA approved projects", "Close to metro & schools", "Easy home-loan help"].map((f) => <li key={f} className="flex items-center gap-1.5"><Check className="size-3 text-warm" />{f}</li>)}</ul>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-[1fr_auto]">
        <div className="rounded-lg bg-surface-2/70 px-3 py-2 text-sm text-muted">Name, phone…</div>
        <span className="btn-primary pointer-events-none h-9 text-sm">Book a site visit</span>
      </div>
      <p className="mt-4 flex items-center gap-2 text-xs text-emerald-700"><span className="size-1.5 rounded-full bg-emerald-500" /> Live · Ad pictures and copy drafted for Meta and Google</p>
    </Frame>
  );
}

function MockLead() {
  return (
    <Frame title="aimva · Leads">
      <div className="divide-y divide-line">
        {[["Arjun Mehta", "Website", 82, true], ["Kavya Reddy", "Meta form", 64, false], ["Imran Khan", "WhatsApp", 41, false]].map(([n, s, sc, fresh]) => (
          <div key={n} className="flex items-center gap-3 py-3">
            <div className="min-w-0 flex-1">
              <p className="flex items-center gap-2 text-sm font-semibold text-strong">{n}{fresh && <span className="rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-xs font-bold uppercase text-emerald-700">New</span>}</p>
              <p className="text-xs text-muted">{s} · {fresh ? "just now" : "2h ago"}</p>
            </div>
            <span className="h-1.5 w-16 overflow-hidden rounded-full bg-surface-2"><span className={cx("block h-full", sc >= 70 ? "bg-warm" : "bg-line-strong")} style={{ width: `${sc}%` }} /></span>
            <span className="w-6 text-right text-sm tabular-nums text-strong">{sc}</span>
          </div>
        ))}
      </div>
      <p className="serif-moment mt-4 text-center text-xl text-strong">The first one is in.</p>
    </Frame>
  );
}

function MockReply() {
  return (
    <Frame title="aimva · Arjun Mehta">
      <div className="space-y-3">
        <div className="max-w-[85%] rounded-2xl rounded-tl-sm bg-emerald-50 px-3.5 py-2.5 text-sm text-ink">Hi Arjun, thanks for your enquiry with Skyline Homes! Would you like to visit the site? Reply with a day and time that suits you.</div>
        <p className="text-xs text-faint">WhatsApp · sent 12 seconds after the form</p>
        <div className="flex items-center gap-3 rounded-xl bg-surface-2/70 px-3.5 py-3">
          <span className="grid size-8 place-items-center rounded-full bg-strong text-white"><PhoneCall className="size-4" /></span>
          <div className="min-w-0 flex-1"><p className="text-sm font-semibold text-strong">Call assistant · English</p><p className="truncate text-xs text-muted">Budget ₹80 L to ₹1 Cr · wants a Saturday visit</p></div>
          <span className="text-xs text-muted">2:41</span>
        </div>
        <p className="text-xs text-muted">Follow-ups on day 2 and day 7 until they reply.</p>
      </div>
    </Frame>
  );
}

function MockPipeline() {
  const cols = [["New", 9], ["Contacted", 3], ["Qualified", 2], ["Won", 2]];
  return (
    <Frame title="aimva · Pipeline">
      <div className="grid grid-cols-4 gap-2">
        {cols.map(([s, n], i) => (
          <div key={s}>
            <p className="text-xs font-medium text-muted">{s}</p>
            <p className="font-display text-2xl font-bold tabular-nums text-strong">{n}</p>
            <div className="mt-2 space-y-1.5">{Array.from({ length: Math.min(3, n) }).map((_, j) => <span key={j} className={cx("block h-6 rounded-md", i === 2 && j === 0 ? "bg-warm/80" : "bg-surface-2")} />)}</div>
          </div>
        ))}
      </div>
      <p className="mt-4 text-xs text-muted">Arjun moved to Qualified after the call. Deal value ₹92,00,000.</p>
    </Frame>
  );
}

function MockResults() {
  return (
    <Frame title="aimva · Results">
      <div className="grid grid-cols-3 gap-3 border-b border-line pb-4">
        {[["Spent", "₹49,664"], ["Leads", "18"], ["Per lead", "₹2,759"]].map(([l, v]) => <div key={l}><p className="font-display text-xl font-bold text-strong">{v}</p><p className="text-xs text-muted">{l}</p></div>)}
      </div>
      <p className="mt-4 text-sm text-ink"><b className="text-strong">Cheapest leads:</b> Free site visit (Meta) at ₹5,402 a lead.</p>
      <p className="mt-1 text-sm text-ink"><b className="text-strong">Next:</b> call your 4 hottest leads now.</p>
      <div className="mt-4 flex items-center gap-3 rounded-xl bg-surface-2/70 px-3.5 py-3">
        <FileText className="size-5 text-warm" />
        <span className="flex-1 text-sm text-strong">AIMVA Results 2026-11-07.pdf</span>
        <Download className="size-4 text-muted" />
      </div>
    </Frame>
  );
}

/* ---- steps ---------------------------------------------------------------------------------------- */
const STEPS = [
  { id: "signup", tab: "Sign up", title: "Sign up in a minute", text: "Name, email, password. A 6-digit code proves the email is yours. No card.", Mock: MockSignup },
  { id: "welcome", tab: "A few questions", title: "Answer a few questions, skip any", text: "Who it's for, what you sell, your website, where you're online, how customers find you. Each answer changes what AIMVA writes for you.", Mock: MockWelcome },
  { id: "page", tab: "Your first page", title: "Your first page is already written", text: "The page, its offer and lead form come from your answers. Ad pictures and copy for Meta, Google and LinkedIn are drafted alongside. Publish on AIMVA or your own domain.", Mock: MockPage },
  { id: "lead", tab: "First lead", title: "The first lead arrives", text: "From the page form, a WhatsApp chat, a call, or a Meta lead form when you sync it: one list, scored so the serious ones are on top. Home celebrates the first one.", Mock: MockLead },
  { id: "reply", tab: "AI reply", title: "A reply in seconds", text: "With your WhatsApp number connected, the welcome goes out in seconds (without it, AIMVA drafts it for a one-tap send). Connect Twilio and the call assistant rings back and asks your questions. Follow-ups go out on day 2 and day 7.", Mock: MockReply },
  { id: "pipeline", tab: "Pipeline", title: "Move them along", text: "New, contacted, qualified, won. Add the deal value, notes and the next step on each lead. Hot leads still waiting come first in Results' next steps.", Mock: MockPipeline },
  { id: "results", tab: "Results", title: "See what paid off, share the report", text: "Spend, leads, cost per lead and sales per campaign, what to fix next, and a clear PDF report you can send to a partner or client.", Mock: MockResults },
];

export default function Tour() {
  useSeo("Product tour", "Walk through AIMVA step by step: sign up, answer a few questions, publish your first page, get a lead, let AI reply, and see what paid off.");
  const { hash } = useLocation();
  const fromHash = Math.max(0, STEPS.findIndex((s) => `#${s.id}` === hash));
  const [i, setI] = useState(fromHash);
  useEffect(() => { setI(fromHash); }, [fromHash]);
  const tabs = useRef([]);
  // Phones: the steps are a scrolling row; keep the chosen pill in view (also when a link opens step 5),
  // scrolling only the row, never the page.
  useEffect(() => {
    const id = setTimeout(() => {
      const el = tabs.current[i], row = el?.parentElement;
      if (!row || row.scrollWidth <= row.clientWidth) return;
      row.scrollLeft += el.getBoundingClientRect().left - row.getBoundingClientRect().left - 16;
    }, 0);  // a timeout, not requestAnimationFrame: frames can be paused while the window isn't in front
    return () => clearTimeout(id);
  }, [i]);
  const go = (n, focus = false) => {
    const k = (n + STEPS.length) % STEPS.length;
    setI(k); window.history.replaceState(window.history.state, "", `#${STEPS[k].id}`);  // shareable link, no scroll jump
    if (focus) tabs.current[k]?.focus();
  };
  const onKey = (e) => {
    if (["ArrowDown", "ArrowRight"].includes(e.key)) { e.preventDefault(); go(i + 1, true); }
    if (["ArrowUp", "ArrowLeft"].includes(e.key)) { e.preventDefault(); go(i - 1, true); }
    if (e.key === "Home") { e.preventDefault(); go(0, true); }
    if (e.key === "End") { e.preventDefault(); go(STEPS.length - 1, true); }
  };
  const s = STEPS[i];

  return (
    <MotionConfig reducedMotion="user">
      <MarketingLayout from="tour">
        <section className="mx-auto max-w-6xl px-4 pb-24 pt-8 sm:px-6 sm:pt-14 lg:pt-20">
          <Heading as="h1" label="Product tour" title="From sign-up to your first sale." sub="Seven steps, about as long as they take in the app. Pick a step, or use the arrow keys." />

          <div className="relative mt-12 grid gap-10 lg:grid-cols-[280px_1fr] lg:gap-14">
            {STEPS.map((st) => <span key={st.id} id={st.id} className="absolute -top-24" aria-hidden />)}{/* targets for /tour#step links */}
            {/* Steps: a vertical list on desktop, a scrolling row on phones */}
            <div role="tablist" aria-label="Tour steps" aria-orientation="vertical" onKeyDown={onKey}
              className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 lg:mx-0 lg:flex-col lg:gap-0 lg:overflow-visible lg:border-l lg:border-line lg:px-0">
              {STEPS.map((st, k) => (
                <button key={st.id} ref={(el) => { tabs.current[k] = el; }} role="tab" id={`tab-${st.id}`} aria-selected={k === i} aria-controls={`panel-${st.id}`} tabIndex={k === i ? 0 : -1}
                  onClick={() => go(k)}
                  className={cx("flex shrink-0 items-center gap-3 rounded-full px-4 py-2 text-left text-sm transition lg:-ml-px lg:rounded-none lg:border-l-2 lg:py-3 lg:pl-5",
                    k === i ? "bg-strong text-white lg:border-warm lg:bg-transparent lg:font-semibold lg:text-strong" : "bg-surface-2/70 text-muted hover:text-strong lg:border-transparent lg:bg-transparent")}>
                  <span className={cx("hidden size-6 shrink-0 place-items-center rounded-full text-xs font-bold tabular-nums lg:grid", k < i ? "bg-strong text-white" : k === i ? "bg-warm text-white" : "bg-surface-2 text-muted")}>{k < i ? <Check className="size-3" /> : k + 1}</span>
                  {st.tab}
                </button>
              ))}
            </div>

            <div>
              <div className="mb-6 h-1 overflow-hidden rounded-full bg-surface-2" aria-hidden>
                <motion.div className="h-full bg-warm" animate={{ width: `${((i + 1) / STEPS.length) * 100}%` }} transition={{ duration: 0.4, ease }} />
              </div>
              <AnimatePresence mode="wait" initial={false}>{/* first step shows at once; only changes animate */}
                <motion.div key={s.id} role="tabpanel" id={`panel-${s.id}`} aria-labelledby={`tab-${s.id}`}
                  initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.3, ease }}
                  className="grid items-start gap-8 xl:grid-cols-[1fr_1.1fr]">
                  <div>
                    <p className="text-sm font-medium tabular-nums text-faint">Step {i + 1} of {STEPS.length}</p>
                    <h2 className="serif-moment mt-2 text-3xl leading-tight text-strong sm:text-4xl">{s.title}</h2>
                    <p className="mt-4 text-[17px] leading-relaxed text-muted">{s.text}</p>
                    <div className="mt-8 flex items-center gap-2">
                      <button type="button" className="btn-subtle h-10 px-3" onClick={() => go(i - 1)} disabled={i === 0} aria-label="Previous step"><ArrowLeft className="size-4" /></button>
                      {i < STEPS.length - 1
                        ? <button type="button" className="btn-ghost h-10" onClick={() => go(i + 1)}>Next: {STEPS[i + 1].tab} <ArrowRight className="size-4" /></button>
                        : <Link to={signupHref("tour")} className="btn-primary h-10">Start free <ArrowRight className="size-4" /></Link>}
                    </div>
                  </div>
                  <s.Mock />
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </section>
        <FinalCta from="tour" title="That's the whole loop." text="Sign up and it takes about a minute to reach step three with your own business." />
      </MarketingLayout>
    </MotionConfig>
  );
}
