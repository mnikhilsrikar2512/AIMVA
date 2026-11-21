// A different moment for each goal (plan "Motion and celebrations", owner 2026-11-21). Each scene shows what the goal
// means, plays once in about two seconds, never loops, and sits still for people who ask their phone for less motion
// (MotionConfig reducedMotion="user" around it). Tapping anywhere skips, as before.
import { MotionConfig, animate, motion, useMotionValue, useTransform } from "framer-motion";
import { useEffect } from "react";

const ease = [0.22, 1, 0.36, 1];

/** First page live: the page lifts into a browser frame and its address writes itself in. */
function PageLive({ domain = "your-business.aimva.in" }) {
  const chars = useMotionValue(0);
  const shown = useTransform(chars, (n) => domain.slice(0, Math.round(n)));
  useEffect(() => { const c = animate(chars, domain.length, { duration: 0.9, delay: 0.6, ease: "linear" }); return c.stop; }, [chars, domain]);
  return (
    <motion.div initial={{ y: 24, opacity: 0, rotateX: 12 }} animate={{ y: 0, opacity: 1, rotateX: 0 }} transition={{ duration: 0.7, ease }}
      className="mx-auto w-72 overflow-hidden rounded-xl bg-surface shadow-[var(--shadow-lift)] ring-1 ring-line" style={{ perspective: 600 }}>
      <div className="flex items-center gap-1.5 border-b border-line px-3 py-2">
        {[0, 1, 2].map((i) => <span key={i} className="size-2 rounded-full bg-line-strong" />)}
        <span className="ml-2 flex-1 truncate rounded bg-surface-2 px-2 py-0.5 text-left font-mono text-[12px] text-strong"><motion.span>{shown}</motion.span><motion.span animate={{ opacity: [1, 0] }} transition={{ repeat: 3, duration: 0.5 }}>|</motion.span></span>
      </div>
      <div className="space-y-2 p-4">
        {[80, 60, 70].map((w, i) => (
          <motion.div key={i} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ delay: 0.3 + i * 0.12, duration: 0.5, ease }}
            className="h-2.5 origin-left rounded-full bg-surface-2" style={{ width: `${w}%` }} />
        ))}
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.5 }} className="mt-3 h-7 w-24 rounded-md bg-accent" />
      </div>
    </motion.div>
  );
}

/** First lead: their message arrives as a chat bubble, and the phone gives one buzz. */
function FirstLead({ name, message }) {
  return (
    <motion.div animate={{ x: [0, -4, 4, -3, 3, 0] }} transition={{ delay: 0.9, duration: 0.35 }}
      className="mx-auto w-64 rounded-[28px] bg-strong p-3 shadow-[var(--shadow-lift)]">
      <div className="min-h-[200px] rounded-[20px] bg-[#ECE5DD] px-3 pb-6 pt-10 text-left">
        <motion.div initial={{ y: 16, opacity: 0, scale: 0.9 }} animate={{ y: 0, opacity: 1, scale: 1 }} transition={{ delay: 0.5, duration: 0.45, ease }}
          className="max-w-[85%] rounded-lg rounded-tl-none bg-white px-3 py-2 text-sm text-[#111] shadow-sm">
          {name && <p className="text-xs font-semibold text-[#075E54]">{name}</p>}
          <p className="line-clamp-3">{message || "Hi, can I get a call back?"}</p>
        </motion.div>
      </div>
    </motion.div>
  );
}

/** First call: the voice wakes and says one line. */
function FirstCall() {
  const bars = [0.4, 0.8, 0.55, 1, 0.7, 0.45, 0.9, 0.6, 0.35];
  return (
    <div className="mx-auto flex h-24 items-center justify-center gap-1.5">
      {bars.map((h, i) => (
        <motion.span key={i} className="w-2 rounded-full bg-brand" initial={{ height: 6 }}
          animate={{ height: [6, h * 80, 10, h * 60, 6] }} transition={{ delay: 0.3 + i * 0.05, duration: 1.6, ease: "easeInOut" }} />
      ))}
    </div>
  );
}

/** First sale: a thread draws from the ad to the lead to the sale, then the amount rolls up. */
function FirstSale({ value }) {
  const n = useMotionValue(0);
  const text = useTransform(n, (v) => `₹${Math.round(v).toLocaleString("en-IN")}`);
  useEffect(() => { if (value) { const c = animate(n, value, { duration: 1, delay: 1.2, ease }); return c.stop; } return undefined; }, [n, value]);
  const steps = ["Ad", "Lead", "Sale"];
  return (
    <div className="mx-auto w-72">
      <svg viewBox="0 0 280 40" className="w-full" aria-hidden>
        <motion.path d="M20 20 H260" stroke="var(--color-brand)" strokeWidth="2" fill="none"
          initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease }} />
        {steps.map((_, i) => (
          <motion.circle key={i} cx={20 + i * 120} cy="20" r="7" fill="var(--color-brand)"
            initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ delay: i * 0.45, duration: 0.3 }} />
        ))}
      </svg>
      <div className="flex justify-between text-xs text-muted">{steps.map((s) => <span key={s} className="w-10 text-center">{s}</span>)}</div>
      {value > 0 && <motion.p className="mt-3 text-2xl font-semibold tabular-nums text-strong">{text}</motion.p>}
    </div>
  );
}

/** 10 / 50 / 100 leads: one star per person who asked, filling in. */
function LeadStars({ count }) {
  const n = Math.min(count, 100);
  const cols = n <= 10 ? 5 : 10;
  return (
    <div className="mx-auto grid w-fit gap-2" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }} aria-hidden>
      {Array.from({ length: n }, (_, i) => (
        <motion.span key={i} className="size-2.5 rounded-full bg-brand"
          initial={{ opacity: 0, scale: 0 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: (i / n) * 1.4, duration: 0.25 }} />
      ))}
    </div>
  );
}

export function MomentScene({ id, facts = {} }) {
  let scene = null;
  if (id === "first_page_live") scene = <PageLive domain={facts.domain} />;
  else if (id === "first_lead") scene = <FirstLead name={facts.firstLeadName} message={facts.firstLeadMessage} />;
  else if (id === "first_call") scene = <FirstCall />;
  else if (id === "first_won") scene = <FirstSale value={facts.wonValue} />;
  else if (id?.startsWith("leads_")) scene = <LeadStars count={Number(id.slice(6))} />;
  if (!scene) return null;
  return <MotionConfig reducedMotion="user"><div className="mb-8">{scene}</div></MotionConfig>;
}
