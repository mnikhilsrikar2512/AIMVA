// One campaign's overview (2026-11-21, owner: "after launch, go straight to the overview of the specific work done").
// Results opens on it with ?campaign=ID: after Launch, from "See results", and from Home's "Live now".
import { Link } from "react-router-dom";
import { ArrowRight, Pencil, Users } from "lucide-react";
import { Sparkline } from "./Motion";

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
          {c.trend?.length > 1 && (
            <div className="mt-4">
              <p className="mb-1 text-xs text-muted">Leads per day, last {days} days</p>
              <Sparkline points={c.trend.map((t) => t.leads)} height={44} className="w-full" />
            </div>
          )}
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
