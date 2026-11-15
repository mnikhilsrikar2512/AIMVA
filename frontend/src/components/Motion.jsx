import { motion } from "framer-motion";
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

/*
 * Inside the app nothing moves unless work is happening (design.md 9.1), so the numbers, trend lines and meters
 * below are still. Reveal/stagger/rise above are for the marketing pages; the app frame sets reducedMotion.
 */

/** A number, formatted, in tabular figures. (Named CountUp for its callers; it no longer counts.) */
export function CountUp({ value, format = (v) => Math.round(v).toLocaleString("en-IN"), className }) {
  return <span className={cx("tabular-nums", className)}>{value === null || value === undefined || Number.isNaN(value) ? "—" : format(value)}</span>;
}

/** Trend line, flat colour, a dot on the latest point. */
export function Sparkline({ points, color = "var(--color-brand)", height = 32, className }) {
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
        <path d={d} fill="none" stroke={color} strokeWidth="1.6" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <span className="absolute size-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full" style={{ left: `${last[0]}%`, top: last[1], background: color }} aria-hidden="true" />
    </div>
  );
}

/** Progress toward (or past) a target. For "lower is better" values (cost per lead) the track runs to 1.5× the
 *  target with a tick at the target, so you can see how far over or under it a number is. */
export function Meter({ value, max, good = "bg-brand", bad = "bg-danger", warn = "bg-warm", invert = false, className }) {
  if (!max) return null;
  const ratio = value / max;
  if (invert) {
    const colour = ratio <= 1 ? good : ratio <= 1.5 ? warn : bad;
    return (
      <div className={cx("relative h-1.5 rounded-full bg-ink/[0.07]", className)} title={`${Math.round(ratio * 100)}% of target`}>
        <div className={cx("h-full rounded-full", colour)} style={{ width: `${Math.min(100, (ratio / 1.5) * 100)}%` }} />
        <span className="absolute -top-0.5 h-2.5 w-0.5 rounded-full bg-strong/50" style={{ left: "66.6%" }} aria-hidden="true" />
      </div>
    );
  }
  return (
    <div className={cx("h-1.5 overflow-hidden rounded-full bg-ink/[0.07]", className)}>
      <div className={cx("h-full rounded-full", ratio >= 1 ? good : bad)} style={{ width: `${Math.min(100, ratio * 100)}%` }} />
    </div>
  );
}
