// The landing hero (owner 2026-11-21: "redesign the landing with cinematic effects and place the mascot properly, he can
// take the whole hero"). One dark stage, the mascot in the light, and a short story told by scrolling: he writes the
// page, answers the lead in her language, calls her back, and the sale lands. Each scroll step is one thing AIMVA does,
// so the motion explains the product instead of decorating it. Reduced motion keeps the story, without the movement.
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, animate, motion, useMotionValue, useMotionValueEvent, useScroll, useSpring, useTransform } from "framer-motion";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowRight, Phone } from "lucide-react";
import { Mascot } from "../Mascot";
import { sampleImg } from "./samples";
import { cx, signupHref } from "./Site";

const ease = [0.22, 1, 0.36, 1];
const CYAN = "#5EE6F0", MARIGOLD = "#F2A33A";

// Example business and lead (fictional). The Telugu lines are the same Claude translation as ReplyScene: needs a
// native speaker's check before launch.
const STAGES = [
  { key: "hello", mood: "hello", dot: "Hello" },
  { key: "page", mood: "thinking", dot: "Page", label: "01 · Your page", title: "One sentence in. A page that brings people in.",
    text: "Smile Studio Dental typed “free check-up this Saturday”. The page and its form were live a minute later." },
  { key: "reply", mood: "happy", dot: "Reply", label: "02 · The reply", title: "Lakshmi asks in Telugu. The answer comes back in Telugu.",
    text: "Within seconds, on WhatsApp, while the dentist is with a patient." },
  { key: "call", mood: "wink", dot: "Call", label: "03 · The call back", title: "Then it calls her back.",
    text: "It asks your questions, offers your free slots, and hands the warm ones to you." },
  { key: "sale", mood: "cheer", dot: "Sale", label: "04 · The sale", title: "You just close.",
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

export default function MascotHero({ user }) {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end end"] });
  const smooth = useSpring(scrollYProgress, { stiffness: 140, damping: 30 });
  const [stage, setStage] = useState(0);
  useMotionValueEvent(scrollYProgress, "change", (v) => setStage(Math.min(STAGES.length - 1, Math.floor(v * STAGES.length * 0.999))));
  const s = STAGES[stage];
  const Card = CARDS[s.key];
  // The light behind him warms from cyan to marigold as the story reaches the sale.
  const glow = useTransform(smooth, [0, 0.75, 1], [CYAN, CYAN, MARIGOLD]);
  const mascotScale = useTransform(smooth, [0, 0.2, 1], [1, 0.86, 0.86]);
  const busy = stage > 0 && stage < 4;

  return (
    <section ref={ref} aria-label="What AIMVA does" className="relative h-[480vh] bg-[#0b1b20] text-white">
      <div className="sticky top-14 flex h-[calc(100svh-3.5rem)] sm:top-16 sm:h-[calc(100svh-4rem)] flex-col overflow-hidden">
        {/* Light and stars */}
        <motion.div aria-hidden className="pointer-events-none absolute left-1/2 top-[42%] size-[900px] -translate-x-1/2 -translate-y-1/2 rounded-full opacity-25 blur-3xl lg:left-[68%]"
          style={{ background: useTransform(glow, (c) => `radial-gradient(circle, ${c} 0%, transparent 62%)`) }} />
        {STARS.map((st, i) => (
          <span key={i} aria-hidden className="mk-star pointer-events-none absolute rounded-full bg-white"
            style={{ left: `${st.x}%`, top: `${st.y}%`, width: st.s, height: st.s, animationDelay: `${st.d}s` }} />
        ))}

        <div className="relative mx-auto grid w-full max-w-6xl flex-1 items-center gap-6 px-4 sm:px-6 lg:grid-cols-[1fr_1fr] lg:gap-10">
          {/* Words */}
          <div className="relative z-10 order-2 min-h-[220px] lg:order-1 lg:min-h-[360px]">
            <AnimatePresence mode="wait">
              <motion.div key={s.key} initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12, transition: { duration: 0.2 } }}
                transition={{ duration: 0.5, ease }}>
                {stage === 0 ? (
                  <>
                    <h1 className="serif-moment text-[34px] text-white leading-[1.02] sm:text-6xl xl:text-[72px]">
                      From ad to sale, <em className="text-[#F2A33A]">in one calm place.</em>
                    </h1>
                    <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-white/70 sm:mt-5 sm:text-lg">
                      Tell AIMVA about your business in one sentence, in any language. It writes your page and ads, answers every lead in seconds and calls them back. You just close.
                    </p>
                    <div className="mt-6 flex flex-col gap-2 sm:mt-7 sm:flex-row sm:gap-3">
                      <Link to={user ? "/app" : signupHref("home")} className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-[#5EE6F0] px-7 text-[15px] font-semibold text-[#0b1b20] hover:bg-white">
                        {user ? "Open app" : "Start free"} <ArrowRight className="size-4" />
                      </Link>
                      <a href="#how" className="inline-flex h-12 items-center justify-center gap-2 rounded-xl px-5 text-[15px] font-medium text-white/80 ring-1 ring-white/20 hover:text-white hover:ring-white/40">
                        Skip the story <ArrowDown className="size-4" />
                      </a>
                    </div>
                    <p className="mt-5 hidden text-sm text-white/50 sm:block">Free while in early access · No card · Scroll to watch him work</p>
                  </>
                ) : (
                  <>
                    <p className="text-sm font-semibold tracking-wide text-[#F2A33A]">{s.label}</p>
                    <h2 className="serif-moment mt-3 text-[28px] text-white leading-[1.08] sm:text-5xl">{s.title}</h2>
                    <p className="mt-4 max-w-md text-base leading-relaxed text-white/70 sm:text-lg">{s.text}</p>
                    {stage === 4 && (
                      <Link to={user ? "/app" : signupHref("home")} className="mt-7 inline-flex h-12 items-center gap-2 rounded-xl bg-[#5EE6F0] px-7 text-[15px] font-semibold text-[#0b1b20] hover:bg-white">
                        {user ? "Open app" : "Start free"} <ArrowRight className="size-4" />
                      </Link>
                    )}
                  </>
                )}
              </motion.div>
            </AnimatePresence>
          </div>

          {/* The mascot, centre stage, and what he is doing right now */}
          <div className="relative order-1 flex items-center justify-center lg:order-2 lg:h-full">
            <motion.div style={{ scale: mascotScale }} className="relative">
              <div>
                <Mascot face mood={s.mood} size={stage === 0 ? 400 : 330} arrive="pop" watch={stage === 0} className={cx(stage === 0 ? "max-w-[44vw]" : "max-w-[26vw]", "sm:max-w-[40vw] lg:max-w-none")} />
              </div>
              {/* The ring under him glows marigold while he works */}
              <motion.span aria-hidden className="pointer-events-none absolute bottom-[1%] left-1/2 h-6 w-[38%] -translate-x-1/2 rounded-full blur-md"
                style={{ background: MARIGOLD }} animate={{ opacity: busy ? [0.35, 0.8, 0.35] : 0.2 }} transition={{ duration: 1.6, repeat: busy ? Infinity : 0 }} />
            </motion.div>
            <AnimatePresence mode="wait">
              {Card && (
                <motion.div key={s.key} initial={{ opacity: 0, x: 40, y: 20, rotate: 4 }} animate={{ opacity: 1, x: 0, y: 0, rotate: -2 }}
                  exit={{ opacity: 0, x: -30, transition: { duration: 0.2 } }} transition={{ type: "spring", stiffness: 180, damping: 22 }}
                  className="relative z-10 -ml-3 origin-left scale-[0.86] sm:scale-100 lg:absolute lg:bottom-[12%] lg:left-[-10%] lg:ml-0">
                  <Card />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Where you are in the story */}
        <div className="relative mx-auto mb-5 flex w-full max-w-6xl items-center gap-2 px-4 sm:px-6">
          {STAGES.map((x, i) => (
            <div key={x.key} className="flex flex-1 flex-col gap-1.5">
              <span className="h-[3px] overflow-hidden rounded-full bg-white/15">
                <motion.span className="block h-full origin-left rounded-full" style={{ background: i === 4 ? MARIGOLD : CYAN }}
                  initial={false} animate={{ scaleX: stage >= i ? 1 : 0 }} transition={{ duration: 0.4, ease }} />
              </span>
              <span className={cx("hidden text-xs sm:block", stage === i ? "text-white" : "text-white/40")}>{x.dot}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
