import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useReducedMotion } from "framer-motion";
import { PhoneCall, Sparkles } from "lucide-react";
import cx from "clsx";
import { ease } from "./Motion";

/*
 * The landing-page hero: AIMVA's real loop in ~12 seconds. A short brief is typed, the landing page
 * assembles, the matching Instagram ad slides in, and a lead arrives that the voice agent calls back.
 * It only runs while visible, and people who prefer reduced motion see the finished scene.
 */
const BRIEF = "Skyline Homes · 2 & 3 BHK near the metro · free site visit this weekend";
const STEPS = ["Brief", "Landing page", "Ad", "Lead"];
const TIMES = [3400, 2800, 2600, 3600]; // how long each phase holds

function Skyline({ className }) {
  return (
    <svg viewBox="0 0 160 100" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="sky" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stopColor="#fbcfb7" /><stop offset="1" stopColor="#c7bdfd" /></linearGradient>
      </defs>
      <rect width="160" height="100" fill="url(#sky)" />
      <circle cx="122" cy="30" r="12" fill="#fff7ed" opacity=".85" />
      {[[10, 48, 26], [40, 30, 30], [74, 40, 22], [100, 22, 28], [132, 52, 22]].map(([x, y, w], i) => (
        <g key={i}>
          <rect x={x} y={y} width={w} height={100 - y} fill={i % 2 ? "#134e5e" : "#0b6b67"} opacity={0.85 - i * 0.05} />
          {Array.from({ length: Math.floor((100 - y) / 12) }).map((_, r) => (
            <rect key={r} x={x + 5} y={y + 6 + r * 12} width={w - 10} height="4" fill="#fde68a" opacity={(r + i) % 3 ? 0.55 : 0.2} />
          ))}
        </g>
      ))}
    </svg>
  );
}

function Typed({ text, run }) {
  const [n, setN] = useState(run ? 0 : text.length);
  useEffect(() => {
    if (!run) { setN(text.length); return; }
    setN(0);
    const id = setInterval(() => setN((v) => (v >= text.length ? (clearInterval(id), v) : v + 1)), 38);
    return () => clearInterval(id);
  }, [run, text]);
  return <span>{text.slice(0, n)}{n < text.length && <span className="ml-px inline-block h-3.5 w-[2px] translate-y-0.5 animate-pulse bg-brand" />}</span>;
}

const pop = { hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0, transition: { duration: 0.45, ease } } };

