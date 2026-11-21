// The landing hero, after the Updraft template the owner liked (2026-11-21): a bright sky, real things drifting in it,
// a big serif promise in the middle. Borrowed: the airy sky with soft clouds, objects floating at different depths
// around a centred serif headline (one italic phrase), a small pill eyebrow, a warm pill button beside a glass one,
// and the objects lifting away at their own speed as you scroll. Ours: the objects are AIMVA's own work (a WhatsApp
// reply, an ad, a lead, a call, a page, a rupee coin), drawn in HTML so they stay sharp at any size, and the mascot
// floats among them. No code, images or copy come from the template.
//
// Laptops and tablets get everything (owner: full power there). Phones get the same sky with four objects and no
// scroll-linked scatter, so an ad click still paints fast. Reduced motion: everything sits still.
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { motion, useInView, useMotionValueEvent, useReducedMotion, useScroll, useSpring, useTransform } from "framer-motion";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowRight, BadgeIndianRupee, Check, Phone, Sparkles, UserRound } from "lucide-react";
import { Mascot } from "../Mascot";
import { signupHref } from "./Site";
import { canWebGL } from "./device";

const SkyObjects3D = lazy(() => import("./SkyObjects3D"));

const ease = [0.22, 1, 0.36, 1];

/** True on laptops and tablets (a fine pointer or a wide screen): they get the heavy version. */
export function useFullPower() {
  const q = "(min-width: 768px)";
  const [on, setOn] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q);
    const f = () => setOn(m.matches);
    m.addEventListener("change", f);
    return () => m.removeEventListener("change", f);
  }, []);
  return on;
}

