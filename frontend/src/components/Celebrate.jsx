// Celebrations: real milestones (first page live, first lead, first sale, 10/50/100 leads…), each once per
// workspace, at most one every 4 hours, never over open work, with rotating words. See design.md section 6.
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "../lib/auth";
import { get } from "../lib/api";
import { parseServerDate } from "../lib/hooks";
import { useLeadEvents } from "../lib/live";

/* ---- confetti: a tiny canvas burst, no dependency ------------------------------------------------- */
const COLORS = ["#0b6b67", "#f4a21c", "#13827a", "#a35700", "#7cc6b8", "#ffd27a"];
const reducedMotion = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

export function confetti({ big = false } = {}) {
  if (reducedMotion()) return;
  const c = document.createElement("canvas");
  c.setAttribute("aria-hidden", "true");
  c.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;pointer-events:none;z-index:80";
  document.body.appendChild(c);
  const dpr = window.devicePixelRatio || 1;
  const W = (c.width = innerWidth * dpr), H = (c.height = innerHeight * dpr);
  const ctx = c.getContext("2d");
  const n = big ? 160 : 60;
  const parts = Array.from({ length: n }, (_, i) => {
    // Big: from both lower corners towards the middle. Medium: one burst from the top right, near the bell.
    const left = big ? i % 2 === 0 : false;
    const x = big ? (left ? 0 : W) : W - 60 * dpr;
    const y = big ? H * 0.85 : 40 * dpr;
    const ang = big ? (left ? -Math.PI / 3 : (-2 * Math.PI) / 3) + (Math.random() - 0.5) * 0.7 : Math.PI * (0.55 + Math.random() * 0.5);
    const sp = (big ? 14 + Math.random() * 12 : 6 + Math.random() * 7) * dpr;
    return { x, y, vx: Math.cos(ang) * sp, vy: Math.sin(ang) * sp, r: (4 + Math.random() * 5) * dpr, rot: Math.random() * 6,
      vr: (Math.random() - 0.5) * 0.3, color: COLORS[i % COLORS.length], shape: i % 3 };
  });
  const until = performance.now() + (big ? 1900 : 1200);
  const tick = (t) => {
    ctx.clearRect(0, 0, W, H);
    const fade = Math.max(0, Math.min(1, (until - t) / 500));
    for (const p of parts) {
      p.vy += 0.32 * dpr; p.vx *= 0.985; p.vy *= 0.985; p.x += p.vx; p.y += p.vy; p.rot += p.vr;
      ctx.save(); ctx.globalAlpha = fade; ctx.translate(p.x, p.y); ctx.rotate(p.rot); ctx.fillStyle = p.color;
      if (p.shape === 0) { ctx.beginPath(); ctx.arc(0, 0, p.r * 0.6, 0, Math.PI * 2); ctx.fill(); }
      else ctx.fillRect(-p.r / 2, -p.r / 4, p.r, p.r / (p.shape === 1 ? 2 : 1.2));
      ctx.restore();
    }
    if (t < until) requestAnimationFrame(tick); else c.remove();
  };
  requestAnimationFrame(tick);
}

/* ---- milestones ----------------------------------------------------------------------------------- */
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const LEAD_STEPS = [10, 50, 100, 250, 500, 1000];

/** Each milestone: id, size (small | medium | big), reached(facts), words(facts) → { title, text, action? }. */
export const MILESTONES = [
  { id: "setup_done", size: "small", reached: (f) => f.setupDone,
    words: () => ({ title: pick(["Setup done.", "You're all set up."]), text: "Everything is ready. Leads from your page, calls and WhatsApp land in one place." }) },
  { id: "first_page_live", size: "medium", reached: (f) => f.pagesLive > 0,
    words: () => ({ title: pick(["Your page is live.", "You're on the internet.", "Page published."]), text: pick(["Share the link and the first lead can come in today.", "Anyone with the link can now ask you for a call."]) }) },
  { id: "first_call", size: "medium", reached: (f) => f.calls > 0,
    words: () => ({ title: pick(["Your assistant took its first call.", "First call done."]), text: "It will greet every new lead the same way, day or night." }) },
  { id: "first_lead", size: "big", reached: (f) => f.leads > 0,
    words: (f) => ({ title: pick(["Your first lead.", "Someone wants to hear from you.", "The first one is in."]),
      text: f.daysSinceSignup != null ? `${f.firstLeadName ? `${f.firstLeadName} asked to hear from you` : "It arrived"}, ${f.daysSinceSignup <= 0 ? "on the day you signed up" : `${f.daysSinceSignup} day${f.daysSinceSignup === 1 ? "" : "s"} after you signed up`}.` : "Call them while they're thinking about you.",
      action: f.firstLeadId ? { label: "Open the lead", to: `/app/leads?lead=${f.firstLeadId}` } : { label: "See leads", to: "/app/leads" } }) },
  { id: "first_hot_lead", size: "medium", reached: (f) => f.hot > 0,
    words: () => ({ title: pick(["A hot lead.", "This one looks serious."]), text: "Hot leads reply fastest in the first five minutes." }) },
  { id: "first_won", size: "big", reached: (f) => f.won > 0,
    words: () => ({ title: pick(["Your first sale.", "You closed one.", "First deal won."]), text: pick(["From an ad to a sale, all in AIMVA. That's the whole point.", "That one started as a click. Well done."]),
      action: { label: "See what worked", to: "/app/command" } }) },
  { id: "won_5", size: "medium", reached: (f) => f.won >= 5,
    words: () => ({ title: "Five sales.", text: "You have a pattern now. Results shows which campaign brought them." }) },
  ...LEAD_STEPS.map((n) => ({ id: `leads_${n}`, size: n === 10 ? "medium" : "big", reached: (f) => f.leads >= n,
    words: () => ({ title: pick([`${n} leads.`, `That's ${n} people who asked.`, `${n} and counting.`]), text: pick(["Every one of them is in Leads, scored and ready to call.", "Keep the pages and campaigns that brought them running."]) }) })),
];

