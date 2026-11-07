// Home: one promise, how it works, what's inside, who it's for, questions. Each section says something new.
import { lazy, Suspense, useRef, useState } from "react";
import { MotionConfig, motion, useMotionValueEvent, useReducedMotion, useScroll, useSpring } from "framer-motion";
import { Link } from "react-router-dom";
import { ArrowRight, AudioLines, BarChart3, Check, ChevronDown, Globe, Image, Megaphone, MessageCircle, Users } from "lucide-react";
import { rise, stagger } from "../components/Motion";
import { FinalCta, Heading, MarketingLayout, cx, signupHref, useSeo } from "../components/marketing/Site";
import { USE_CASES } from "../components/marketing/useCases";
import { useAuth } from "../lib/auth";

const ProductDemo = lazy(() => import("../components/ProductDemo"));

const STEPS = [
  { title: "Make a page or an ad", text: "Answer a few questions and your landing page, ad pictures and ad copy start already written. The page goes live in a click." },
  { title: "Leads arrive in one list", text: "Page forms, WhatsApp chats and calls land in Leads by themselves, and Meta lead forms when you sync. Scored, so the serious ones are on top." },
  { title: "AI replies, you close", text: "WhatsApp says hello within seconds and your AI assistant calls them back, through your own WhatsApp and Twilio numbers. You pick up the warm ones." },
];

const FEATURES = [
  { icon: Globe, name: "Pages", text: "Landing pages with a lead form, written for your business. Your domain, Netlify or Vercel.", tour: "page" },
  { icon: Image, name: "Pictures and videos", text: "Ad pictures from a sentence, free and in your brand's colours. Short promo videos when you add a fal.ai key.", tour: "page" },
  { icon: Megaphone, name: "Campaigns", text: "AI-written ads for Meta, Google and LinkedIn, created in your ad account as paused drafts to finish and launch. Spend syncs back.", tour: "page" },
  { icon: AudioLines, name: "Calls", text: "Practise in your browser, then connect Twilio and it rings new leads back, asks your questions and hands over to you.", tour: "reply" },
  { icon: MessageCircle, name: "WhatsApp", text: "Connect your WhatsApp Business number: a welcome within seconds, follow-ups on day 2 and day 7, and one inbox for replies.", tour: "reply" },
  { icon: Users, name: "Leads", text: "Every lead in one list, de-duplicated and scored, synced to Google Sheets or OneDrive.", tour: "pipeline" },
  { icon: BarChart3, name: "Results", text: "Spend, leads and sales per campaign, what to fix next, and a PDF report in one click.", tour: "results" },
];

const FAQ = [
  ["How much does it cost?", "Nothing while AIMVA is in early access. Paid plans will come later, and we'll tell you well before anything changes."],
  ["Do I need API keys or a developer?", "No. Pages, pictures, practice calls and analytics work from the first minute on AIMVA's built-in AI. Sending WhatsApp messages and placing real phone calls need your own WhatsApp Business and Twilio numbers; connect them, and your ad accounts, whenever you're ready."],
  ["Which languages does the call assistant speak?", "Practice calls in your browser can use English (Indian and US), Hindi, Telugu, Tamil, Spanish, French, German or Arabic, where your browser has that voice. Real phone calls through Twilio are in English today; Hindi, Telugu and Tamil voices are coming."],
  ["Can I use my own domain?", "Yes. Publish on AIMVA, point your own domain at it, or deploy to Netlify or Vercel."],
  ["I run an agency. Can each client have their own space?", "Yes. Each client gets a workspace with their own pages, campaigns, leads and results. Invite your team and the client, and turn on approvals so nothing goes live without their yes."],
  ["Where do my leads go?", "Into Leads, in your account. You can download them as Excel, CSV or a PDF report at any time, or sync them to Google Sheets or OneDrive."],
];

/** A line draws through the steps as you scroll; each step lights up when the line reaches it. */
function Steps() {
  const ref = useRef(null);
  const reduce = useReducedMotion();
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 85%", "end 60%"] });
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 24 });
  const [reached, setReached] = useState(reduce ? STEPS.length : 0);
  useMotionValueEvent(progress, "change", (v) => !reduce && setReached(Math.min(STEPS.length, Math.floor(v * STEPS.length + 0.35))));
  return (
    <ol ref={ref} className="relative mt-8 grid gap-8 sm:mt-14 md:grid-cols-3 md:gap-10">
      {/* Phones and small tablets: the steps read top to bottom along one line. */}
      <span className="absolute bottom-5 left-5 top-5 w-px bg-line-strong md:hidden" aria-hidden />
      <span className="absolute left-5 right-5 top-5 hidden h-px bg-line-strong md:block" aria-hidden />
      <motion.span className="absolute left-5 right-5 top-5 hidden h-[2px] origin-left bg-warm md:block" style={{ scaleX: reduce ? 1 : progress }} aria-hidden />
      {STEPS.map((s, i) => {
        const on = reached > i;
        return (
          <li key={s.title} className="relative grid grid-cols-[2.5rem_1fr] gap-x-4 md:block">
            <span className={cx("relative grid size-10 place-items-center rounded-full font-display text-sm font-bold transition-colors duration-300",
              on ? "bg-strong text-white" : "bg-surface text-warm shadow-[var(--shadow-soft)]")}>
              {on && i < reached - 1 ? <Check className="size-4" /> : i + 1}
            </span>
            <h3 className="mt-2 text-lg font-semibold text-strong md:mt-5">{s.title}</h3>
            <p className="col-start-2 mt-1 text-[15px] leading-relaxed text-muted md:mt-2">{s.text}</p>
          </li>
        );
      })}
    </ol>
  );
}

