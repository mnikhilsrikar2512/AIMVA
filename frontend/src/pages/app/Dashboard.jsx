import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Rocket } from "lucide-react";
import { motion } from "framer-motion";
import { CountUp, rise, spring, stagger } from "../../components/Motion";
import { Chip, Modal, cx } from "../../components/ui";
import { useOnboarding } from "../../components/AppLayout";
import { FirstLeadPath } from "../../components/Onboarding";
import { post } from "../../lib/api";
import { useLeadEvents } from "../../lib/live";
import { useAuth } from "../../lib/auth";
import { useApi } from "../../lib/hooks";
import { LaunchCard } from "../../components/Agents";
import { RecentWork } from "../../components/RecentWork";
import { nextLeadMilestone } from "../../components/Celebrate";
import { answersFrom } from "../../lib/onboardingAnswers";

export const SOURCE_TONE = { website: "pink", meta: "blue", google: "green", linkedin: "cyan", whatsapp: "green", voice: "violet", manual: "slate" };

export function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-line-strong bg-surface-2 px-3 py-2 text-xs shadow-xl">
      <p className="text-faint">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="font-semibold text-strong">{p.value} {p.name}</p>
      ))}
    </div>
  );
}

const STAGE = { new: ["New", "bg-sky-400"], contacted: ["Contacted", "bg-violet-400"], qualified: ["Qualified", "bg-amber-400"],
  won: ["Won", "bg-emerald-500"], lost: ["Lost", "bg-slate-300"] };

/** Where leads are in the pipeline; bars grow to their share so stuck stages stand out. */
function Pipeline({ funnel }) {
  const max = Math.max(1, ...funnel.map((f) => f.count));
  return (
    <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-3">
      {funnel.map((f) => {
        const [label, color] = STAGE[f.stage] || [f.stage, "bg-slate-300"];
        return (
          <motion.div key={f.stage} variants={rise}>
            <div className="mb-1 flex justify-between text-sm"><span className="text-ink">{label}</span><span className="font-semibold text-strong"><CountUp value={f.count} /></span></div>
            <div className="h-2 overflow-hidden rounded-full bg-ink/[0.06]">
              <motion.div className={cx("h-full rounded-full", color)} initial={{ width: 0 }} animate={{ width: `${(f.count / max) * 100}%` }} transition={{ ...spring, delay: 0.15 }} />
            </div>
          </motion.div>
        );
      })}
    </motion.div>
  );
}