/** The next lead count to aim for, for a faint progress line on Home. */
export function nextLeadMilestone(leads) {
  const n = LEAD_STEPS.find((x) => x > leads);
  return n ? { target: n, left: n - leads } : null;
}

const COOLDOWN = 4 * 60 * 60 * 1000;
const RANK = { small: 0, medium: 1, big: 2 };
const storeKey = (user) => `aimva_milestones_${user?.id ?? "x"}_${user?.workspace?.id ?? "own"}`;
const load = (k) => { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage blocked */ } };

/** Is the person in the middle of something? Then the moment waits. */
const busyNow = () => !!document.querySelector("[role=dialog], [data-aimva-editor-open]") || document.documentElement.classList.contains("focus-mode")
  || /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "") || document.activeElement?.isContentEditable;

async function readFacts(onboarding, user) {
  const leads = await get("/api/leads").catch(() => null);
  if (!leads) return null;
  const s = Object.fromEntries((onboarding?.steps || []).map((x) => [x.key, x.done]));
  const first = [...leads].sort((a, b) => (a.created_at < b.created_at ? -1 : 1))[0];
  const signup = user?.created_at ? parseServerDate(user.created_at) : null;
  const firstAt = first ? parseServerDate(first.created_at) : null;
  return {
    leads: leads.length, hot: leads.filter((l) => l.score >= 70).length, won: leads.filter((l) => l.stage === "won").length,
    pagesLive: s.publish ? 1 : 0, calls: s.voice ? 1 : 0, setupDone: !!onboarding?.all_done,
    firstLeadId: first?.id, firstLeadName: first?.name?.split(" ")[0],
    daysSinceSignup: signup && firstAt ? Math.floor((firstAt - signup) / 86400000) : null,
  };
}

/** Mounted once in the app frame. Watches for milestones and shows at most one at a time. */
export function Celebrations({ onboarding }) {
  const { user } = useAuth();
  const [moment, setMoment] = useState(null);
  const pending = useRef(null);
  const key = storeKey(user);

  const show = useCallback((m, facts) => {
    const st = load(key) || { seen: [], last: 0 };
    st.seen = [...new Set([...st.seen, m.id])]; st.last = Date.now(); save(key, st);
    const w = m.words(facts);
    if (m.size === "big") { setMoment({ ...w, id: m.id }); confetti({ big: true }); return; }
    if (m.size === "medium") confetti();
    toast(w.title, { description: w.text, duration: m.size === "medium" ? 6000 : 4000 });
  }, [key]);

  const check = useCallback(async () => {
    // Wait until we know which workspace this is (right after sign-in `user` has no `workspace` yet): checking
    // under the wrong key would compare one workspace's leads with another's baseline and celebrate old leads.
    if (!user || !("workspace" in user) || !onboarding) return;
    const facts = await readFacts(onboarding, user);
    if (!facts) return;
    let st = load(key);
    const reached = MILESTONES.filter((m) => m.reached(facts));
    // First run on this browser: whatever was already reached is marked seen quietly, so existing owners aren't flooded.
    if (!st) { save(key, { seen: reached.map((m) => m.id), last: 0 }); return; }
    const fresh = reached.filter((m) => !st.seen.includes(m.id));
    if (!fresh.length) return;
    // The biggest new moment wins; smaller ones reached at the same time are marked seen without a show.
    fresh.sort((a, b) => RANK[b.size] - RANK[a.size]);
    const [top, ...rest] = fresh;
    if (rest.length) { st = { ...st, seen: [...st.seen, ...rest.map((m) => m.id)] }; save(key, st); }
    const cooling = Date.now() - (st.last || 0) < COOLDOWN && top.size !== "big";
    if (cooling) return;  // stays unseen; it gets its turn after the cooldown
    if (busyNow()) { pending.current = { top, facts }; return; }
    show(top, facts);
  }, [user, onboarding, key, show]);

  useEffect(() => { check(); }, [check]);
  useLeadEvents(() => { setTimeout(check, 800); });
  // A moment that waited for the person to finish what they were doing.
  useEffect(() => {
    const t = setInterval(() => { if (pending.current && !busyNow()) { const { top, facts } = pending.current; pending.current = null; show(top, facts); } }, 3000);
    return () => clearInterval(t);
  }, [show]);

  useEffect(() => {
    if (!moment) return;
    const close = () => setMoment(null);
    const t = setTimeout(() => window.addEventListener("keydown", close, { once: true }), 300);
    return () => { clearTimeout(t); window.removeEventListener("keydown", close); };
  }, [moment]);

  if (!moment) return null;
  return createPortal(
    <div className="fixed inset-0 z-[70] grid place-items-center bg-bg/70 p-6 backdrop-blur-sm animate-[fade_250ms_ease]" onClick={() => setMoment(null)} role="status" aria-live="polite">
      <div className="max-w-md text-center animate-[rise_500ms_cubic-bezier(.22,1,.36,1)]" onClick={(e) => e.stopPropagation()}>
        <p className="serif-moment text-4xl leading-tight text-strong sm:text-5xl">{moment.title}</p>
        <p className="mt-3 text-base text-muted">{moment.text}</p>
        <div className="mt-6 flex items-center justify-center gap-2">
          {moment.action && <Link to={moment.action.to} className="btn-primary" onClick={() => setMoment(null)}>{moment.action.label}</Link>}
          <button type="button" className="btn-subtle" onClick={() => setMoment(null)} autoFocus>Back to work</button>
        </div>
      </div>
    </div>,
    document.body
  );
}
