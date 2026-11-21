// One campaign's overview (2026-11-21, owner: "after launch, go straight to the overview of the specific work done").
// Results opens on it with ?campaign=ID: after Launch, from "See results", and from Home's "Live now".
import { Link } from "react-router-dom";
import { ArrowRight, Pencil, Users } from "lucide-react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const day = (iso) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });

/** Leads per day as bars (one series, one axis); the tooltip adds that day's spend. */
function LeadsChart({ trend, days }) {
  const data = trend.map((t) => ({ ...t, label: day(t.day) }));
  const total = data.reduce((n, t) => n + (t.leads || 0), 0);
  const best = data.reduce((b, t) => ((t.leads || 0) > (b?.leads || 0) ? t : b), null);
  return (
    <figure className="mt-5">
      <figcaption className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
        <span className="text-sm font-medium text-strong">Leads per day</span>
        <span className="text-xs text-muted">{total} in the last {days} days{best?.leads > 1 ? ` · best day ${best.label} (${best.leads})` : ""}</span>
      </figcaption>
      <div className="h-48 w-full">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} barCategoryGap={2}>
            <CartesianGrid vertical={false} stroke="var(--color-line)" />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: "var(--color-line-strong)" }} interval="preserveStartEnd" minTickGap={28}
              tick={{ fontSize: 12, fill: "var(--color-muted)" }} />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} width={28} tick={{ fontSize: 12, fill: "var(--color-muted)" }} />
            <Tooltip cursor={{ fill: "var(--color-surface-2)" }} content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const t = payload[0].payload;
              return (
                <div className="rounded-md bg-surface px-3 py-2 text-xs shadow-[var(--shadow-lift)] ring-1 ring-line">
                  <p className="text-muted">{t.label}</p>
                  <p className="font-semibold text-strong">{t.leads} lead{t.leads === 1 ? "" : "s"}</p>
                  <p className="text-muted">{inr(t.spend)} spent</p>
                </div>
              );
            }} />
            <Bar dataKey="leads" fill="var(--color-brand)" radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}

const inr = (v) => `₹${Number(v || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const PLATFORM = { meta: "Facebook and Instagram", google: "Google", linkedin: "LinkedIn" };
const STATUS = { active: "Running", paused: "Paused", draft: "Draft", ended: "Ended" };

export function CampaignFocus({ c, days, onAll }) {
  if (!c) return null;
  const fresh = !c.period_spend && !c.leads;
  const started = c.started_on ? new Date(c.started_on).toLocaleDateString(undefined, { day: "numeric", month: "short" }) : null;
  const numbers = [
    ["Spent", inr(c.period_spend ?? c.spend)],
    ["Leads", (c.leads ?? 0).toLocaleString("en-IN")],
    ["Cost per lead", c.cpl ? inr(c.cpl) : "–"],
    ["Sales", c.won ? `${c.won} · ${inr(c.revenue)}` : "–"],
  ];
  return (
    <section aria-labelledby="focus-h" className="max-w-4xl">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="focus-h" className="text-lg font-semibold text-strong">{c.name}</h2>
        <button type="button" onClick={onAll} className="text-sm font-medium text-brand hover:underline">All results</button>
      </div>
      <p className="mt-0.5 text-sm text-muted">
        {STATUS[c.status] || c.status} on {PLATFORM[c.platform] || c.platform}
        {started && ` · since ${started}`} · {inr(c.daily_budget)} a day
      </p>

      {fresh ? (
        <p className="mt-5 border-y border-line py-5 text-[15px] text-ink">
          It's live. The first numbers usually show within a few hours, and new leads land in Leads and on Home the moment they arrive.
        </p>
      ) : (
        <>
          <dl className="mt-5 grid grid-cols-2 gap-y-4 border-y border-line py-5 sm:grid-cols-4">
            {numbers.map(([k, v]) => (
              <div key={k}>
                <dt className="text-xs text-muted">{k} <span className="sr-only">in the last {days} days</span></dt>
                <dd className="mt-1 text-xl font-semibold tabular-nums text-strong">{v}</dd>
              </div>
            ))}
          </dl>
          {c.trend?.length > 1 && <LeadsChart trend={c.trend} days={days} />}
        </>
      )}

      <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm">
        <Link to="/app/leads" className="inline-flex items-center gap-1.5 font-medium text-brand hover:underline"><Users className="size-4" /> See its leads</Link>
        <Link to={`/app/ads/${c.platform}?view=work&id=${c.id}`} className="inline-flex items-center gap-1.5 font-medium text-brand hover:underline"><Pencil className="size-4" /> Change the ad</Link>
        <Link to="/app" className="inline-flex items-center gap-1.5 text-muted hover:text-strong">Home <ArrowRight className="size-3.5" /></Link>
      </div>
    </section>
  );
}
