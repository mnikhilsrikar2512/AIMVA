// The landing hero: real pages made by AIMVA's page builder, set in depth (browser behind, phone in front, the lead
// that page brought in nearest to you). Every few seconds it moves to another kind of business.
// Depth is CSS 3D (no WebGL), so it costs almost nothing. Tilt follows the pointer on laptops and the scroll on phones,
// only on devices that can afford it; reduced motion and low-end phones get the same scene, still.
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useInView, useMotionValue, useScroll, useSpring, useTransform } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { ease } from "../Motion";
import { SAMPLES, sampleImg, sampleUrl } from "./samples";
import { finePointer, prefersReducedMotion, richMotion } from "./device";
import { cx } from "./Site";

const HOLD = 6; // seconds each business stays on screen

function Tick({ run }) {
  return (
    <svg viewBox="0 0 16 16" className="size-3.5" aria-hidden>
      <circle cx="8" cy="8" r="8" fill="#25d366" />
      <path d="M4.5 8.3 7 10.6l4.6-5" fill="none" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
        strokeDasharray="16" style={run ? { animation: "mk-tick 0.45s 0.5s cubic-bezier(0.22,1,0.36,1) both" } : undefined} />
    </svg>
  );
}

function LeadCard({ s, still }) {
  return (
    <motion.div key={s.key} initial={still ? false : { opacity: 0, y: 18, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 8, transition: { duration: 0.2 } }} transition={{ type: "spring", stiffness: 260, damping: 24, delay: still ? 0 : 0.9 }}
      className="rounded-2xl bg-surface/95 p-3 shadow-[var(--shadow-lift)] backdrop-blur-sm sm:p-3.5">
      <div className="flex items-center gap-2.5">
        <span className="grid size-9 shrink-0 place-items-center rounded-full text-sm font-bold text-white" style={{ background: s.lead.tint }}>{s.lead.initial}</span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-semibold text-strong">New lead · {s.lead.name}</p>
          <p className="line-clamp-2 text-xs text-muted">{s.lead.note}</p>
        </div>
        <span className="rounded-full bg-lavender px-2 py-0.5 text-xs font-semibold text-brand">{s.lead.score}</span>
      </div>
      <p className="mt-2.5 flex items-center gap-1.5 border-t border-line pt-2.5 text-xs font-medium text-ink">
        <Tick run={!still} /> WhatsApp hello sent
      </p>
    </motion.div>
  );
}