// ---- the things drifting in the sky ------------------------------------------------------------------------------
function Reply() {
  return (
    <div className="w-[230px] rounded-2xl bg-[#ECE5DD] p-2.5 shadow-[0_30px_60px_-20px_rgba(15,40,47,0.45)]">
      <p className="max-w-[88%] rounded-xl rounded-tl-sm bg-white px-2.5 py-1.5 text-[12px] leading-snug text-[#111]">
        <span className="block text-[11px] font-semibold text-[#075E54]">Lakshmi R.</span>Is the free check-up on Saturday?
      </p>
      <p className="ml-auto mt-1.5 max-w-[90%] rounded-xl rounded-tr-sm bg-[#d9fdd3] px-2.5 py-1.5 text-[12px] leading-snug text-[#111]">
        Yes! 11 am or 4 pm?<span className="mt-0.5 block text-right text-[11px] text-[#667781]">8 seconds ✓✓</span>
      </p>
    </div>
  );
}
function Ad() {
  return (
    <div className="w-[200px] overflow-hidden rounded-2xl bg-white shadow-[0_30px_60px_-20px_rgba(15,40,47,0.45)]">
      <div className="flex items-center gap-2 px-2.5 py-2">
        <span className="grid size-6 place-items-center rounded-full bg-[#0b6b67] text-[11px] font-bold text-white">S</span>
        <span className="text-[12px] font-semibold text-[#111]">Smile Studio<span className="block text-[11px] font-normal text-[#737373]">Sponsored</span></span>
      </div>
      <div className="grid aspect-[4/3] place-items-center bg-[linear-gradient(135deg,#0b6b67,#5EE6F0)] px-4 text-center">
        <span className="font-serif text-[20px] italic leading-tight text-white">Free check-up this Saturday</span>
      </div>
      <div className="flex items-center justify-between px-2.5 py-2 text-[12px]"><span className="text-[#737373]">smile-studio.in</span><span className="rounded-md bg-[#eef1f3] px-2 py-1 font-semibold text-[#111]">Book now</span></div>
    </div>
  );
}
function Lead() {
  return (
    <div className="flex w-[210px] items-center gap-3 rounded-2xl bg-white p-3 shadow-[0_30px_60px_-20px_rgba(15,40,47,0.45)]">
      <span className="grid size-9 shrink-0 place-items-center rounded-full bg-[#F2A33A]/20 text-[#9A5200]"><UserRound className="size-4" /></span>
      <span className="min-w-0 text-[12px] leading-snug text-[#0f282f]"><b className="block font-semibold">New lead · Lakshmi R.</b><span className="text-[#5b6873]">From your ad · 2 min ago</span></span>
    </div>
  );
}
function Call() {
  return (
    <div className="w-[190px] rounded-2xl bg-[#13262c] p-3 text-white shadow-[0_30px_60px_-20px_rgba(15,40,47,0.55)]">
      <div className="flex items-center gap-2"><span className="grid size-7 place-items-center rounded-full bg-[#5EE6F0]/15 text-[#5EE6F0]"><Phone className="size-3.5" /></span><span className="text-[12px] font-semibold">Calling back · 0:14</span></div>
      <div className="mt-2.5 flex h-6 items-center gap-[3px]" aria-hidden>
        {[0.5, 0.9, 0.6, 1, 0.7, 0.4, 0.85, 0.55, 0.75, 0.45, 0.95, 0.6, 0.8].map((h, i) => (
          <span key={i} className="w-1 rounded-full bg-[#5EE6F0]" style={{ height: `${h * 100}%` }} />
        ))}
      </div>
    </div>
  );
}
function Page() {
  return (
    <div className="w-[220px] overflow-hidden rounded-xl bg-white shadow-[0_30px_60px_-20px_rgba(15,40,47,0.45)]">
      <div className="flex items-center gap-1 border-b border-black/5 bg-[#f4f6f7] px-2 py-1.5">{[0, 1, 2].map((i) => <span key={i} className="size-1.5 rounded-full bg-black/15" />)}<span className="ml-1.5 rounded bg-white px-1.5 font-mono text-[11px] text-[#34424f]">smile-studio.in</span></div>
      <div className="space-y-1.5 p-3">
        <span className="block h-2.5 w-3/4 rounded bg-[#0f282f]" /><span className="block h-1.5 w-full rounded bg-[#0f282f]/15" /><span className="block h-1.5 w-5/6 rounded bg-[#0f282f]/15" />
        <span className="mt-2 flex items-center gap-1.5 rounded-md bg-[#eef6f6] p-1.5 text-[11px] text-[#0b6b67]"><Check className="size-3" /> Lead form · live</span>
      </div>
    </div>
  );
}
function Coin({ size = 76 }) {
  return (
    <div className="grid place-items-center rounded-full shadow-[0_24px_40px_-14px_rgba(154,82,0,0.55),inset_0_-6px_10px_rgba(154,82,0,0.35),inset_0_6px_10px_rgba(255,255,255,0.6)]"
      style={{ width: size, height: size, background: "radial-gradient(circle at 35% 30%, #FFE3A3, #F2A33A 55%, #C97A12)" }}>
      <span className="font-serif text-[0.5em] font-semibold text-[#7a4300]" style={{ fontSize: size * 0.42 }}>₹</span>
    </div>
  );
}
function Sale() {
  return (
    <div className="flex items-center gap-2.5 rounded-full bg-white py-2 pl-2 pr-4 shadow-[0_30px_60px_-20px_rgba(15,40,47,0.45)]">
      <span className="grid size-8 place-items-center rounded-full bg-[#0b6b67] text-white"><BadgeIndianRupee className="size-4" /></span>
      <span className="text-[13px] font-semibold tabular-nums text-[#0f282f]">₹4,500 sale</span>
    </div>
  );
}

