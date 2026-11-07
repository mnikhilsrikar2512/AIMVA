import { useEffect, useId, useRef, useState } from "react";
import { animate, motion, useInView, useReducedMotion } from "framer-motion";
import cx from "clsx";

/*
 * AIMVA motion language: motion always explains a change in the data or the flow of work.
 * Numbers count to their new value, trends draw left to right, progress fills toward a target,
 * new items rise into place and resolved items leave. Nothing loops for decoration, and every
 * animation collapses to an instant change for people who prefer reduced motion.
 */
export const ease = [0.22, 1, 0.36, 1];
export const spring = { type: "spring", stiffness: 260, damping: 30 };

export function Reveal({ children, delay = 0, y = 14, className, as = "div" }) {
  const C = motion[as];
  return (
    <C className={className} initial={{ opacity: 0, y }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-40px" }}
      transition={{ duration: 0.5, ease, delay }}>
      {children}
    </C>
  );
}

export const stagger = { hidden: {}, show: { transition: { staggerChildren: 0.06, delayChildren: 0.04 } } };
export const rise = { hidden: { opacity: 0, y: 12 }, show: { opacity: 1, y: 0, transition: { duration: 0.45, ease } } };

/** A number that counts from its previous value to the new one, so changes are noticed. */
export function CountUp({ value, format = (v) => Math.round(v).toLocaleString("en-IN"), className, duration = 0.9 }) {
  const reduce = useReducedMotion();
  const ref = useRef(null);
  const inView = useInView(ref, { once: true });
  const from = useRef(0);
  const [shown, setShown] = useState(reduce ? value : 0);
  useEffect(() => {
    if (value === null || value === undefined || Number.isNaN(value)) return;
    if (reduce || !inView) { if (reduce) setShown(value); return; }
    const controls = animate(from.current, value, { duration, ease, onUpdate: setShown });
    from.current = value;
    return () => controls.stop();
  }, [value, inView, reduce, duration]);
  return <span ref={ref} className={cx("tabular-nums", className)}>{value === null || value === undefined ? "—" : format(shown)}</span>;
}

/** Trend line revealed left to right (a clip wipe, so the stroke stays crisp at any width); a dot marks the latest point. */
export function Sparkline({ points, color = "var(--color-brand)", height = 32, className, fill = true }) {
  const id = useId().replace(/:/g, "");
  const reduce = useReducedMotion();
  const vals = points.map((p) => (p ?? 0));
  if (vals.length < 2) return <div style={{ height }} className={className} />;
  const max = Math.max(1, ...vals);
  const w = 100;
  const xy = vals.map((v, i) => [(i / (vals.length - 1)) * w, height - 3 - (v / max) * (height - 6)]);
  const d = xy.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const last = xy[xy.length - 1];
  return (
    <div className={cx("relative w-full", className)} style={{ height }}>
      <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" className="absolute inset-0 h-full w-full overflow-visible" aria-hidden="true">
        <defs>
          <linearGradient id={`g${id}`} x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.2" /><stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
          <clipPath id={`c${id}`}>
            <motion.rect x="0" y="-4" height={height + 8} initial={{ width: reduce ? w : 0 }} animate={{ width: w }} transition={{ duration: 1, ease }} />
          </clipPath>
        </defs>
        <g clipPath={`url(#c${id})`}>
          {fill && <path d={`${d} L${w},${height} L0,${height} Z`} fill={`url(#g${id})`} />}
          <path d={d} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
        </g>
      </svg>
      <motion.span className="absolute size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full" style={{ left: `${last[0]}%`, top: last[1], background: color }}
        initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: reduce ? 0 : 0.9, ...spring }} aria-hidden="true" />
    </div>
  );
}

/** Progress toward (or past) a target. For "lower is better" values (cost per lead) the track runs to 1.5× the
 *  target with a tick at the target, so you can see how far over or under it a number is. */
export function Meter({ value, max, good = "bg-emerald-500", bad = "bg-rose-400", warn = "bg-amber-400", invert = false, className }) {
  if (!max) return null;
  const ratio = value / max;
  if (invert) {
    const colour = ratio <= 1 ? good : ratio <= 1.5 ? warn : bad;
    return (
      <div className={cx("relative h-1.5 rounded-full bg-ink/[0.07]", className)} title={`${Math.round(ratio * 100)}% of target`}>
        <motion.div className={cx("h-full rounded-full", colour)} initial={{ width: 0 }} animate={{ width: `${Math.min(100, (ratio / 1.5) * 100)}%` }} transition={spring} />
        <span className="absolute -top-0.5 h-2.5 w-0.5 rounded-full bg-strong/50" style={{ left: "66.6%" }} aria-hidden="true" />
      </div>
    );
  }
  return (
    <div className={cx("h-1.5 overflow-hidden rounded-full bg-ink/[0.07]", className)}>
      <motion.div className={cx("h-full rounded-full", ratio >= 1 ? good : bad)} initial={{ width: 0 }} animate={{ width: `${Math.min(100, ratio * 100)}%` }} transition={spring} />
    </div>
  );
}

/** Soft live indicator: a steady dot with a single expanding ring (no endless bouncing). */
export function LiveDot({ tone = "bg-emerald-500", className }) {
  return (
    <span className={cx("relative inline-flex size-2", className)}>
      <span className={cx("absolute inset-0 rounded-full opacity-60 motion-safe:animate-ping", tone)} style={{ animationIterationCount: 3 }} />
      <span className={cx("relative inline-flex size-2 rounded-full", tone)} />
    </span>
  );
}
