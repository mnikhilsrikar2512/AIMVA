import { createContext, useContext, useEffect, useRef } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useApi } from "../lib/hooks";
import { cx } from "./ui";

/**
 * Every module's place in one journey: you make something, it reaches people, they ask, some buy.
 * The trail says where this screen sits; the sentence says what this module's work has led to so far, from real
 * links (a picture's url in an ad, a page's slug on its leads), never from copy. See backend/app/routers/story.py.
 */
const STEPS = [
  { key: "make", label: "Make", to: "/app/images" },
  { key: "reach", label: "Reach", to: "/app/ads/meta" },
  { key: "leads", label: "Leads", to: "/app/leads" },
  { key: "sales", label: "Sales", to: "/app/command" },
];
const STEP_OF = { pictures: "make", videos: "make", pages: "make", campaigns: "reach", leads: "leads", results: "sales" };

const StoryCtx = createContext(null);
/** One fetch for the whole screen: the trail and every card's "used in" line read the same answer. */
export function StoryProvider({ children }) {
  const api = useApi("/api/story");
  const { pathname } = useLocation();
  const first = useRef(true);
  // Coming back to a screen after making or publishing something elsewhere should show the new links.
  useEffect(() => { if (first.current) { first.current = false; return; } api.reload(); }, [pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  return <StoryCtx.Provider value={api}>{children}</StoryCtx.Provider>;
}
export function useStory() {
  return useContext(StoryCtx)?.data || null;
}

const inr = (v) => {
  const n = Number(v) || 0;
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(n >= 1e8 ? 0 : 1)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(n >= 1e6 ? 0 : 1)} L`;
  return `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
};
const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const B = ({ children }) => <b className="font-semibold text-strong">{children}</b>;
const SOURCE = { website: "your pages", meta: "Meta ads", google: "Google ads", linkedin: "LinkedIn ads", whatsapp: "WhatsApp", voice: "calls", manual: "added by hand" };

function made(kind, s, noun) {
  if (!s.made) return { text: <>A {noun} is where an ad or a page starts. Make one and put it to work; this line will show the leads and sales it brings.</> };
  const idle = s.made - s.used;
  if (!s.used) return { text: <><B>{plural(s.made, noun)}</B> made, none in an ad or on a page yet, so {s.made === 1 ? "it hasn't" : "they haven't"} reached anyone.</>,
    next: { to: "/app/ads/meta", label: `Put one in an ad` } };
  return {
    text: <><B>{s.used} of {s.made}</B> {s.made === 1 ? noun : `${noun}s`} {s.used === 1 ? "is" : "are"} in your ads and pages. They brought <B>{plural(s.leads, "lead")}</B>
      {s.won ? <> and <B>{plural(s.won, "sale")}</B> worth <B>{inr(s.value)}</B></> : <>, no sales yet</>}.{idle ? <> {idle} {idle === 1 ? "hasn't" : "haven't"} been used.</> : null}</>,
    next: idle ? { to: "/app/ads/meta", label: "Put another in an ad" } : null,
  };
}

const LINES = {
  pictures: (d) => made("pictures", d.pictures, "picture"),
  videos: (d) => made("videos", d.videos, "video"),
  pages: ({ pages: p }) => {
    if (!p.made) return { text: <>A page is where people who see your ad come to ask. Make one and every enquiry lands in Leads.</> };
    if (!p.live) return { text: <><B>{plural(p.made, "page")}</B> made, none live, so nobody can reach {p.made === 1 ? "it" : "them"} yet.</> };
    const rate = p.visits ? Math.round((p.leads / p.visits) * 1000) / 10 : 0;
    return {
      text: <><B>{p.visits.toLocaleString("en-IN")} visits</B> to your {plural(p.live, "live page")} became <B>{plural(p.leads, "lead")}</B>{p.visits ? <> ({rate}%)</> : null}
        {p.won ? <>, and <B>{plural(p.won, "customer")}</B> worth <B>{inr(p.value)}</B></> : <>, no sales yet</>}.</>,
      next: p.leads ? { to: "/app/leads?source=website", label: "See who asked" } : { to: "/app/ads/meta", label: "Send people here with an ad" },
    };
  },
  campaigns: ({ campaigns: c }) => {
    if (!c.made) return { text: <>A campaign takes your pictures and pages to the people who might buy. Nothing is spent until you publish.</> };
    if (!c.spend) return { text: <><B>{plural(c.made, "campaign")}</B> drafted, nothing spent yet.</> };
    const per = c.won ? c.spend / c.won : null;
    return {
      text: <>All your ads together: <B>{inr(c.spend)}</B> spent brought <B>{plural(c.leads, "lead")}</B>
        {c.won ? <> and <B>{plural(c.won, "sale")}</B> worth <B>{inr(c.value)}</B>, so each customer cost <B>{inr(per)}</B></> : <> and no sales yet</>}.</>,
      next: c.leads ? { to: "/app/leads", label: "See these leads" } : null,
    };
  },
  leads: ({ leads: l }) => {
    if (!l.leads) return { text: <>Everyone who asks, from your pages, ads, WhatsApp or calls, lands here. Reply fast: the first business to answer usually wins.</> };
    const top = Object.entries(l.sources).sort((a, b) => b[1] - a[1]).slice(0, 3).map(([k, n]) => `${n} from ${SOURCE[k] || k}`).join(", ");
    return {
      text: <><B>{plural(l.leads, "person", "people")}</B> asked ({top}). <B>{l.won}</B> became {l.won === 1 ? "a customer" : "customers"}{l.won ? <> worth <B>{inr(l.value)}</B></> : null}.</>,
      next: { to: "/app/command", label: "What each ad earned" },
    };
  },
  results: (d) => {
    // The totals are on this screen already; the story here is which part of the journey the money came from.
    const r = d.results;
    if (!r.won) return { text: r.leads ? <>No sales yet from your <B>{plural(r.leads, "lead")}</B>. Mark a lead as won in Leads and this line shows where each sale came from.</>
      : <>This is where the journey ends: what you spent and what came back. It fills in once your first lead arrives.</> };
    const parts = r.sales_by_source.map((x) => <span key={x.source}>{SOURCE[x.source] || x.source} <B>{inr(x.value)}</B> ({x.won})</span>);
    return { text: <>Where your {plural(r.won, "sale")} came from, since you started: {parts.reduce((acc, p, i) => (i ? [...acc, i === parts.length - 1 ? " and " : ", ", p] : [p]), [])}.</> };
  },
};

/** The trail and the sentence, under a module's page header. */
export function StoryLine({ module, className }) {
  const d = useStory();
  const here = STEP_OF[module];
  const line = d && LINES[module]?.(d);
  return (
    <div className={cx("-mt-2 mb-6 sm:-mt-4", className)}>
      <ol aria-label="Where this fits" className="mb-1.5 flex flex-wrap items-center gap-x-1.5 text-xs font-medium">
        {STEPS.map((s, i) => (
          <li key={s.key} className="flex items-center gap-1.5">
            {i > 0 && <span aria-hidden className="h-px w-4 bg-line-strong" />}
            {s.key === here
              ? <span aria-current="step" className="rounded-full bg-strong px-2 py-0.5 text-white">{s.label}</span>
              : <Link to={s.to} className="text-muted hover:text-strong">{s.label}</Link>}
          </li>
        ))}
      </ol>
      {line ? (
        <p className="max-w-3xl text-sm leading-relaxed text-ink">
          {line.text}{line.next && <> <Link to={line.next.to} className="inline-flex items-center gap-0.5 whitespace-nowrap font-medium text-brand hover:underline">{line.next.label}<ArrowRight className="size-3.5" /></Link></>}
        </p>
      ) : <p className="h-5 w-80 max-w-full animate-pulse rounded-full bg-surface-2" aria-label="Loading" />}
    </div>
  );
}

/** "In the Meta ad · 4 leads · 2 sales" under a picture or video, or nothing when it isn't used. */
export function UsedIn({ assetId, className }) {
  const d = useStory();
  const uses = d?.uses?.[String(assetId)];
  if (!uses?.length) return null;
  const leads = uses.reduce((n, u) => n + u.leads, 0);
  const won = uses.reduce((n, u) => n + u.won, 0);
  const where = uses.map((u) => (u.kind === "page" ? "your page" : `the ${u.platform === "meta" ? "Meta" : u.platform === "google" ? "Google" : "LinkedIn"} ad`));
  const label = [...new Set(where)].join(" and ");
  return (
    <p className={cx("truncate text-xs font-medium text-brand", className)} title={uses.map((u) => u.name).join(", ")}>
      In {label} · {plural(leads, "lead")}{won ? ` · ${plural(won, "sale")}` : ""}
    </p>
  );
}

/** A campaign or page's own outcome line: "4 leads · 2 sales · ₹36,000". */
export function Outcome({ kind, id, className }) {
  const d = useStory();
  const o = d?.[kind === "page" ? "per_page" : "per_campaign"]?.[String(id)];
  if (!o) return null;
  return (
    <span className={cx("text-xs", o.won ? "text-brand" : "text-muted", className)}>
      {plural(o.leads, "lead")}{o.won ? ` · ${plural(o.won, "sale")} · ${inr(o.value)}` : ""}
    </span>
  );
}