// x / y: where it rests (% of the hero), d: depth 0 (far) to 1 (near). Nearer things are bigger, move more with the
// pointer and leave faster when you scroll. rot: its tilt. phone: shown on phones too.
const THINGS = [
  { C: Reply, x: 14, y: 34, d: 0.9, rot: -6 },
  { C: Ad, x: 83, y: 30, d: 0.75, rot: 7 },
  { C: Lead, x: 80, y: 70, d: 1, rot: -4 },
  { C: Call, x: 16, y: 74, d: 0.6, rot: 5 },
  { C: Page, x: 28, y: 10, d: 0.35, rot: -10 },
  { C: () => <Coin size={84} />, x: 64, y: 9, d: 0.5, rot: 12, phone: { x: 80, y: 10 } },
  { C: () => <Coin size={48} />, x: 6, y: 56, d: 0.3, rot: -18, phone: { x: 14, y: 12 } },
  { C: Sale, x: 62, y: 86, d: 0.45, rot: 3 },
];

function Thing({ t, i, p, px, py, full, reduce }) {
  const k = 0.4 + t.d * 0.8;  // nearer = faster
  const y = useTransform(p, [0, 1], [0, -(260 + t.d * 520)]);
  const x = useTransform(p, [0, 1], [0, (t.x < 50 ? -1 : 1) * (60 + t.d * 220)]);
  const r = useTransform(p, [0, 1], [t.rot, t.rot + (t.x < 50 ? -14 : 14)]);
  const mx = useTransform(px, (v) => v * 40 * t.d), my = useTransform(py, (v) => v * 30 * t.d);
  return (
    <motion.div aria-hidden className="pointer-events-none absolute" style={{ left: `${full ? t.x : t.phone.x}%`, top: `${full ? t.y : t.phone.y}%`, x: full ? x : 0, y: full ? y : 0, rotate: full ? r : t.rot, zIndex: Math.round(t.d * 10) }}>
      <motion.div style={{ x: mx, y: my, scale: full ? 0.82 + t.d * 0.38 : 0.72 }} initial={reduce ? false : { opacity: 0, y: 60 }}
        animate={{ opacity: 1, y: 0 }} transition={{ duration: 1.2, ease, delay: 0.15 + i * 0.08 }} className="-translate-x-1/2 -translate-y-1/2">
        <motion.div animate={reduce ? undefined : { y: [0, -10 * k, 0], rotate: [0, 1.5, 0] }} transition={{ duration: 6 + i * 0.7, repeat: Infinity, ease: "easeInOut" }}>
          <t.C />
        </motion.div>
      </motion.div>
    </motion.div>
  );
}

// Soft clouds: blurred white shapes on three layers, drifting slowly sideways (no images, so nothing to download).
const CLOUDS = [
  { x: -8, y: 64, w: 56, h: 26, o: 0.95, l: 0 }, { x: 58, y: 70, w: 60, h: 30, o: 0.95, l: 0 }, { x: 22, y: 82, w: 70, h: 26, o: 1, l: 0 },
  { x: 70, y: 18, w: 34, h: 14, o: 0.7, l: 1 }, { x: 4, y: 14, w: 30, h: 12, o: 0.6, l: 1 }, { x: 36, y: 44, w: 30, h: 10, o: 0.45, l: 1 },
  { x: -10, y: 36, w: 40, h: 16, o: 0.8, l: 2 }, { x: 80, y: 46, w: 36, h: 16, o: 0.75, l: 2 },
];