const inr = (v) => `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

/** One sentence of numbers instead of a row of stat boxes. */
function NumbersLine({ k }) {
  if (!k) return <p className="h-5 w-72 max-w-full animate-pulse rounded-full bg-surface-2" aria-label="Loading numbers" />;
  const change = k.leads_change == null ? null : k.leads_change;
  return (
    <p className="text-[15px] leading-relaxed text-ink">
      <b className="font-semibold text-strong"><CountUp value={k.leads} /> lead{k.leads === 1 ? "" : "s"}</b> in the last 30 days
      {change != null && change !== 0 && <span className={change > 0 ? "text-emerald-700" : "text-muted"}> ({change > 0 ? "+" : ""}{change}%)</span>}
      {k.hot_leads > 0 && <>, <b className="font-semibold text-warm">{k.hot_leads} hot</b></>}.
      {k.cpl ? <> <b className="font-semibold text-strong">{inr(k.cpl)}</b> a lead.</> : null}
      {k.calls > 0 && <> {k.calls} call{k.calls === 1 ? "" : "s"} answered.</>}
      {" "}<Link to="/app/analytics" className="text-sm font-medium text-brand hover:underline">Charts</Link>
    </p>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const onboarding = useOnboarding();
  const ob = onboarding?.data;
  const steps = Object.fromEntries((ob?.steps || []).map((s) => [s.key, s.done]));
  // Getting started until the first lead exists or the person skips the guide. Data decides, not a setting.
  const starting = !!ob && !ob.dismissed && !steps.lead;
  const isClient = user?.workspace?.role === "client";
  const { data, reload } = useApi(starting || !ob ? null : "/api/analytics/overview?days=30");
  const sites = useApi(starting ? "/api/sites" : null, []);
  useLeadEvents(() => { reload(); });
  const [launch, setLaunch] = useState(false);
  useEffect(() => { if (params.get("launch")) { setLaunch(true); params.delete("launch"); setParams(params, { replace: true }); } }, [params, setParams]);

  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const first = user.name.split(" ")[0];
  const k = data?.kpis;
  const next = k ? nextLeadMilestone(k.leads) : null;

  return (
    <div>
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4 pr-10 md:pr-12">
        <div>
          <p className="text-sm text-muted">{new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}</p>
          <h1 className="serif-moment mt-1 text-3xl text-strong">{starting ? `Welcome, ` : `${greet}, `}<em className="text-warm">{first}</em></h1>
        </div>
        {!starting && !isClient && ob && (
          <button type="button" className="btn-ghost btn-sm" onClick={() => setLaunch(true)}><Rocket className="size-4" /> Launch something new</button>
        )}
      </div>

      {!ob ? (
        <div className="space-y-3" aria-label="Loading">{[0, 1, 2].map((i) => <div key={i} className="h-10 max-w-3xl animate-pulse rounded-lg bg-surface-2" style={{ opacity: 1 - i * 0.25 }} />)}</div>
      ) : starting ? (
        <>
          <FirstLeadPath status={ob} sites={sites.data} website={answersFrom(ob).website} onStatus={(s) => { onboarding.setData(s); sites.reload(); }} launch={<LaunchCard initialWhat={answersFrom(ob).website || ""} />} />
          <p className="mt-6 max-w-3xl text-xs text-muted">
            Know your way around already?{" "}
            <button type="button" className="font-medium text-brand hover:underline"
              onClick={async () => onboarding.setData(await post("/api/onboarding/dismiss", { dismissed: true }))}>Skip the guide</button>
            {" "}· Press <kbd>⌘K</kbd> to jump anywhere.
          </p>
        </>
      ) : (
        <>
          <NumbersLine k={k} />
          {next && <p className="mt-1 text-xs text-muted">{next.left} more to {next.target} leads.</p>}

          <div className="mt-8 grid gap-x-12 gap-y-10 lg:grid-cols-[minmax(0,1fr)_280px]">
            <div className="min-w-0"><RecentWork limit={12} /></div>
            <aside className="min-w-0">
              <h2 className="mb-3 text-sm font-semibold text-strong">Pipeline</h2>
              {data ? <Pipeline funnel={data.funnel} /> : <div className="h-32 animate-pulse rounded-lg bg-surface-2" />}
              <h2 className="mb-3 mt-8 text-sm font-semibold text-strong">Top leads</h2>
              {data?.top_leads?.length ? (
                <ul className="space-y-2.5">
                  {data.top_leads.map((l) => (
                    <li key={l.id} className="flex items-center justify-between gap-2 text-sm">
                      <Link to={`/app/leads?lead=${l.id}`} className="truncate py-1 text-ink hover:text-brand hover:underline">{l.name}</Link>
                      <span className="flex items-center gap-2">
                        <Chip tone={SOURCE_TONE[l.source] || "slate"}>{l.source}</Chip>
                        <span className={cx("w-8 text-right font-semibold", l.score >= 70 ? "text-warm" : "text-strong")}>{l.score}</span>
                      </span>
                    </li>
                  ))}
                </ul>
              ) : data ? <p className="text-sm text-muted">Your best leads show up here, scored by how likely they are to buy.</p> : null}
            </aside>
          </div>
        </>
      )}

      <Modal open={launch} onClose={() => setLaunch(false)} title="Launch something new" wide>
        <p className="-mt-1 mb-4 text-sm text-muted">One link or sentence. AIMVA builds the page, ad drafts, call-back assistant and follow-ups. Ads always wait for you.</p>
        <LaunchCard />
      </Modal>
    </div>
  );
}