export default function ProductDemo() {
  const reduce = useReducedMotion();
  const ref = useRef(null);
  const visible = useInView(ref, { amount: 0.35 });
  // Moving content stops while someone is looking closely (pointer over it or keyboard focus inside).
  const [held, setHeld] = useState(false);
  const [phase, setPhase] = useState(reduce ? 3 : 0);
  const [cycle, setCycle] = useState(0);
  useEffect(() => {
    if (reduce || !visible || held) return;
    const t = setTimeout(() => {
      if (phase < 3) setPhase(phase + 1);
      else { setPhase(0); setCycle((c) => c + 1); }
    }, TIMES[phase]);
    return () => clearTimeout(t);
  }, [phase, visible, reduce, held]);
  const at = (p) => phase >= p;

  return (
    <div ref={ref} onPointerEnter={(e) => e.pointerType === "mouse" && setHeld(true)} onPointerLeave={() => setHeld(false)} className="w-full max-sm:[zoom:0.82]" role="img" aria-label="AIMVA demo: a short brief becomes a landing page and an Instagram ad, then a lead arrives and the AI voice agent calls them back.">
      <div className="relative mx-auto h-[440px] w-full max-w-[560px] sm:h-[480px]">
        {/* Brief */}
        <motion.div key={`brief-${cycle}`} initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease }}
          className="absolute left-0 top-2 z-20 w-[230px] rounded-2xl bg-white p-3.5 shadow-[var(--shadow-lift)] sm:w-[260px]">
          <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-brand"><Sparkles className="size-3.5" /> Your brief</p>
          <p className="mt-1.5 min-h-[40px] text-[13px] leading-snug text-strong"><Typed text={BRIEF} run={!reduce && phase === 0} /></p>
        </motion.div>

        {/* Landing page */}
        <motion.div initial={false} animate={{ opacity: at(1) ? 1 : 0.35, scale: at(1) ? 1 : 0.97 }} transition={{ duration: 0.5, ease }}
          className="absolute right-0 top-16 z-10 w-[80%] overflow-hidden rounded-2xl bg-white shadow-[var(--shadow-lift)] ring-1 ring-black/5">
          <div className="flex items-center gap-1.5 border-b border-black/5 px-3 py-2">
            {["#fca5a5", "#fcd34d", "#86efac"].map((c) => <span key={c} className="size-2 rounded-full" style={{ background: c }} />)}
            <span className="ml-2 truncate rounded-full bg-slate-100 px-2.5 py-0.5 text-[10px] text-slate-500">aimva.page/skyline-homes</span>
          </div>
          <motion.div key={`page-${cycle}`} variants={{ show: { transition: { staggerChildren: 0.12 } } }} initial="hidden" animate={at(1) ? "show" : "hidden"}
            className="grid grid-cols-[1.3fr_1fr] gap-3 p-4">
            <div>
              <motion.p variants={pop} className="text-[10px] font-bold text-slate-800">Skyline Homes</motion.p>
              <motion.p variants={pop} className="mt-2 bg-gradient-to-r from-violet-600 to-orange-400 bg-clip-text text-[19px] font-extrabold leading-tight text-transparent">
                2 & 3 BHK homes near the metro
              </motion.p>
              <motion.p variants={pop} className="mt-1.5 text-[10px] text-slate-500">Free site visit this weekend · Whitefield</motion.p>
              <motion.div variants={pop} className="mt-3 overflow-hidden rounded-lg"><Skyline className="h-20 w-full" /></motion.div>
            </div>
            <motion.div variants={pop} className="rounded-xl bg-slate-50 p-2.5 shadow-sm">
              <p className="text-[10px] font-bold text-slate-800">Book a site visit</p>
              {["Name", "Phone", "Preferred date"].map((f) => <div key={f} className="mt-1.5 rounded-md bg-white px-2 py-1 text-[9px] text-slate-400 ring-1 ring-slate-200">{f}</div>)}
              <div className="mt-1.5 flex items-center gap-1 text-[8.5px] text-slate-500"><span className="size-2 rounded-sm bg-violet-500" /> Call me now</div>
              <div className="mt-2 rounded-md bg-violet-600 py-1 text-center text-[9px] font-bold text-white">Book a site visit</div>
            </motion.div>
          </motion.div>
        </motion.div>

        {/* Instagram ad */}
        <AnimatePresence>
          {at(2) && (
            <motion.div key={`ad-${cycle}`} initial={{ opacity: 0, x: -30, rotate: -4 }} animate={{ opacity: 1, x: 0, rotate: -3 }} exit={{ opacity: 0, x: -20 }}
              transition={{ type: "spring", stiffness: 200, damping: 22 }}
              className="absolute bottom-6 left-2 z-30 w-[150px] overflow-hidden rounded-[22px] bg-white p-1.5 shadow-[var(--shadow-lift)] ring-1 ring-black/10 sm:w-[170px]">
              <div className="flex items-center gap-1.5 px-1.5 py-1">
                <span className="size-5 rounded-full bg-[conic-gradient(from_200deg,#feda75,#fa7e1e,#d62976,#962fbf,#4f5bd5,#feda75)] p-[1.5px]"><span className="grid size-full place-items-center rounded-full border border-white bg-slate-800 text-[7px] font-bold text-white">S</span></span>
                <span className="leading-tight"><span className="block text-[9px] font-bold text-slate-800">skylinehomes</span><span className="block text-[8px] text-slate-400">Sponsored</span></span>
              </div>
              <div className="relative overflow-hidden rounded-xl">
                <Skyline className="h-[150px] w-full" />
                <p className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent p-2 pt-6 text-[11px] font-extrabold leading-tight text-white">From ₹45 L near the metro</p>
              </div>
              <div className="mt-1 flex items-center justify-between bg-[#0095f6] px-2 py-1.5 text-[9px] font-semibold text-white">Book a site visit <span>›</span></div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Lead arrives, agent calls */}
        <AnimatePresence>
          {at(3) && (
            <motion.div key={`lead-${cycle}`} initial={{ opacity: 0, y: 24, scale: 0.95 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10 }}
              transition={{ type: "spring", stiffness: 260, damping: 22 }}
              className="absolute bottom-2 right-0 z-30 w-[245px] rounded-2xl bg-white p-3 shadow-[var(--shadow-lift)] ring-1 ring-black/5">
              <div className="flex items-center gap-2.5">
                <span className="grid size-9 place-items-center rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 text-sm font-bold text-white">P</span>
                <div className="min-w-0 flex-1">
                  <p className="text-[13px] font-bold text-slate-800">New lead · Priya S.</p>
                  <p className="text-[11px] text-slate-500">From your page · score <b className="text-emerald-600">86</b></p>
                </div>
              </div>
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.9 }}
                className="mt-2.5 flex items-center gap-2 rounded-xl bg-violet-50 px-2.5 py-2 text-[11px] font-semibold text-violet-700">
                <span className="relative grid size-6 place-items-center rounded-full bg-violet-600 text-white">
                  {!reduce && <span className="absolute inset-0 animate-ping rounded-full bg-violet-500/50" />}
                  <PhoneCall className="relative size-3" />
                </span>
                Voice agent calling back…
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <div className="mt-3 flex justify-center gap-1.5">
        {STEPS.map((s, i) => (
          <span key={s} className={cx("relative rounded-full px-3 py-1 text-[11px] font-semibold transition-colors", phase === i ? "text-white" : "text-faint")}>
            {phase === i && <motion.span layoutId="demo-step" className="absolute inset-0 rounded-full bg-strong" transition={{ type: "spring", stiffness: 400, damping: 34 }} />}
            <span className="relative">{s}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