export default function SkyHero({ user }) {
  const ref = useRef(null);
  const reduce = useReducedMotion();
  const full = useFullPower() && !reduce;
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  const p = useSpring(scrollYProgress, { stiffness: 120, damping: 30, mass: 0.4 });
  const words = { y: useTransform(p, [0, 1], [0, -120]), opacity: useTransform(p, [0, 0.6], [1, 0]) };
  const sky = useTransform(p, [0, 1], [0, 160]);
  const mascotY = useTransform(p, [0, 1], [0, -220]);
  const cloudLayer = [useTransform(p, [0, 1], [0, -80]), useTransform(p, [0, 1], [0, -200]), useTransform(p, [0, 1], [0, -360])];
  const px = useSpring(0, { stiffness: 50, damping: 18 }), py = useSpring(0, { stiffness: 50, damping: 18 });
  const onMove = (e) => {
    if (!full) return;
    const r = e.currentTarget.getBoundingClientRect();
    px.set((e.clientX - r.left) / r.width - 0.5); py.set((e.clientY - r.top) / r.height - 0.5);
  };
  const [waved, setWaved] = useState(false);
  useEffect(() => { const t = setTimeout(() => setWaved(true), 3200); return () => clearTimeout(t); }, []);
  // Laptops and tablets with WebGL: real lit 3D objects. Everyone else: two drawn coins (no app screenshots).
  const [gl] = useState(() => typeof window !== "undefined" && canWebGL());
  const three = full && gl;
  const seen = useInView(ref, { margin: "100px 0px" });
  const scrollRef = useRef(0), pointerRef = useRef({ x: 0, y: 0 });
  useMotionValueEvent(p, "change", (v) => { scrollRef.current = v; });
  useMotionValueEvent(px, "change", (v) => { pointerRef.current.x = v; });
  useMotionValueEvent(py, "change", (v) => { pointerRef.current.y = v; });
  const things = three ? [] : full ? THINGS : THINGS.filter((t) => t.phone);
  const HEAD = ["From", "ad", "to", "sale,"], TAIL = ["in", "one", "calm", "place."];
  const word = (w, i, base) => (
    <motion.span key={w + i} className="inline-block" initial={reduce ? false : { opacity: 0, y: 30, filter: "blur(12px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      transition={{ duration: 0.9, ease, delay: base + i * 0.07 }}>{w}&nbsp;</motion.span>
  );

  return (
    <section id="hero" ref={ref} aria-label="AIMVA" onPointerMove={onMove} className="relative isolate overflow-hidden text-[#0f282f]">
      {/* Sky: deep morning blue at the top, cyan light, warm haze near the horizon */}
      <motion.div aria-hidden style={{ y: sky }} className="absolute inset-0 -top-[20%] -z-10">
        <div className="absolute inset-0 bg-[linear-gradient(180deg,#2E86C1_0%,#5DADE2_22%,#A9DCF2_48%,#E6F6FB_70%,#FFF6E8_100%)]" />
        <div className="absolute left-1/2 top-[58%] h-[50%] w-[90%] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,rgba(255,214,150,0.55),transparent)] blur-2xl" />
      </motion.div>
      {[0, 1, 2].map((l) => (
        <motion.div key={l} aria-hidden style={{ y: full ? cloudLayer[l] : 0 }} className={l === 2 ? "pointer-events-none absolute inset-0 z-20 will-change-transform" : "pointer-events-none absolute inset-0 -z-[5] will-change-transform"}>
          {CLOUDS.filter((c) => c.l === l && (full || l === 0)).map((c, i) => (
            <motion.span key={i} className="absolute rounded-[50%] bg-white will-change-transform" style={{ left: `${c.x}%`, top: `${c.y}%`, width: `${c.w}%`, height: `${c.h}%`, opacity: c.o, filter: `blur(${full ? 28 + l * 6 : 22}px)` }}
              animate={reduce ? undefined : { x: [0, l % 2 ? -40 : 40, 0] }} transition={{ duration: 40 + i * 9, repeat: Infinity, ease: "easeInOut" }} />
          ))}
        </motion.div>
      ))}

      {three && (
        <motion.div aria-hidden className="pointer-events-none absolute inset-0 z-[5]" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 1.2, delay: 0.2 }}>
          <Suspense fallback={null}><SkyObjects3D scroll={scrollRef} pointer={pointerRef} active={seen} /></Suspense>
        </motion.div>
      )}
      {things.map((t, i) => <Thing key={i} t={t} i={i} p={p} px={px} py={py} full={full} reduce={reduce} />)}

      <div className="relative z-10 mx-auto flex min-h-[calc(100svh-3.5rem)] max-w-4xl flex-col items-center justify-center px-4 pb-16 pt-10 text-center sm:min-h-[calc(100svh-4rem)]">
        <motion.div style={full ? words : undefined} className="flex flex-col items-center">
          <motion.span initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, ease, delay: 0.5 }}
            className="mb-5 inline-flex items-center gap-2 rounded-full bg-white/55 px-3.5 py-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-[#0f282f]/80 ring-1 ring-white/70 backdrop-blur-md">
            <span className="size-1.5 rounded-full bg-[#F2A33A]" /> Free while in early access
          </motion.span>
          <h1 className="serif-moment text-[44px] leading-[0.98] tracking-[-0.02em] text-[#0f282f] [text-shadow:0_2px_30px_rgba(255,255,255,0.6)] sm:text-7xl xl:text-[96px]" aria-label="From ad to sale, in one calm place.">
            <span aria-hidden className="block">{HEAD.map((w, i) => word(w, i, 0.7))}</span>
            <em aria-hidden className="block text-[#0b6b67]">{TAIL.map((w, i) => word(w, i, 1.0))}</em>
          </h1>
          <motion.p initial={reduce ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease, delay: 1.45 }}
            className="mt-6 max-w-xl text-[15px] leading-relaxed text-[#21414a] sm:text-lg">
            Tell AIMVA about your business in one sentence, in any language. It writes your page and ads, answers every lead in seconds and calls them back. You just close.
          </motion.p>
          <motion.div initial={reduce ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease, delay: 1.65 }}
            className="mt-8 flex flex-col items-center gap-3 sm:flex-row">
            <Link to={user ? "/app" : signupHref("home")} className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[#F2A33A] px-7 text-[15px] font-semibold text-[#2b1700] shadow-[0_14px_30px_-12px_rgba(201,122,18,0.8)] transition hover:bg-[#ffb751]">
              {user ? "Open app" : "Start free"} <ArrowRight className="size-4" />
            </Link>
            <a href="#story" className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-white/45 px-6 text-[15px] font-medium text-[#0f282f] ring-1 ring-white/80 backdrop-blur-md transition hover:bg-white/70">
              See it work <ArrowDown className="size-4" />
            </a>
          </motion.div>
        </motion.div>
      </div>

      {/* The mascot floats in the sky with everything else, bottom centre, and waves once */}
      <motion.div className="absolute bottom-[6%] left-1/2 z-[15] hidden -translate-x-1/2 md:block" style={full ? { y: mascotY } : undefined}
        initial={reduce ? false : { opacity: 0, y: 80 }} animate={{ opacity: 1, y: 0 }} transition={{ type: "spring", stiffness: 70, damping: 14, delay: 1.9 }}>
        <Mascot mood={waved ? "idle" : "hello"} watch={waved} size={110} label="AIMVA's helper" />
      </motion.div>
      <span aria-hidden className="absolute bottom-6 right-8 z-20 hidden items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.2em] text-[#0f282f]/60 lg:flex">
        <span className="h-8 w-px bg-[#0f282f]/30" /> Scroll <Sparkles className="size-3" />
      </span>
    </section>
  );
}