export default function HeroStage() {
  const ref = useRef(null);
  const visible = useInView(ref, { amount: 0.3 });
  const [rich] = useState(richMotion);
  const [fine] = useState(finePointer);
  const [still] = useState(prefersReducedMotion);
  const [i, setI] = useState(0);
  const [held, setHeld] = useState(false);
  const s = SAMPLES[i];
  const auto = !still && visible && !held;

  // Warm the next business's pictures while this one is on screen, so the swap never shows a blank frame.
  useEffect(() => {
    const n = SAMPLES[(i + 1) % SAMPLES.length].key;
    const t = setTimeout(() => { ["m", "d"].forEach((z) => { const im = new Image(); im.src = sampleImg(n, z); }); }, 2500);
    return () => clearTimeout(t);
  }, [i]);

  // Pointer tilt (laptops) and scroll tilt (phones), both springy and both small.
  const px = useMotionValue(0), py = useMotionValue(0);
  const sx = useSpring(px, { stiffness: 90, damping: 18 }), sy = useSpring(py, { stiffness: 90, damping: 18 });
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const scrollTilt = useSpring(useTransform(scrollYProgress, [0.25, 0.75], [7, -5]), { stiffness: 80, damping: 20 });
  const rotateY = useTransform(sx, (v) => -13 + v * 9);
  const rotateX = useTransform([sy, scrollTilt], ([y, t]) => (rich && !fine ? t : 6) - y * 7);
  const move = (e) => {
    if (!rich || !fine) return;
    const r = ref.current.getBoundingClientRect();
    px.set((e.clientX - r.left) / r.width - 0.5);
    py.set((e.clientY - r.top) / r.height - 0.5);
  };
  const leave = () => { px.set(0); py.set(0); setHeld(false); };

  return (
    <div ref={ref} className="w-full" onPointerMove={move} onPointerEnter={(e) => e.pointerType === "mouse" && setHeld(true)} onPointerLeave={leave}
      onFocus={() => setHeld(true)} onBlur={() => setHeld(false)}>
      <div className="mk-stage relative mx-auto h-[380px] w-full max-w-[580px] sm:h-[480px]" role="img"
        aria-label={`A page AIMVA's page builder made for a ${s.kind.toLowerCase()}, on a laptop and a phone, and a new lead it brought in.`}>
        <motion.div className="mk-3d absolute inset-0" style={rich ? { rotateX, rotateY } : { rotateX: 6, rotateY: -13 }}>
          {/* Laptop view, furthest back */}
          <div className="absolute left-0 top-4 w-[84%] overflow-hidden rounded-xl bg-surface shadow-[var(--shadow-lift)] sm:top-6" style={{ transform: "translateZ(-70px)" }}>
            <div className="flex items-center gap-1.5 border-b border-line px-3 py-2">
              <span className="size-2 rounded-full bg-line-strong" /><span className="size-2 rounded-full bg-line-strong" /><span className="size-2 rounded-full bg-line-strong" />
              <span className="ml-2 truncate text-xs text-faint">{s.business}</span>
            </div>
            <div className="relative aspect-[16/10] bg-surface-2">
              <AnimatePresence initial={false}>
                <motion.img key={s.key} src={sampleImg(s.key, "d")} alt="" width="960" height="600" decoding="async" fetchpriority={i === 0 ? "high" : "auto"}
                  initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.6, ease }}
                  className="absolute inset-0 size-full object-cover object-top" />
              </AnimatePresence>
            </div>
          </div>

          {/* Phone view, in front */}
          <div className="mk-phone absolute right-[1%] top-0 aspect-[9/19] w-[40%] max-w-[220px] sm:right-0" style={{ transform: "translateZ(60px)" }}>
            <div className="mk-screen">
              <AnimatePresence initial={false}>
                <motion.img key={s.key} src={sampleImg(s.key, "m")} alt="" width="560" height="1212" decoding="async"
                  initial={{ opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.6, ease, delay: 0.15 }}
                  className="absolute inset-0 size-full object-cover object-top" />
              </AnimatePresence>
            </div>
          </div>

          {/* The lead that page brought in, nearest */}
          <div className="absolute bottom-3 left-[7%] w-[74%] max-w-[290px] sm:bottom-8 sm:left-[2%] sm:w-[64%]" style={{ transform: "translateZ(130px)" }}>
            <AnimatePresence mode="wait" initial={false}><LeadCard key={s.key} s={s} still={still} /></AnimatePresence>
          </div>
        </motion.div>
      </div>

      {/* Which business: tap to switch; the bar under the active one shows when it moves on. */}
      <div className="mt-4 flex flex-wrap items-center justify-center gap-1 sm:mt-2" role="group" aria-label="Sample pages">
        {SAMPLES.map((x, n) => (
          <button key={x.key} type="button" aria-pressed={n === i} onClick={() => setI(n)}
            className={cx("relative h-9 overflow-hidden rounded-full px-3 text-xs font-semibold transition-colors", n === i ? "text-white" : "text-muted hover:text-strong")}>
            {n === i && <motion.span layoutId="hero-pill" className="absolute inset-0 rounded-full bg-strong" transition={{ type: "spring", stiffness: 420, damping: 34 }} />}
            {n === i && auto && (
              <span key={`t-${i}`} className="absolute inset-x-3 bottom-1.5 h-[2px] origin-left rounded-full bg-peach"
                style={{ animation: `mk-timer ${HOLD}s linear both` }} onAnimationEnd={() => setI((v) => (v + 1) % SAMPLES.length)} />
            )}
            <span className="relative">{x.kind}</span>
          </button>
        ))}
        <a href={sampleUrl(s.key)} target="_blank" rel="noopener" className="mk-go ml-1 inline-flex h-9 items-center gap-1 rounded-full px-3 text-xs font-semibold text-brand hover:bg-lavender/60">
          Open this sample <ArrowUpRight className="size-3.5" />
        </a>
      </div>
    </div>
  );
}
