// The landing hero (owner 2026-11-21, after the scroll story felt jumpy: "Mascot only, no story"). The first screen is
// the mascot, the promise and one button. He waves, then settles and watches your pointer. Scrolling away moves him and
// the words continuously with the page (no steps, no size jumps). The four-step story lives in its own calm section
// further down (Story), where each step simply fades in as it reaches you. Reduced motion keeps everything, still.
import { useEffect, useRef, useState } from "react";
import { animate, motion, useInView, useMotionValue, useScroll, useTransform } from "framer-motion";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowRight, Phone } from "lucide-react";
import { Mascot } from "../Mascot";
import { sampleImg } from "./samples";
import { cx, signupHref } from "./Site";

const ease = [0.22, 1, 0.36, 1];
const CYAN = "#5EE6F0", MARIGOLD = "#F2A33A";

// Example business and lead (fictional). The Telugu lines are the same Claude translation as ReplyScene: needs a
// native speaker's check before launch.
const STEPS = [
  { key: "page", label: "01 · Your page", title: "One sentence in. A page that brings people in.",
    text: "Smile Studio Dental typed “free check-up this Saturday”. The page and its form were live a minute later." },
  { key: "reply", label: "02 · The reply", title: "Lakshmi asks in Telugu. The answer comes back in Telugu.",
    text: "Within seconds, on WhatsApp, while the dentist is with a patient." },
  { key: "call", label: "03 · The call back", title: "Then it calls her back.",
    text: "It asks your questions, offers your free slots, and hands the warm ones to you." },
  { key: "sale", label: "04 · The sale", title: "You just close.",
    text: "Lakshmi came in on Saturday. ₹4,500, traced back to the ad that found her." },
];

function PageCard() {
  return (
    <div className="w-[260px] overflow-hidden rounded-xl bg-white shadow-2xl ring-1 ring-white/10 sm:w-[300px]">
      <div className="flex items-center gap-1.5 border-b border-black/5 bg-[#f4f6f7] px-3 py-2">
        {[0, 1, 2].map((i) => <span key={i} className="size-2 rounded-full bg-black/15" />)}
        <span className="ml-2 truncate rounded bg-white px-2 py-0.5 font-mono text-[11px] text-[#34424f]">smile-studio.aimva.in</span>
      </div>
      <motion.div initial={{ clipPath: "inset(0 0 100% 0)" }} animate={{ clipPath: "inset(0 0 0% 0)" }} transition={{ duration: 1.1, ease }}>
        <img src={sampleImg("dental", "d")} alt="A dental clinic's landing page made by AIMVA" className="block aspect-[4/3] w-full object-cover object-top" />
      </motion.div>
    </div>
  );
}

function ChatCard() {
  return (
    <div className="w-[270px] rounded-2xl bg-[#ECE5DD] p-3 shadow-2xl sm:w-[310px]">
      <motion.p initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease }}
        className="max-w-[85%] rounded-xl rounded-tl-sm bg-white px-3 py-2 text-[13px] leading-snug text-[#111]">
        <span className="block text-xs font-semibold text-[#075E54]">Lakshmi R.</span>
        నమస్తే, శనివారం ఉచిత చెకప్ దొరుకుతుందా?
      </motion.p>
      <motion.p initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.9, duration: 0.4, ease }}
        className="ml-auto mt-2 max-w-[88%] rounded-xl rounded-tr-sm bg-[#d9fdd3] px-3 py-2 text-[13px] leading-snug text-[#111]">
        నమస్తే లక్ష్మి గారు! శనివారం కుదురుతుంది. ఉదయం 11 గంటలకా, సాయంత్రం 4 గంటలకా?
        <span className="mt-0.5 block text-right text-[11px] text-[#667781]">sent in 8 seconds ✓✓</span>
      </motion.p>
    </div>
  );
}