function Faq() {
  return (
    <div className="mt-10 divide-y divide-line border-y border-line">
      {FAQ.map(([q, a]) => (
        <details key={q} className="group py-1">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-4 py-4 text-[17px] font-medium text-strong [&::-webkit-details-marker]:hidden">
            {q}<ChevronDown className="size-5 shrink-0 text-faint transition group-open:rotate-180" />
          </summary>
          <p className="max-w-2xl pb-5 text-[15px] leading-relaxed text-muted">{a}</p>
        </details>
      ))}
    </div>
  );
}

export default function Landing() {
  useSeo(null, "AIMVA writes your landing page and ad drafts, welcomes every new lead on WhatsApp in seconds, calls them back with an AI assistant, and shows what's working. Free while in early access.");
  const { user } = useAuth();
  return (
    <MotionConfig reducedMotion="user">
      <MarketingLayout from="home">
        {/* Hero */}
        <section className="relative">
          <div className="aura pointer-events-none absolute inset-x-0 top-0 h-[640px] opacity-70" aria-hidden />
          <div className="relative mx-auto grid max-w-6xl items-center gap-10 px-4 pb-12 pt-8 sm:gap-12 sm:px-6 sm:pb-20 sm:pt-12 lg:grid-cols-[1fr_1.05fr] lg:pb-28 lg:pt-20">
            <motion.div variants={stagger} initial={false} animate="show">{/* visible without waiting for an animation frame */}
              <motion.p variants={rise} className="text-sm font-semibold text-warm">Marketing and lead replies for growing businesses</motion.p>
              <motion.h1 variants={rise} className="serif-moment mt-4 text-[44px] leading-[1.02] text-strong sm:text-6xl xl:text-[72px]">
                From ad to sale, <em className="text-warm">in one calm place.</em>
              </motion.h1>
              <motion.p variants={rise} className="mt-5 max-w-xl text-base leading-relaxed text-muted sm:mt-6 sm:text-lg">
                AIMVA writes your page and your ads. Every new lead gets a WhatsApp hello in seconds and a call back from your AI assistant. You just close.
              </motion.p>
              <motion.div variants={rise} className="mt-7 flex flex-col gap-2 sm:mt-9 sm:flex-row sm:gap-3">
                <Link to={user ? "/app" : signupHref("home")} className="btn-primary h-12 px-7 text-[15px]">{user ? "Open app" : "Start free"} <ArrowRight className="size-4" /></Link>
                <Link to="/tour" className="btn-subtle h-12 px-5 text-[15px]">See how it works</Link>
              </motion.div>
              <motion.p variants={rise} className="mt-6 text-sm text-faint">Free while in early access · No card · Connect WhatsApp and Twilio when you're ready</motion.p>
            </motion.div>
            <Suspense fallback={<div className="h-[440px] w-full rounded-[2rem] bg-surface-2/60" />}><ProductDemo /></Suspense>
          </div>
        </section>

        {/* How it works */}
        <section id="how" className="scroll-mt-20 border-t border-line">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24">
            <Heading label="How it works" title="Three steps, and the middle one runs itself." />
            <Steps />
          </div>
        </section>

        {/* What's inside: a list, not a grid of boxes */}
        <section id="features" className="scroll-mt-20 border-t border-line">
          <div className="mx-auto grid max-w-6xl gap-8 px-4 py-14 sm:gap-12 sm:px-6 sm:py-20 lg:grid-cols-[0.8fr_1.2fr] lg:py-24">
            <div className="lg:sticky lg:top-28 lg:self-start">
              <Heading label="What's inside" title="Seven tools that share one lead list." sub="A lead from an ad, a page, a call or a WhatsApp message is the same person in every tool, with one history." />
              <Link to="/tour" className="mt-6 inline-flex items-center gap-1.5 text-[15px] font-semibold text-warm hover:underline">Walk through it in the product tour <ArrowRight className="size-4" /></Link>
            </div>
            <ul className="divide-y divide-line border-y border-line">
              {FEATURES.map((f) => (
                <li key={f.name}>
                  <Link to={`/tour#${f.tour}`} className="group flex items-start gap-4 py-5">
                    <f.icon className="mt-0.5 size-5 shrink-0 text-warm" />
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold text-strong">{f.name}</span>
                      <span className="mt-1 block text-[15px] leading-relaxed text-muted">{f.text}</span>
                    </span>
                    <ArrowRight className="mt-1 size-4 shrink-0 text-faint opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100 group-focus-visible:opacity-100" />
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Who it's for: a teaser, the detail lives on /use-cases */}
        <section className="border-t border-line">
          <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24">
            <Heading label="Who it's for" title="Built for people who'd rather be doing the work." />
            <ul className="mt-8 grid gap-x-12 gap-y-6 sm:mt-12 md:grid-cols-3 md:gap-y-0">
              {USE_CASES.map((u) => (
                <li key={u.slug} className="border-t border-line-strong pt-5">
                  <Link to={`/use-cases/${u.slug}`} className="group block">
                    <p className="font-semibold text-strong">{u.short}</p>
                    <p className="mt-2 text-[15px] leading-relaxed text-muted">{u.lede}</p>
                    <span className="mt-4 inline-flex items-center gap-1.5 text-sm font-semibold text-warm">How AIMVA helps <ArrowRight className="size-4 transition group-hover:translate-x-0.5" /></span>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </section>

        {/* Questions */}
        <section id="faq" className="scroll-mt-20 border-t border-line">
          <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24">
            <Heading label="Questions" title="Good to know." />
            <Faq />
          </div>
        </section>

        <FinalCta from="home" />
      </MarketingLayout>
    </MotionConfig>
  );
}
