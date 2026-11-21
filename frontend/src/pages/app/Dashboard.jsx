import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { MessageCircle } from "lucide-react";
import { Modal, cx } from "../../components/ui";
import { useOnboarding, useProjectsContext } from "../../components/AppLayout";
import { FirstLeadPath } from "../../components/Onboarding";
import { post } from "../../lib/api";
import { useLeadEvents } from "../../lib/live";
import { useAuth } from "../../lib/auth";
import { timeAgo, useApi } from "../../lib/hooks";
import { LaunchCard } from "../../components/Agents";
import { RecentWork } from "../../components/RecentWork";
import { answersFrom } from "../../lib/onboardingAnswers";
import { LoadErrorBar } from "../../components/LoadError";
import { AskBox } from "../../components/AskBox";
import { Mascot, homeLine } from "../../components/Mascot";

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

const inr = (v) => `₹${Number(v).toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
const SOURCE_WORD = { website: "your page", meta: "Meta ads", google: "Google ads", linkedin: "LinkedIn ads", whatsapp: "WhatsApp", voice: "calls", manual: "added by hand" };
const plural = (n, one, many = one + "s") => `${n} ${n === 1 ? one : many}`;

/** When the owner last opened Home, kept in this browser. Read once per visit, then moved to now. */
function useLastVisit(userId) {
  const [since] = useState(() => {
    const key = `aimva.home.seen.${userId}`;
    let prev = null;
    try { prev = localStorage.getItem(key); localStorage.setItem(key, new Date().toISOString()); } catch { /* private window */ }
    // A visit a minute ago says nothing: look back at least an hour.
    return prev && Date.now() - Date.parse(prev) > 3600e3 ? prev : new Date(Date.now() - 24 * 3600e3).toISOString();
  });
  return since;
}

function sinceWords(iso, firstVisit) {
  const d = new Date(iso);
  if (Date.now() - d.getTime() <= 24.5 * 3600e3 && firstVisit) return "In the last 24 hours";
  const day = d.toDateString() === new Date().toDateString() ? "today" : d.toLocaleDateString(undefined, { weekday: "long" });
  return `Since you were last here (${day}, ${d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })})`;
}

/** What came in, who is waiting, what AIMVA does by itself later. The 30-day numbers live on Results. */
function Today({ t, error, onRetry, isClient }) {
  if (error && !t) return <LoadErrorBar what="today" onRetry={onRetry} className="max-w-3xl" />;
  if (!t) return <div className="space-y-3" aria-label="Loading">{[0, 1].map((i) => <div key={i} className="h-6 max-w-xl animate-pulse rounded-full bg-surface-2" />)}</div>;
  const n = t.new.count;
  const sources = Object.entries(t.new.by_source).map(([s, c]) => `${c} from ${SOURCE_WORD[s] || s}`);
  const firstVisit = Math.abs(Date.parse(t.since + "Z") - (Date.now() - 24 * 3600e3)) < 120e3;
  const later = [t.later.follow_ups && `send ${plural(t.later.follow_ups, "follow-up")} on WhatsApp`,
    t.later.calls && `ring ${plural(t.later.calls, "lead")} once it's 9am where they are`].filter(Boolean);
  return (
    <div className="max-w-3xl space-y-6">
      <p className="text-[15px] leading-relaxed text-ink">
        <span className="text-muted">{sinceWords(t.since + "Z", firstVisit)}: </span>
        {n ? <><b className="font-semibold tabular-nums text-strong">{n} new lead{n === 1 ? "" : "s"}</b>{sources.length > 1 || n > 1 ? ` (${sources.join(", ")})` : ` from ${SOURCE_WORD[Object.keys(t.new.by_source)[0]] || "somewhere"}`}.</> : "no new leads."}
        {t.won.count > 0 && <> <b className="font-semibold text-brand">{plural(t.won.count, "sale")}{t.won.value ? ` worth ${inr(t.won.value)}` : ""}</b>.</>}
        {t.calls > 0 && <> {plural(t.calls, "call")} answered for you.</>}
      </p>

      {t.welcome_not_sent.count > 0 && !isClient && (
        <p className="text-sm text-warm">
          {t.welcome_not_sent.count === 1 ? "One welcome" : `${t.welcome_not_sent.count} welcomes`} didn't go out{t.welcome_not_sent.why ? `: ${t.welcome_not_sent.why}` : ""}.{" "}
          <Link to={/connected/i.test(t.welcome_not_sent.why) ? "/app/settings?tab=integrations" : `/app/leads?lead=${t.welcome_not_sent.lead_id}`} className="font-medium text-brand hover:underline">
            {/connected/i.test(t.welcome_not_sent.why) ? "Connect WhatsApp" : "Send it yourself"}
          </Link>
        </p>
      )}

      <section>
        <h2 className="mb-2 text-sm font-semibold text-strong">{t.waiting.count ? `Waiting on ${isClient ? "a reply" : "you"} (${t.waiting.count})` : "Nobody is waiting"}</h2>
        {t.waiting.count ? (
          <ul className="divide-y divide-line">
            {t.waiting.leads.map((l) => (
              <li key={l.id} className="flex items-center gap-3 py-2.5">
                <Link to={`/app/leads?lead=${l.id}`} className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-x-2 text-sm">
                    <span className="font-semibold text-strong hover:underline">{l.name}</span>
                    <span className="text-xs text-warm">waiting {timeAgo(l.waiting_since).replace(/ ago$/, "")}</span>
                    {l.language_name && <span className="text-xs text-muted">{l.language_name}</span>}
                  </p>
                  {l.message && <p className="line-clamp-1 text-sm text-muted">{l.message}</p>}
                </Link>
                {!isClient && l.phone && <Link to={`/app/leads?lead=${l.id}&reply=1`} className="btn-primary btn-sm shrink-0"><MessageCircle className="size-3.5" /> Reply</Link>}
              </li>
            ))}
          </ul>
        ) : <p className="text-sm text-muted">Everyone has had an answer. New leads land here first.</p>}
        {t.waiting.count > t.waiting.leads.length && <Link to="/app/leads" className="mt-1 inline-block text-sm font-medium text-brand hover:underline">All {t.waiting.count} waiting</Link>}
      </section>

      {later.length > 0 && !isClient && <p className="text-sm text-muted">Later today AIMVA will {later.join(" and ")}. Nothing for you to do.</p>}
    </div>
  );
}