/** Languages a lead can write in and get the hello back in (the list the reply engine knows). Borrowed from the
 *  template: a slow strip of small pills under the hero (theirs were flight routes). */
const LANGS = ["Hindi", "Telugu", "Tamil", "Kannada", "Malayalam", "Marathi", "Bengali", "Gujarati", "Punjabi", "Odia", "Urdu", "Hinglish", "English"];
export function LanguageStrip() {
  const reduce = useReducedMotion();
  const row = [...LANGS, ...LANGS];
  return (
    <div className="relative overflow-hidden border-y border-line bg-surface py-4" aria-label={`Replies in ${LANGS.join(", ")}`}>
      <div className="pointer-events-none absolute inset-y-0 left-0 z-10 w-16 bg-gradient-to-r from-surface to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-10 w-16 bg-gradient-to-l from-surface to-transparent" />
      <motion.ul aria-hidden className="flex w-max gap-2.5" animate={reduce ? undefined : { x: ["0%", "-50%"] }} transition={{ duration: 38, repeat: Infinity, ease: "linear" }}>
        {row.map((l, i) => (
          <li key={i} className="whitespace-nowrap rounded-full border border-line-strong px-3 py-1 text-xs font-semibold uppercase tracking-[0.12em] text-muted">
            Lead writes in {l} <span className="text-faint">→</span> reply in {l}
          </li>
        ))}
      </motion.ul>
    </div>
  );
}