function CallCard() {
  const bars = [0.5, 0.9, 0.6, 1, 0.7, 0.4, 0.85, 0.55, 0.75, 0.45, 0.95, 0.6];
  return (
    <div className="w-[260px] rounded-2xl bg-[#13262c] p-4 text-white shadow-2xl ring-1 ring-white/10 sm:w-[300px]">
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-full bg-[#5EE6F0]/15 text-[#5EE6F0]"><Phone className="size-4" /></span>
        <div><p className="text-sm font-semibold">Calling Lakshmi R.</p><p className="text-xs text-white/60">0:14 · in English</p></div>
      </div>
      <div className="mt-4 flex h-10 items-center gap-1" aria-hidden>
        {bars.map((h, i) => (
          <motion.span key={i} className="w-1.5 rounded-full" style={{ background: CYAN }}
            animate={{ height: [6, h * 36, 8, h * 28, 6] }} transition={{ duration: 1.4, delay: i * 0.05, repeat: Infinity, ease: "easeInOut" }} />
        ))}
      </div>
      <p className="mt-3 text-[13px] leading-snug text-white/80">“Saturday at 11 works. Shall I book it for you?”</p>
    </div>
  );
}

function SaleCard() {
  const n = useMotionValue(0);
  const text = useTransform(n, (v) => `₹${Math.round(v).toLocaleString("en-IN")}`);
  useEffect(() => { const c = animate(n, 4500, { duration: 1.2, delay: 0.5, ease }); return c.stop; }, [n]);
  const steps = ["Ad", "Page", "Reply", "Call", "Sale"];
  return (
    <div className="w-[260px] rounded-2xl bg-white p-4 shadow-2xl sm:w-[300px]">
      <p className="text-xs font-medium text-[#5b6873]">New sale · Smile Studio Dental</p>
      <motion.p className="mt-1 text-3xl font-semibold tabular-nums text-[#0f282f]">{text}</motion.p>
      <div className="mt-4 flex items-center justify-between">
        {steps.map((s, i) => (
          <div key={s} className="flex flex-1 items-center last:flex-none">
            <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: 0.2 + i * 0.15 }}
              className="size-2.5 rounded-full" style={{ background: i === 4 ? MARIGOLD : "#0b6b67" }} />
            {i < 4 && <motion.span initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 0.3 + i * 0.15, duration: 0.2 }} className="h-px flex-1 origin-left bg-[#0b6b67]/40" />}
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] text-[#5b6873]">{steps.map((s) => <span key={s}>{s}</span>)}</div>
    </div>
  );
}

const CARDS = { page: PageCard, reply: ChatCard, call: CallCard, sale: SaleCard };

// Fixed star field: positions are deterministic so the hero looks the same on every visit.
const STARS = Array.from({ length: 28 }, (_, i) => ({ x: (i * 37.7) % 100, y: (i * 61.3) % 100, d: (i % 5) * 0.8, s: 1 + (i % 3) }));

/** His size for the screen: smaller on a phone so the headline and button still fit on the first screen. */
function useHeroSize() {
  const pick = () => (typeof window === "undefined" ? 300 : window.innerWidth < 640 ? 150 : window.innerWidth < 1024 ? 230 : 300);
  const [size, setSize] = useState(pick);
  useEffect(() => { const on = () => setSize(pick()); window.addEventListener("resize", on); return () => window.removeEventListener("resize", on); }, []);
  return size;
}

export default function MascotHero({ user }) {
  const ref = useRef(null);
  // 0 when the hero fills the screen, 1 when it has scrolled away. Values follow the scroll directly, so nothing jumps.
  const { scrollYProgress: p } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const words = { opacity: useTransform(p, [0, 0.55], [1, 0]), y: useTransform(p, [0, 1], [0, -60]) };
  const him = { y: useTransform(p, [0, 1], [0, 140]), scale: useTransform(p, [0, 1], [1, 0.9]) };
  const glowY = useTransform(p, [0, 1], [0, 120]);
  // He waves hello once, then settles and watches (same body, same size: only the arm and the eyes change).
  const [waved, setWaved] = useState(false);
  const size = useHeroSize();
  useEffect(() => { const t = setTimeout(() => setWaved(true), 2600); return () => clearTimeout(t); }, []);

  return (
    <section ref={ref} aria-label="AIMVA" className="relative overflow-hidden bg-[#0b1b20] text-white">
      <motion.div aria-hidden style={{ y: glowY }} className="pointer-events-none absolute left-1/2 top-[40%] size-[820px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-25 blur-3xl lg:left-[70%]">
        <div className="size-full rounded-full" style={{ background: `radial-gradient(circle, ${CYAN} 0%, transparent 62%)` }} />
      </motion.div>
      {STARS.map((st, i) => (
        <span key={i} aria-hidden className="mk-star pointer-events-none absolute rounded-full bg-white"
          style={{ left: `${st.x}%`, top: `${st.y}%`, width: st.s, height: st.s, animationDelay: `${st.d}s` }} />
      ))}

      <div className="relative mx-auto grid min-h-[calc(100svh-3.5rem)] max-w-6xl content-center items-center gap-4 px-4 pb-10 pt-6 sm:min-h-[calc(100svh-4rem)] sm:px-6 lg:grid-cols-[1.1fr_0.9fr] lg:gap-10 lg:py-0">
        <motion.div style={words} className="relative z-10 order-2 lg:order-1">
          <motion.h1 initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease, delay: 0.15 }}
            className="serif-moment text-[36px] leading-[1.02] text-white sm:text-6xl xl:text-[76px]">
            From ad to sale, <em className="text-[#F2A33A]">in one calm place.</em>
          </motion.h1>
          <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease, delay: 0.3 }}
            className="mt-4 max-w-xl text-[15px] leading-relaxed text-white/70 sm:mt-5 sm:text-lg">
            Tell AIMVA about your business in one sentence, in any language. It writes your page and ads, answers every lead in seconds and calls them back. You just close.
          </motion.p>
          <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease, delay: 0.45 }}
            className="mt-6 flex flex-col gap-2 sm:mt-8 sm:flex-row sm:gap-3">
            <Link to={user ? "/app" : signupHref("home")} className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-[#5EE6F0] px-7 text-[15px] font-semibold text-[#0b1b20] transition-colors hover:bg-white">
              {user ? "Open app" : "Start free"} <ArrowRight className="size-4" />
            </Link>
            <a href="#story" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl px-5 text-[15px] font-medium text-white/80 ring-1 ring-white/20 transition hover:text-white hover:ring-white/40">
              See him work <ArrowDown className="size-4" />
            </a>
          </motion.div>
          <p className="mt-5 hidden text-sm text-white/50 sm:block">Free while in early access · No card needed</p>
        </motion.div>

        <motion.div style={him} className="relative order-1 flex justify-center lg:order-2">
          <Mascot face={waved} watch={waved} mood="hello" size={size} arrive="pop" />
          <span aria-hidden className="pointer-events-none absolute bottom-[2%] left-1/2 h-6 w-[30%] -translate-x-1/2 rounded-full opacity-30 blur-md" style={{ background: MARIGOLD }} />
        </motion.div>
      </div>
    </section>
  );
}