/**
 * Home's right side (owner 2026-11-21: "this side looks too free of space"). The mascot sits on top of what is live
 * right now, one tap from its overview (after launching and signing back in it must be easy to find), then this
 * week's numbers. Running campaigns first, then live pages. With nothing live, the mascot points at the box instead.
 */
function HomeSide({ waiting = 0 }) {
  const { data } = useApi("/api/command/overview?days=7");
  const [taps, setTaps] = useState(0);
  const camps = data ? [...(data.products || []).flatMap((p) => p.campaigns), ...(data.unassigned?.campaigns || [])].filter((c) => c.status === "active") : [];
  const pages = data ? [...(data.products || []).flatMap((p) => p.pages), ...(data.unassigned?.pages || [])].filter((p) => p.published) : [];
  const rows = [
    ...camps.map((c) => ({ key: `c${c.id}`, to: `/app/command?campaign=${c.id}`, title: c.name,
      meta: `Ad · ${c.leads ? plural(c.leads, "lead") : "no leads yet"} · ${inr(c.period_spend || 0)} this week` })),
    ...pages.map((p) => ({ key: `p${p.id}`, to: `/app/websites?site=${p.id}`, title: p.name, meta: `Page · ${plural(p.visits || 0, "visit")}` })),
  ].slice(0, 4);
  const k = data?.kpis || {};
  const line = homeLine({ waiting, live: rows.length, leads: k.leads || 0, taps });
  return (
    <aside aria-label="Live now and this week" className="lg:sticky lg:top-6 lg:pt-10">
      <div className="relative z-10 -mb-5 flex justify-end pr-6">
        {data && <Mascot mood={line.mood} say={line.say} sayAlign="side" size={taps % 5 === 4 ? 128 : 92} arrive="hop" watch onTap={() => setTaps((n) => n + 1)} label="Poke the mascot" />}
      </div>
      <div className="rounded-2xl bg-surface p-5 pt-7 ring-1 ring-line">
        {rows.length > 0 ? (
          <section aria-labelledby="live-h">
            <h2 id="live-h" className="mb-1 flex items-center gap-2 text-sm font-semibold text-strong"><span className="size-2 rounded-full bg-brand" aria-hidden /> Live now</h2>
            <ul className="-mx-2 divide-y divide-line">
              {rows.map((r) => (
                <li key={r.key}>
                  <Link to={r.to} className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-surface-2/60">
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium text-strong">{r.title}</span>
                      <span className="block truncate text-xs text-muted">{r.meta}</span>
                    </span>
                    <span className="text-xs font-medium text-brand">Overview</span>
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        ) : (
          <p className="text-sm text-muted">{data ? "Nothing is live yet. Your pages and ads show here the moment they go live, one tap from their numbers." : "Loading…"}</p>
        )}
        {data && (
          <dl className="mt-5 grid grid-cols-3 gap-2 border-t border-line pt-4">
            {[["Leads", (k.leads || 0).toLocaleString("en-IN")], ["Spent", inr(k.spend || 0)], ["Sales", (k.won || 0).toLocaleString("en-IN")]].map(([a, b]) => (
              <div key={a}><dt className="text-xs text-muted">{a}</dt><dd className="mt-0.5 text-lg font-semibold tabular-nums text-strong">{b}</dd></div>
            ))}
          </dl>
        )}
        <Link to="/app/command" className="mt-4 inline-block text-sm font-medium text-brand hover:underline">This week in full</Link>
      </div>
    </aside>
  );
}

export default function Dashboard() {
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const onboarding = useOnboarding();
  const ob = onboarding?.data;
  const steps = Object.fromEntries((ob?.steps || []).map((s) => [s.key, s.done]));
  // The 4-step path is only for accounts from before /start (design.md 3.3: new projects get the reveal instead).
  // Getting started until the first lead exists or the person skips the guide. Data decides, not a setting.
  const { active, loading: projectsLoading } = useProjectsContext();
  const starting = !!ob && !projectsLoading && !ob.dismissed && !steps.lead && !active?.set_up;
  const isClient = user?.workspace?.role === "client";
  const since = useLastVisit(user.id);
  const { data, reload, error } = useApi(starting || !ob || projectsLoading ? null : `/api/today?since=${encodeURIComponent(since)}`);
  const sites = useApi("/api/sites", []);
  useLeadEvents(() => { reload(); });
  const [launch, setLaunch] = useState(false);
  useEffect(() => { if (params.get("launch")) { setLaunch(true); params.delete("launch"); setParams(params, { replace: true }); } }, [params, setParams]);

  const hour = new Date().getHours();
  const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const first = (user.name || "").split(" ")[0];

  const side = !isClient && ob && !projectsLoading && !starting;
  return (
    <div className={cx(side && "grid gap-10 lg:grid-cols-[minmax(0,48rem)_minmax(280px,340px)] lg:justify-between xl:gap-14")}>
    <div className="min-w-0">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted">{new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}</p>
          <h1 className="mt-1 text-[28px] font-semibold leading-tight text-strong">{starting ? `Welcome, ${first}` : `${greet}, ${first}`}</h1>
        </div>
      </div>

      {!isClient && ob && !projectsLoading && (
        <div className="mb-10">
          <AskBox hasPage={(sites.data || []).length > 0} waiting={data?.waiting?.count || 0} modules={active?.modules || []} />
        </div>
      )}

      {!ob && onboarding?.error ? (
        <LoadErrorBar what="your home page" onRetry={onboarding.reload} className="max-w-3xl" />
      ) : !ob || projectsLoading ? (
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
          <Today t={data} error={error} onRetry={reload} isClient={isClient} />
          <div className="mt-10 max-w-3xl">
            <RecentWork limit={8} />
            <p className="mt-4 text-xs text-muted">Your 30-day numbers and charts are on <Link to="/app/analytics" className="font-medium text-brand hover:underline">Results</Link>.</p>
          </div>
        </>
      )}

    </div>
      {side && <div><HomeSide waiting={data?.waiting?.count || 0} /></div>}
      <Modal open={launch} onClose={() => setLaunch(false)} title="Launch something new" wide>
        <p className="-mt-1 mb-4 text-sm text-muted">One link or sentence. AIMVA builds the page, ad drafts, call-back assistant and follow-ups. Ads always wait for you.</p>
        <LaunchCard />
      </Modal>
    </div>
  );
}