/** The last screen: back up in the sky (the template ends on clouds too), the mascot, one button. */
export function SkyFinale({ user }) {
  const ref = useRef(null);
  const reduce = useReducedMotion();
  const full = useFullPower() && !reduce;
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const drift = [useTransform(scrollYProgress, [0, 1], [80, -80]), useTransform(scrollYProgress, [0, 1], [160, -160])];
  return (
    <section id="finale" ref={ref} aria-labelledby="finale-h" className="relative isolate overflow-hidden text-[#0f282f]">
      <div aria-hidden className="absolute inset-0 -z-10 bg-[linear-gradient(180deg,#FFF6E8_0%,#CDEBF7_45%,#5DADE2_100%)]" />
      {[0, 1].map((l) => (
        <motion.div key={l} aria-hidden style={{ y: full ? drift[l] : 0 }} className="pointer-events-none absolute inset-0 -z-[5]">
          {CLOUDS.filter((c) => c.l === l || (!full && c.l === 0)).map((c, i) => (
            <span key={i} className="absolute rounded-[50%] bg-white" style={{ left: `${c.x}%`, top: `${100 - c.y - c.h}%`, width: `${c.w}%`, height: `${c.h}%`, opacity: c.o * 0.9, filter: `blur(${full ? 30 : 22}px)` }} />
          ))}
        </motion.div>
      ))}
      <div className="relative mx-auto flex max-w-3xl flex-col items-center px-4 py-20 text-center sm:px-6 sm:py-28">
        <Mascot mood="happy" size={120} watch label="AIMVA's helper" />
        <h2 id="finale-h" className="serif-moment mt-4 text-[36px] leading-tight sm:text-6xl">Your next lead could be <em className="text-[#0b6b67]">in today.</em></h2>
        <p className="mx-auto mt-4 max-w-lg text-base text-[#21414a] sm:text-lg">Create a free account, tell him about your business in one sentence, and your first page is written for you.</p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link to={user ? "/app" : signupHref("home")} className="inline-flex h-12 items-center justify-center gap-2 rounded-full bg-[#F2A33A] px-7 text-[15px] font-semibold text-[#2b1700] shadow-[0_14px_30px_-12px_rgba(201,122,18,0.8)] transition hover:bg-[#ffb751]">
            {user ? "Open app" : "Start free"} <ArrowRight className="size-4" />
          </Link>
          <Link to="/tour" className="inline-flex h-12 items-center justify-center rounded-full bg-white/50 px-6 text-[15px] font-medium ring-1 ring-white/80 backdrop-blur-md hover:bg-white/75">Take the product tour</Link>
        </div>
        <p className="mt-5 text-sm text-[#21414a]/80">Free while in early access. No card needed.</p>
      </div>
    </section>
  );
}

/** Smooth, weighted scrolling on laptops and tablets only (phones keep their own native scroll). */
export function useSmoothScroll() {
  const full = useFullPower();
  const reduce = useReducedMotion();
  useEffect(() => {
    if (!full || reduce) return undefined;
    let lenis, raf, live = true;
    import("lenis").then(({ default: Lenis }) => {
      if (!live) return;
      lenis = new Lenis({ lerp: 0.1, smoothWheel: true, anchors: true });
      const loop = (t) => { lenis.raf(t); raf = requestAnimationFrame(loop); };
      raf = requestAnimationFrame(loop);
    });
    return () => { live = false; cancelAnimationFrame(raf); lenis?.destroy(); };
  }, [full, reduce]);
}