/** One step: the words and the thing he made, faded in when it reaches you. The card mounts then, so its own small
 *  motion (the page filling in, the reply arriving, the count-up) plays while you are looking at it. */
function Step({ step, i }) {
  const ref = useRef(null);
  const seen = useInView(ref, { once: true, margin: "-15% 0px" });
  const Card = CARDS[step.key];
  return (
    <li ref={ref} className="grid items-center gap-6 py-10 sm:py-14 md:grid-cols-2 md:gap-12">
      <motion.div initial={{ opacity: 0, y: 16 }} animate={seen ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.6, ease }} className={cx(i % 2 && "md:order-2")}>
        <p className="text-sm font-semibold tracking-wide text-[#F2A33A]">{step.label}</p>
        <h3 className="serif-moment mt-3 text-[28px] leading-[1.08] text-white sm:text-4xl">{step.title}</h3>
        <p className="mt-3 max-w-md text-base leading-relaxed text-white/70 sm:text-lg">{step.text}</p>
      </motion.div>
      <div className={cx("flex min-h-[220px] items-center justify-center", i % 2 ? "md:order-1 md:justify-start" : "md:justify-end")}>
        {seen && (
          <motion.div initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease, delay: 0.1 }}>
            <Card />
          </motion.div>
        )}
      </div>
    </li>
  );
}

/** The story the hero used to tell by hijacking the scroll, now a normal section you read at your own pace. */
export function Story({ user }) {
  const end = useRef(null);
  const atEnd = useInView(end, { once: true, margin: "-10% 0px" });
  return (
    <section id="story" aria-labelledby="story-h" className="scroll-mt-16 bg-[#0b1b20] text-white">
      <div className="mx-auto max-w-6xl px-4 py-14 sm:px-6 sm:py-20 lg:py-24">
        <p className="text-sm font-semibold tracking-wide text-[#5EE6F0]">One lead, start to finish</p>
        <h2 id="story-h" className="serif-moment mt-3 max-w-2xl text-[32px] leading-[1.05] text-white sm:text-5xl">Watch him take a lead from ad to sale.</h2>
        <ol className="mt-4 divide-y divide-white/10">
          {STEPS.map((s, i) => <Step key={s.key} step={s} i={i} />)}
        </ol>
        <div ref={end} className="mt-6 flex flex-wrap items-center gap-5 border-t border-white/10 pt-10">
          {atEnd && <Mascot mood="cheer" size={96} arrive="hop" />}
          <div>
            <p className="text-lg font-semibold text-white">Your first lead could be this week.</p>
            <Link to={user ? "/app" : signupHref("home")} className="mt-3 inline-flex h-11 items-center gap-2 rounded-xl bg-[#5EE6F0] px-6 text-[15px] font-semibold text-[#0b1b20] transition-colors hover:bg-white">
              {user ? "Open app" : "Start free"} <ArrowRight className="size-4" />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
