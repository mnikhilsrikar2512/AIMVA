import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  ArrowDownRight, ArrowUpRight, BadgeIndianRupee, Check, ChevronDown, Clock, Compass, Copy, ExternalLink, Facebook, Globe,
  Linkedin, Megaphone, MoreHorizontal, Package, Pause, Pencil, PhoneCall, Play, Plus, Search, Sparkles, Target, Trash2,
  TrendingUp, X,
} from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Chip, Empty, Field, Modal, PageHeader, Spinner, Tabs, cx, IconButton } from "../../components/ui";
import { AgentSwitch } from "../../components/Agents";
import { DownloadMenu } from "../../components/DownloadMenu";
import { useAuth } from "../../lib/auth";
import { del, get, patch, post, put } from "../../lib/api";
import { timeAgo, useAction, useApi } from "../../lib/hooks";
import { CountUp, Meter, Reveal, Sparkline, ease, rise, stagger } from "../../components/Motion";

/* ---- formatting & vocabulary --------------------------------------------------------------------------- */
const inr = (v, d = 0) => (v === null || v === undefined ? "—" : `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: d })}`);
const compact = (v) => {
  if (v === null || v === undefined) return "—";
  const n = Number(v);
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(n >= 1e8 ? 0 : 1)} Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(n >= 1e6 ? 0 : 1)} L`;
  return inr(n);
};
const times = (v) => (v === null || v === undefined ? "—" : `${v >= 10 ? Math.round(v) : v.toFixed(1)}×`);
const pct = (v) => (v === null || v === undefined ? "—" : `${Number(v).toFixed(1)}%`);
const PLATFORM = { meta: [Facebook, "Meta"], google: [Search, "Google"], linkedin: [Linkedin, "LinkedIn"], other: [Megaphone, "Offline / other"] };
const HEALTH = {
  great: ["green", "Cheap leads"], ok: ["blue", "On target"], attention: ["rose", "Needs attention"], learning: ["amber", "Learning"],
  no_data: ["slate", "No results yet"], paused: ["slate", "Paused"], draft: ["slate", "Draft"], untracked: ["amber", "Leads not tracked"],
};
const SORTS = [["period_spend", "Spend"], ["leads", "Leads"], ["cpl", "Cost per lead"], ["ctr", "CTR"], ["name", "Name"]];

function Delta({ value, invert }) {
  if (value === null || value === undefined) return null;
  const up = value >= 0;
  const good = invert ? !up : up;
  const I = up ? ArrowUpRight : ArrowDownRight;
  return <span className={cx("inline-flex items-center gap-0.5 text-xs font-semibold tabular-nums", good ? "text-emerald-600" : "text-rose-600")}><I className="size-3.5" />{Math.abs(value)}%</span>;
}

function Section({ id, title, sub, actions, children, className }) {
  return (
    <section id={id} className={cx("scroll-mt-6", className)}>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div><h2 className="text-lg font-bold sm:text-xl">{title}</h2>{sub && <p className="text-sm text-muted">{sub}</p>}</div>
        {actions}
      </div>
      {children}
    </section>
  );
}

/* ---- 1. pulse: spend → leads → revenue -------------------------------------------------------------- */
function FlowNode({ label, value, sub, tone }) {
  return (
    <motion.div variants={rise} className="relative z-10 min-w-0 px-1.5 py-1 text-center sm:rounded-3xl sm:bg-surface/90 sm:px-5 sm:py-4 sm:shadow-[var(--shadow-soft)] sm:backdrop-blur">
      <p className={cx("text-xs font-semibold leading-tight sm:truncate sm:uppercase sm:tracking-wider", tone)}>{label}</p>
      <p className="mt-1 truncate font-display text-lg font-bold text-strong sm:text-2xl lg:text-4xl">{value}</p>
      <div className="mt-0.5 min-h-4 truncate text-xs text-muted sm:text-xs">{sub}</div>
    </motion.div>
  );
}

function FlowLink({ label, active }) {
  const reduce = useReducedMotion();
  return (
    <motion.div variants={rise} className="relative hidden items-center justify-center sm:flex">
      <svg className="absolute inset-0 h-full w-full" preserveAspectRatio="none" viewBox="0 0 100 20" aria-hidden="true">
        <motion.line x1="0" y1="10" x2="100" y2="10" stroke="var(--color-brand)" strokeOpacity="0.45" strokeWidth="2" strokeDasharray="4 6"
          vectorEffect="non-scaling-stroke" animate={active && !reduce ? { strokeDashoffset: [0, -20] } : {}} transition={{ repeat: Infinity, duration: 1.2, ease: "linear" }} />
      </svg>
      <span className="relative whitespace-nowrap rounded-full bg-lavender px-2.5 py-1 text-xs font-semibold text-brand">{label}</span>
    </motion.div>
  );
}

function Pulse({ k, summary, brief, onBrief, briefBusy }) {
  const winRate = k.leads ? Math.round((k.won / k.leads) * 100) : null;
  return (
    <section className="relative overflow-hidden rounded-[1.75rem] p-3 sm:p-5">
      <div className="aura pointer-events-none absolute inset-0 opacity-80" aria-hidden="true" />
      <motion.div variants={stagger} initial="hidden" animate="show"
        className="relative grid grid-cols-3 gap-2 sm:grid-cols-[1fr_minmax(70px,0.5fr)_1fr_minmax(70px,0.5fr)_1fr] sm:gap-1">
        <FlowNode label="Ad spend" tone="text-violet-600" value={<CountUp value={k.spend} format={compact} />} sub={<Delta value={k.spend_change} invert />} />
        <FlowLink active={k.leads > 0} label={k.cpl ? `${inr(k.cpl)} / lead` : k.leads > 0 ? "no spend tracked" : "no leads yet"} />
        <FlowNode label="Leads" tone="text-sky-600" value={<CountUp value={k.leads} />}
          sub={<span className="inline-flex items-center gap-1.5"><Delta value={k.leads_change} />{k.hot > 0 && <span className="font-semibold text-rose-600">{k.hot} hot</span>}</span>} />
        <FlowLink active={k.won > 0} label={winRate !== null ? `${winRate}% won` : "—"} />
        <FlowNode label="Revenue won" tone="text-emerald-600" value={<CountUp value={k.revenue} format={compact} />}
          sub={k.roas ? <span className="font-semibold text-emerald-700">{times(k.roas)} return</span> : `${k.won} won`} />
      </motion.div>
      {/* On phones the connectors collapse into one line of ratios. */}
      <p className="relative mt-2 flex justify-center gap-3 text-xs font-semibold text-brand sm:hidden">
        <span>{k.cpl ? `${inr(k.cpl)} / lead` : k.leads > 0 ? "no spend tracked" : "no leads yet"}</span><span className="text-faint">·</span><span>{winRate !== null ? `${winRate}% won` : "—"}</span>
      </p>
      <Reveal delay={0.35} className="relative mt-3 flex items-start gap-2.5 rounded-2xl bg-surface/75 px-4 py-3 text-sm text-ink backdrop-blur">
        <Sparkles className="mt-0.5 size-4 shrink-0 text-brand" />
        <p className="flex-1">{brief?.text || summary}{" "}
          {!brief && <button className="whitespace-nowrap font-semibold text-brand hover:underline disabled:opacity-50" onClick={onBrief} disabled={briefBusy}>
            {briefBusy ? "Writing…" : "Weekly brief →"}</button>}
        </p>
      </Reveal>
    </section>
  );
}

/* ---- side column: week ahead, pacing, decisions ------------------------------------------------------- */
function WeekAhead({ plan, typical }) {
  const rows = [["Leads", plan.leads_next_7, (v) => (v === 0 ? "0" : v.toFixed(v < 10 ? 1 : 0))], ["Spend", plan.spend_next_7, (v) => (v >= 1e4 && v < 1e5 ? `₹${(v / 1e3).toFixed(1)}k` : compact(v))]  /* three columns: ₹11,520 would be cut off */, ["Per lead", plan.cpl_next_7, (v) => (v && plan.leads_next_7 ? inr(v) : "—")]];
  return (
    <Card className="p-5">
      <h2 className="font-semibold text-strong">Next 7 days</h2>
      <p className="text-xs text-muted">At the current pace{plan.planned_budget_7 ? ` · budgets allow ${compact(plan.planned_budget_7)}` : ""}</p>
      <div className="mt-4 grid grid-cols-3 gap-2">
        {rows.map(([label, v, fmt]) => (
          <div key={label} className="min-w-0">
            <p className="text-xs font-medium text-faint">{label}</p>
            <p className="truncate font-display text-xl font-bold text-strong"><CountUp value={v} format={fmt} /></p>
          </div>
        ))}
      </div>
      {typical && <p className="mt-2 text-xs text-faint">Typical cost per lead across campaigns: {inr(typical)}</p>}
    </Card>
  );
}

function Pacing({ products }) {
  const rows = products.filter((p) => p.monthly_budget > 0);
  return (
    <Card className="p-5">
      <h2 className="font-semibold text-strong">Budget this month</h2>
      {rows.length === 0 ? <p className="mt-2 text-sm text-muted">Set a monthly budget on a product to track pacing.</p> : (
        <ul className="mt-3 space-y-4">
          {rows.map((p) => {
            const over = p.month_projection > p.monthly_budget * 1.15;
            const proj = Math.min(100, (p.month_projection / p.monthly_budget) * 100);
            return (
              <li key={p.id}>
                <div className="flex justify-between gap-2 text-sm"><span className="truncate text-ink">{p.name}</span><span className="shrink-0 font-semibold text-strong">{compact(p.month_spend)}</span></div>
                <div className="relative mt-1.5 h-2 rounded-full bg-ink/[0.06]">
                  <motion.div className={cx("h-full rounded-full", over ? "bg-rose-400" : "bg-emerald-500")} initial={{ width: 0 }}
                    animate={{ width: `${Math.min(100, (p.month_spend / p.monthly_budget) * 100)}%` }} transition={{ type: "spring", stiffness: 160, damping: 26 }} />
                  {/* projected month-end spend */}
                  <span className={cx("absolute -top-1 h-4 w-0.5 rounded-full", over ? "bg-rose-600" : "bg-strong/40")} style={{ left: `calc(${proj}% - 1px)` }} title="Projected month end" />
                </div>
                <p className={cx("mt-1 text-xs", over ? "font-semibold text-rose-600" : "text-faint")}>
                  of {compact(p.monthly_budget)} · on pace for {compact(p.month_projection)}
                </p>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function Decisions({ items }) {
  const [all, setAll] = useState(false);
  if (!items.length) return null;
  const shown = all ? items : items.slice(0, 4);
  return (
    <Card className="p-5">
      <h2 className="mb-3 font-semibold text-strong">Recent decisions</h2>
      <ol className="relative space-y-3 border-l border-line pl-4">
        {shown.map((d) => (
          <li key={d.id} className="relative">
            <span className={cx("absolute -left-[21px] top-1.5 size-2.5 rounded-full ring-4 ring-surface", d.decision === "accepted" ? "bg-emerald-500" : d.decision === "snoozed" ? "bg-amber-400" : "bg-slate-300")} />
            <p className="text-sm leading-snug text-strong">{d.title}</p>
            <p className="text-xs text-muted"><span className="capitalize">{d.decision}</span>{d.result ? ` · ${d.result}` : ""} · {timeAgo(d.at)}</p>
          </li>
        ))}
      </ol>
      {items.length > 4 && <button className="mt-3 text-xs font-semibold text-brand hover:underline" onClick={() => setAll((a) => !a)}>{all ? "Show fewer" : `Show all ${items.length}`}</button>}
    </Card>
  );
}

/* ---- 3. products ---------------------------------------------------------------------------------------- */
function Metric({ label, value, hint, className }) {
  return (
    <div className={cx("min-w-0", className)}>
      <p className="truncate text-xs font-medium text-faint">{label}</p>
      <div className="truncate text-sm font-semibold text-strong">{value}</div>
      {hint}
    </div>
  );
}

function ProductCard({ p, selected, onSelect, onEdit }) {
  const attention = p.campaigns.filter((c) => c.health === "attention").length;
  const active = p.campaigns.filter((c) => c.status === "active").length;
  const trend = useMemo(() => {
    const days = p.campaigns[0]?.trend?.map((t) => t.day) || [];
    return days.map((d) => p.campaigns.reduce((n, c) => n + (c.trend.find((t) => t.day === d)?.leads || 0), 0));
  }, [p.campaigns]);
  return (
    <motion.div variants={rise} id={`product-${p.id}`} whileHover={{ y: -3 }} transition={{ type: "spring", stiffness: 300, damping: 24 }}
      className={cx("card relative flex scroll-mt-6 flex-col p-5 transition-shadow hover:shadow-[var(--shadow-lift)]", selected && "ring-2 ring-brand/60")}>
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-brand/15 to-peach/25 text-brand"><Package className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <p className="truncate font-bold text-strong" title={p.name}>{p.name}</p>
          <p className="truncate text-xs text-muted">{p.kind}{p.price ? ` · ${compact(p.price)}` : ""} · {active} live campaign{active === 1 ? "" : "s"}</p>
        </div>
        <button className="grid size-8 shrink-0 place-items-center rounded-full text-faint hover:bg-ink/[0.05] hover:text-strong" onClick={() => onEdit(p)} aria-label={`Edit ${p.name}`}><Pencil className="size-3.5" /></button>
      </div>
      <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
        <Metric label="Spend" value={compact(p.spend)} />
        <Metric label="Leads" value={<span className="flex flex-wrap items-center gap-x-1.5">{p.leads}<Delta value={p.leads_change} /></span>} />
        <Metric label={p.target_cpl ? `Per lead · target ${inr(p.target_cpl)}` : "Per lead"} value={inr(p.cpl)}
          hint={p.target_cpl ? <Meter value={p.cpl || 0} max={p.target_cpl} invert className="mt-1" /> : null} />
        <Metric label="Return on ads" value={p.roas ? <span className="text-emerald-700">{times(p.roas)}</span> : p.won ? `${p.won} won` : "—"} />
      </div>
      <div className="mt-3"><Sparkline points={trend} height={30} /></div>
      <div className="mt-auto flex items-center justify-between gap-2 pt-3">
        {attention > 0 ? <Chip tone="rose">{attention} need{attention === 1 ? "s" : ""} attention</Chip> : <Chip tone="green">All on track</Chip>}
        <button className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:underline" onClick={() => onSelect(p.id)}>
          {selected ? "Show all campaigns" : "View campaigns"} <ChevronDown className="size-3.5" />
        </button>
      </div>
    </motion.div>
  );
}

/* ---- 4. campaigns --------------------------------------------------------------------------------------- */
function MoreMenu({ c, products, page, onChanged }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return;
    const close = (e) => { if (!ref.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  const tracking = page?.published ? `${page.url}?aimva_c=${c.id}` : null;
  const linkTo = async (pid) => {
    try { await post("/api/products/link", { kind: "campaign", id: c.id, product_id: pid }); toast.success(pid ? "Linked" : "Unlinked"); onChanged(); } catch (e) { toast.error(e.message); }
    setOpen(false);
  };
  return (
    <div className="relative" ref={ref}>
      <button className="grid size-8 place-items-center rounded-full text-muted hover:bg-ink/[0.05] hover:text-strong" onClick={() => setOpen((o) => !o)} aria-label="More actions" aria-expanded={open}>
        <MoreHorizontal className="size-4" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: -4, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: -4, scale: 0.97 }} transition={{ duration: 0.15 }}
            className="absolute right-0 z-30 mt-1 w-64 overflow-hidden rounded-2xl bg-surface p-1.5 text-sm shadow-[var(--shadow-lift)] ring-1 ring-line">
            <button disabled={!tracking} className="flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left hover:bg-ink/[0.04] disabled:opacity-50"
              onClick={() => { navigator.clipboard?.writeText(tracking); toast.success("Tracking link copied. Use it as the ad's destination URL."); setOpen(false); }}>
              <Copy className="size-4 shrink-0 text-muted" /> {tracking ? "Copy tracking link" : "Tracking link (publish its page first)"}
            </button>
            <p className="px-3 pb-1 pt-2 text-xs font-semibold uppercase tracking-wider text-faint">Product</p>
            {products.map((p) => (
              <button key={p.id} className="flex w-full items-center gap-2 rounded-xl px-3 py-1.5 text-left hover:bg-ink/[0.04]" onClick={() => linkTo(p.id)}>
                <span className="size-4 shrink-0">{c.product_id === p.id && <Check className="size-4 text-brand" />}</span><span className="truncate">{p.name}</span>
              </button>
            ))}
            {c.product_id && <button className="flex w-full items-center gap-2 rounded-xl px-3 py-1.5 text-left text-muted hover:bg-ink/[0.04]" onClick={() => linkTo(null)}><span className="size-4" />No product</button>}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function BudgetCell({ c, onSave }) {
  const [edit, setEdit] = useState(null);
  if (edit === null) {
    return <button className="inline-flex items-center gap-1 rounded-lg px-1 py-0.5 tabular-nums hover:bg-ink/[0.05]" onClick={() => setEdit(String(c.daily_budget))} title="Edit daily budget">{inr(c.daily_budget)}<Pencil className="size-3 text-faint" /></button>;
  }
  const save = () => { const v = Number(edit); if (!Number.isNaN(v) && v >= 0 && v !== c.daily_budget) onSave(v); setEdit(null); };
  return <input className="input h-8 w-24 px-2 text-xs" type="number" min="0" value={edit} autoFocus onChange={(e) => setEdit(e.target.value)} onBlur={save}
    onKeyDown={(e) => { if (e.key === "Enter") save(); if (e.key === "Escape") setEdit(null); }} aria-label="Daily budget" />;
}

function CampaignActions({ c, products, page, onChanged, onResults }) {
  const [busy, run] = useAction();
  const toggle = () => run(async () => { await patch(`/api/campaigns/${c.id}`, { status: c.status === "active" ? "paused" : "active" }); onChanged(); },
    c.status === "active" ? "Paused" : "Marked active");
  return (
    <div className="flex items-center justify-end gap-0.5">
      {c.status !== "draft" && (
        <button className="grid size-8 place-items-center rounded-full text-muted hover:bg-ink/[0.05] hover:text-strong disabled:opacity-40" onClick={toggle} disabled={busy}
          aria-label={c.status === "active" ? "Pause" : "Resume"} title={c.status === "active" ? "Pause" : "Resume"}>
          {busy ? <Spinner className="size-3.5" /> : c.status === "active" ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
        </button>
      )}
      <Button size="sm" variant="ghost" onClick={() => onResults(c)}>Results</Button>
      <MoreMenu c={c} products={products} page={page} onChanged={onChanged} />
    </div>
  );
}

function Campaigns({ campaigns, products, pages, filter, setFilter, onChanged, onResults, onAdd }) {
  const [health, setHealth] = useState("all");
  const [sort, setSort] = useState("period_spend");
  const pageFor = (c) => pages.find((p) => p.product_id && p.product_id === c.product_id && p.published) || null;
  const saveBudget = async (c, v) => {
    try { await patch(`/api/campaigns/${c.id}`, { daily_budget: v }); toast.success("Budget updated"); onChanged(); } catch (e) { toast.error(e.message); }
  };
  const rows = campaigns
    .filter((c) => filter === "all" || (filter === "none" ? !c.product_id : c.product_id === filter))
    .filter((c) => health === "all" || (health === "attention" ? ["attention", "untracked"].includes(c.health) : health === "off" ? ["paused", "draft"].includes(c.status) : c.health === health))
    .sort((a, b) => (sort === "name" ? a.name.localeCompare(b.name) : sort === "cpl" ? (a.cpl ?? Infinity) - (b.cpl ?? Infinity) : (b[sort] ?? -1) - (a[sort] ?? -1)));
  const healthCounts = {
    attention: campaigns.filter((c) => ["attention", "untracked"].includes(c.health)).length,
    great: campaigns.filter((c) => c.health === "great").length,
    off: campaigns.filter((c) => ["paused", "draft"].includes(c.status)).length,
  };
  return (
    <Section id="campaigns" title="Campaigns" sub="Every campaign across products. Click a budget to change it."
      actions={<Button size="sm" onClick={onAdd}><Plus className="size-3.5" /> Add campaign</Button>}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <select className="input h-9 w-auto pr-8 text-sm" value={filter} onChange={(e) => setFilter(e.target.value === "all" || e.target.value === "none" ? e.target.value : Number(e.target.value))} aria-label="Product">
          <option value="all">All products</option>
          {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          <option value="none">Not linked to a product</option>
        </select>
        <div className="flex flex-wrap gap-1">
          {[["all", "All"], ["attention", `Needs attention ${healthCounts.attention}`], ["great", `Cheap leads ${healthCounts.great}`], ["off", `Paused & drafts ${healthCounts.off}`]].map(([v, l]) => (
            <button key={v} onClick={() => setHealth(v)} className={cx("rounded-full px-3 py-1.5 text-xs font-semibold transition", health === v ? "bg-strong text-white" : "bg-surface-2 text-muted hover:text-strong")}>{l}</button>
          ))}
        </div>
        <label className="ml-auto flex items-center gap-2 text-xs text-muted">Sort
          <select className="input h-9 w-auto pr-8 text-sm" value={sort} onChange={(e) => setSort(e.target.value)}>{SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        </label>
      </div>
      {rows.length === 0 ? <Card><p className="text-sm text-muted">No campaigns match these filters.</p></Card> : (
        <>
          {/* Wide screens: one table, scannable column by column */}
          <div className="card hidden overflow-visible xl:block">
            <table className="w-full table-fixed text-sm">
              <thead className="text-left text-xs font-semibold uppercase tracking-wider text-faint">
                <tr className="border-b border-line">
                  <th className="px-4 py-3">Campaign</th><th className="w-[104px] px-3 py-3 text-right">Budget / day</th>
                  <th className="w-[92px] px-3 py-3 text-right">Spend</th><th className="w-[76px] px-3 py-3 text-right">Leads</th><th className="w-[104px] px-3 py-3">Per lead</th>
                  <th className="w-[64px] px-3 py-3 text-right">CTR</th><th className="w-[84px] px-3 py-3">Leads / day</th><th className="w-[150px] px-3 py-3" />
                </tr>
              </thead>
              <motion.tbody variants={stagger} initial="hidden" animate="show">
                {rows.map((c) => {
                  const [P, plabel] = PLATFORM[c.platform] || PLATFORM.other;
                  const [tone, hlabel] = HEALTH[c.health] || HEALTH.no_data;
                  return (
                    <motion.tr key={c.id} variants={rise} className="border-b border-line align-middle last:border-0 hover:bg-ink/[0.015]">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-2 text-ink" title={plabel}><P className="size-4" /></span>
                          <div className="min-w-0"><p className="truncate font-semibold text-strong" title={c.name}>{c.name}</p>
                            <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted"><Chip tone={tone} className="shrink-0 !px-2 !py-0 text-xs">{hlabel}</Chip>
                              <span className="truncate">{c.product_name || <span className="text-amber-700">No product</span>}</span></p></div>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-right"><BudgetCell c={c} onSave={(v) => saveBudget(c, v)} /></td>
                      <td className="px-3 py-3 text-right tabular-nums">{inr(c.period_spend)}</td>
                      <td className="px-3 py-3 text-right tabular-nums"><span className="block font-semibold text-strong">{c.leads}</span><Delta value={c.leads_change} /></td>
                      <td className="px-3 py-3"><span className="tabular-nums">{inr(c.cpl)}</span>{c.target_cpl && c.cpl ? <Meter value={c.cpl} max={c.target_cpl} invert className="mt-1" /> : null}</td>
                      <td className="px-3 py-3 text-right tabular-nums">{pct(c.ctr)}</td>
                      <td className="px-3 py-3"><Sparkline points={c.trend.map((t) => t.leads)} height={24} fill={false} /></td>
                      <td className="px-2 py-3"><CampaignActions c={c} products={products} page={pageFor(c)} onChanged={onChanged} onResults={onResults} /></td>
                    </motion.tr>
                  );
                })}
              </motion.tbody>
            </table>
          </div>
          {/* Narrower screens: one card per campaign */}
          <motion.div variants={stagger} initial="hidden" animate="show" className="grid grid-cols-[minmax(0,1fr)] gap-2 sm:grid-cols-2 xl:hidden">
            {rows.map((c) => {
              const [P] = PLATFORM[c.platform] || PLATFORM.other;
              const [tone, hlabel] = HEALTH[c.health] || HEALTH.no_data;
              return (
                <motion.div key={c.id} variants={rise} className="card p-4">
                  <div className="flex items-start gap-2.5">
                    <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-2"><P className="size-4" /></span>
                    <div className="min-w-0 flex-1"><p className="font-semibold leading-snug text-strong">{c.name}</p><p className="truncate text-xs text-muted">{c.product_name || "No product"}</p></div>
                  </div>
                  <div className="mt-2"><Chip tone={tone}>{hlabel}</Chip></div>
                  <div className="mt-3 grid grid-cols-4 gap-2">
                    <Metric label="Spend" value={compact(c.period_spend)} /><Metric label="Leads" value={c.leads} />
                    <Metric label="Per lead" value={inr(c.cpl)} /><Metric label="CTR" value={pct(c.ctr)} />
                  </div>
                  <div className="mt-3 flex items-center justify-between gap-2 border-t border-line pt-2">
                    <span className="text-xs text-muted">Budget <BudgetCell c={c} onSave={(v) => saveBudget(c, v)} /></span>
                    <CampaignActions c={c} products={products} page={pageFor(c)} onChanged={onChanged} onResults={onResults} />
                  </div>
                </motion.div>
              );
            })}
          </motion.div>
        </>
      )}
    </Section>
  );
}

/* ---- 5. landing pages ---------------------------------------------------------------------------------- */
function Pages({ pages, products, onChanged }) {
  if (!pages.length) return null;
  const link = async (s, pid) => {
    try { await post("/api/products/link", { kind: "site", id: s.id, product_id: pid }); toast.success("Saved"); onChanged(); } catch (e) { toast.error(e.message); }
  };
  return (
    <Section title="Landing pages" sub="Link each page to what it sells, so its leads and tracking links line up.">
      <div className="card divide-y divide-line">
        {pages.map((s) => (
          <div key={s.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
            <Globe className="size-4 shrink-0 text-faint" />
            <span className="min-w-0 flex-1"><span className="block truncate font-semibold text-strong">{s.name}</span>
              <span className="text-xs text-muted">{s.published ? "Live" : "Draft"} · {s.visits.toLocaleString("en-IN")} visits</span></span>
            {s.published && <IconButton label="Open the live page" href={s.url} target="_blank" rel="noreferrer"><ExternalLink className="size-4" /></IconButton>}
            <select className="input h-9 w-auto max-w-[220px] pr-8 text-sm" value={s.product_id || ""} aria-label={`Product for ${s.name}`}
              onChange={(e) => link(s, e.target.value ? Number(e.target.value) : null)}>
              <option value="">Not linked</option>
              {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        ))}
      </div>
    </Section>
  );
}

/* ---- modals ------------------------------------------------------------------------------------------- */
function ProductModal({ product, open, onClose, onSaved }) {
  const blank = { name: "", kind: "product", price: "", target_cpl: "", monthly_budget: "", status: "active", notes: "" };
  const [f, setF] = useState(blank);
  const [busy, run] = useAction();
  useEffect(() => { if (open) setF(product ? { ...product } : blank); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const num = (v) => (v === "" || v === null ? 0 : Number(v));
  const save = (e) => {
    e.preventDefault();
    const body = { name: f.name, kind: f.kind, status: f.status, notes: f.notes || "", price: num(f.price), target_cpl: num(f.target_cpl), monthly_budget: num(f.monthly_budget) };
    run(async () => { await (product ? put(`/api/products/${product.id}`, body) : post("/api/products", body)); onSaved(); onClose(); }, product ? "Saved" : "Product added");
  };
  return (
    <Modal open={open} onClose={onClose} title={product ? "Edit product" : "What do you sell?"}>
      <form onSubmit={save} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_140px]">
          <Field label="Name"><input className="input" value={f.name} onChange={set("name")} required minLength={2} maxLength={160} placeholder="2BHK at Skyline Towers" autoFocus /></Field>
          <Field label="Type"><select className="input" value={f.kind} onChange={set("kind")}><option value="product">Product</option><option value="service">Service</option><option value="offer">Offer</option></select></Field>
        </div>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Sale value (₹)" hint="Typical price"><input className="input" type="number" min="0" value={f.price} onChange={set("price")} /></Field>
          <Field label="Target per lead (₹)" hint="What a lead is worth"><input className="input" type="number" min="0" value={f.target_cpl} onChange={set("target_cpl")} /></Field>
          <Field label="Monthly budget (₹)" hint="Optional"><input className="input" type="number" min="0" value={f.monthly_budget} onChange={set("monthly_budget")} /></Field>
        </div>
        {product && <Field label="Status"><select className="input" value={f.status} onChange={set("status")}><option value="active">Active</option><option value="paused">Paused</option><option value="archived">Archived</option></select></Field>}
        <div className="flex items-center justify-between">
          {product ? <Button type="button" variant="danger" onClick={() => { if (confirm(`Delete “${product.name}”? Its campaigns, pages and leads are kept.`)) run(async () => { await del(`/api/products/${product.id}`); onSaved(); onClose(); }, "Deleted"); }}><Trash2 className="size-4" /> Delete</Button> : <span />}
          <Button type="submit" busy={busy}>{product ? "Save" : "Add product"}</Button>
        </div>
      </form>
    </Modal>
  );
}

function ResultsModal({ campaign, onClose, onSaved }) {
  const [f, setF] = useState({ spend: "", impressions: "", clicks: "", mode: "add", since: "" });
  const [busy, run] = useAction();
  useEffect(() => setF({ spend: "", impressions: "", clicks: "", mode: "add", since: campaign?.started_on || "" }), [campaign]);
  const set = (k) => (e) => setF((x) => ({ ...x, [k]: e.target.value }));
  const save = (e) => {
    e.preventDefault();
    run(async () => {
      await post(`/api/campaigns/${campaign.id}/results`, { spend: Number(f.spend || 0), impressions: Number(f.impressions || 0), clicks: Number(f.clicks || 0), mode: f.mode, since: f.mode === "total" && f.since ? f.since : null });
      onSaved();
      onClose();
    }, "Results saved");
  };
  return (
    <Modal open={!!campaign} onClose={onClose} title={campaign ? `Results · ${campaign.name}` : ""}>
      {campaign && (
        <form onSubmit={save} className="space-y-4">
          <p className="text-sm text-muted">{campaign.platform === "meta" && campaign.external_id ? "Meta campaigns sync automatically; use this only to correct numbers." : "Copy today's numbers from the ad platform (or your offline spend). AIMVA works out cost per lead and trends."}</p>
          <Tabs value={f.mode} onChange={(m) => setF((x) => ({ ...x, mode: m }))} tabs={[{ value: "add", label: "Add today's numbers" }, { value: "total", label: "Set running totals" }]} />
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Spend (₹)"><input className="input" type="number" min="0" step="0.01" required value={f.spend} onChange={set("spend")} autoFocus /></Field>
            <Field label="Impressions"><input className="input" type="number" min="0" value={f.impressions} onChange={set("impressions")} /></Field>
            <Field label="Clicks"><input className="input" type="number" min="0" value={f.clicks} onChange={set("clicks")} /></Field>
          </div>
          {f.mode === "total" && (
            <Field label="Running since" hint="So AIMVA spreads these totals over the right days instead of counting them all as today.">
              <input className="input" type="date" value={f.since} max={new Date().toISOString().slice(0, 10)} onChange={set("since")} />
            </Field>
          )}
          <p className="text-xs text-faint">Running totals now: {inr(campaign.spend)} · {campaign.impressions.toLocaleString("en-IN")} impressions · {campaign.clicks.toLocaleString("en-IN")} clicks</p>
          <div className="flex justify-end"><Button type="submit" busy={busy}>Save results</Button></div>
        </form>
      )}
    </Modal>
  );
}

function CampaignModal({ open, products, defaultProduct, onClose, onSaved }) {
  const [f, setF] = useState({ name: "", platform: "meta", daily_budget: "", product_id: "" });
  const [busy, run] = useAction();
  useEffect(() => { if (open) setF({ name: "", platform: "meta", daily_budget: "", product_id: defaultProduct || products[0]?.id || "" }); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = (e) => {
    e.preventDefault();
    run(async () => {
      const c = await post("/api/campaigns", { name: f.name, platform: f.platform, daily_budget: Number(f.daily_budget || 0), product_id: f.product_id ? Number(f.product_id) : null });
      if (f.platform === "other") await patch(`/api/campaigns/${c.id}`, { status: "active" });
      onSaved();
      onClose();
    }, "Campaign added");
  };
  return (
    <Modal open={open} onClose={onClose} title="Add a campaign">
      <form onSubmit={save} className="space-y-4">
        <Field label="Name"><input className="input" required minLength={2} maxLength={200} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Diwali leads · Instagram" autoFocus /></Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Product"><select className="input" value={f.product_id} onChange={(e) => setF({ ...f, product_id: e.target.value })}>
            <option value="">No product</option>{products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}</select></Field>
          <Field label="Where it runs"><select className="input" value={f.platform} onChange={(e) => setF({ ...f, platform: e.target.value })}>
            <option value="meta">Meta</option><option value="google">Google Ads</option><option value="linkedin">LinkedIn</option><option value="other">Offline / other</option></select></Field>
          <Field label="Daily budget (₹)"><input className="input" type="number" min="0" value={f.daily_budget} onChange={(e) => setF({ ...f, daily_budget: e.target.value })} /></Field>
        </div>
        <p className="text-xs text-faint">Build the ad itself on the Meta, Google or LinkedIn pages, or run it elsewhere and enter its results here.</p>
        <div className="flex justify-end"><Button type="submit" busy={busy}>Add campaign</Button></div>
      </form>
    </Modal>
  );
}

/* ---- page -------------------------------------------------------------------------------------------- */
const CAMP_COLS = [
  { key: "name", label: "Campaign" }, { key: "platform", label: "Platform" }, { key: "product_name", label: "Product" }, { key: "status", label: "Status" },
  { key: "period_spend", label: "Spent (₹)", pdf: (v) => inr(v) }, { key: "leads", label: "Leads" }, { key: "cpl", label: "Cost per lead (₹)", pdf: (v) => inr(v) },
  { key: "target_cpl", label: "Target cost per lead (₹)", pdf: (v) => inr(v) }, { key: "ctr", label: "CTR %", pdf: (v) => pct(v) },
  { key: "health", label: "Health", get: (c) => HEALTH[c.health]?.[1] || c.health },
];
const PROD_COLS = [{ key: "name", label: "Product" }, { key: "campaigns", label: "Campaigns", get: (p) => p.campaigns?.length || 0 }, { key: "pages", label: "Pages", get: (p) => p.pages?.length || 0 }];

export default function Command() {
  const { user } = useAuth();
  const business = user?.workspace?.name || user?.company || user?.name || "";
  const [days, setDays] = useState("30");
  const { data, loading, reload } = useApi(`/api/command/overview?days=${days}`);
  const [productModal, setProductModal] = useState({ open: false, product: null });
  const [results, setResults] = useState(null);
  const [adding, setAdding] = useState(false);
  const [brief, setBrief] = useState(null);
  const [briefBusy, setBriefBusy] = useState(false);
  const [filter, setFilter] = useState("all");

  // Arriving from For you with #campaigns or #product-3: scroll there once the numbers are in.
  const { hash } = useLocation();
  useEffect(() => {
    if (!data || !hash) return;
    const t = setTimeout(() => document.querySelector(hash)?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    return () => clearTimeout(t);
  }, [data, hash]);
  const loadBrief = async () => {
    setBriefBusy(true);
    try { setBrief(await get("/api/command/brief")); } catch (e) { toast.error(e.message); } finally { setBriefBusy(false); }
  };
  const selectProduct = (pid) => {
    setFilter((f) => (f === pid ? "all" : pid));
    requestAnimationFrame(() => document.getElementById("campaigns")?.scrollIntoView({ behavior: "smooth" }));
  };

  const products = data?.products || [];
  const campaigns = useMemo(() => (data ? [...products.flatMap((p) => p.campaigns), ...data.unassigned.campaigns] : []), [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const pages = useMemo(() => (data ? [...products.flatMap((p) => p.pages), ...data.unassigned.pages] : []), [data]); // eslint-disable-line react-hooks/exhaustive-deps
  const empty = data && !products.length && !campaigns.length;

  return (
    <div>
      <PageHeader icon={Compass} tone="violet" title="Results" subtitle="What you spent, the leads and sales it brought, per product and campaign."
        actions={<div className="flex flex-wrap gap-2">
          <DownloadMenu name="Results" disabled={!data || empty}
            excel={() => [{ name: "Campaigns", columns: CAMP_COLS, rows: campaigns }, { name: "Products", columns: PROD_COLS, rows: products }]}
            pdf={async (filename) => (await import("../../lib/reports/results")).resultsReport({ data, days, business, filename })} />
          <Tabs value={days} onChange={setDays} tabs={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }]} />
          <Button onClick={() => setProductModal({ open: true, product: null })}><Plus className="size-4" /> Add product</Button>
        </div>} />
      <div className="mb-6">
        <AgentSwitch kind="autopilot" title="Campaign Autopilot" modes={{ suggest: "Suggest", auto: "Fix safely" }}
          text="Checks every campaign each morning. Suggest puts fixes in For you (the bell); Fix safely pauses money-wasters and trims overspend itself, never raising budgets." />
      </div>

      {loading || !data ? <div className="grid h-60 place-items-center"><Spinner className="size-6" /></div> : empty ? (
        <Empty icon={Package} title="Start with what you sell"
          text="Add a product, service or offer. Then link its campaigns and landing page, and AIMVA shows how each one performs and what to do next."
          action={<Button onClick={() => setProductModal({ open: true, product: null })}><Plus className="size-4" /> Add your first product</Button>} />
      ) : (
        <div className="space-y-8">
          <Pulse k={data.kpis} summary={data.summary} brief={brief} onBrief={loadBrief} briefBusy={briefBusy} />

          {/* Next steps live only in the For you panel (design.md: nothing said twice); this line points there. */}
          {data.recommendations.length > 0 && (
            <button type="button" onClick={() => window.dispatchEvent(new CustomEvent("aimva:foryou"))}
              className="-mt-4 flex w-full items-center gap-2 border-b border-line pb-3 text-left text-sm text-muted hover:text-strong">
              <span className="size-2 shrink-0 rounded-full bg-warm" aria-hidden />
              <span className="flex-1"><span className="font-semibold text-strong">Next steps</span> for these campaigns, ranked by impact, are in For you</span>
              <span className="font-medium text-brand">Open</span>
            </button>
          )}
          <div>
            <motion.aside variants={stagger} initial="hidden" animate="show" className="grid min-w-0 grid-cols-[minmax(0,1fr)] content-start gap-5 sm:grid-cols-2 xl:grid-cols-3">
              <motion.div variants={rise}><WeekAhead plan={data.plan} typical={data.account_cpl} /></motion.div>
              <motion.div variants={rise}><Pacing products={products} /></motion.div>
              <motion.div variants={rise} className="sm:col-span-2 xl:col-span-1"><Decisions items={data.decisions} /></motion.div>
            </motion.aside>
          </div>

          {products.length > 0 && (
            <Section title="Products" sub="What you sell, and how its advertising is doing.">
              <motion.div variants={stagger} initial="hidden" animate="show" className="grid grid-cols-[minmax(0,1fr)] gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {products.map((p) => <ProductCard key={p.id} p={p} selected={filter === p.id} onSelect={selectProduct} onEdit={(prod) => setProductModal({ open: true, product: prod })} />)}
              </motion.div>
            </Section>
          )}

          <Campaigns campaigns={campaigns} products={products} pages={pages} filter={filter} setFilter={setFilter}
            onChanged={reload} onResults={setResults} onAdd={() => setAdding(true)} />

          <Pages pages={pages} products={products} onChanged={reload} />
        </div>
      )}

      <ProductModal open={productModal.open} product={productModal.product} onClose={() => setProductModal({ open: false, product: null })} onSaved={reload} />
      <ResultsModal campaign={results} onClose={() => setResults(null)} onSaved={reload} />
      <CampaignModal open={adding} products={products} defaultProduct={typeof filter === "number" ? filter : null} onClose={() => setAdding(false)} onSaved={reload} />
    </div>
  );
}
