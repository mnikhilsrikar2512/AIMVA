import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight, Bot, Check, CircleDashed, Clock, Globe, Minus, Rocket, X } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, cx } from "./ui";
import { get, post, put } from "../lib/api";
import { parseServerDate, timeAgo, useApi } from "../lib/hooks";
import { useAgentEvents } from "../lib/live";
import { ease } from "./Motion";

/*
 * The work agents (backend: app/agents) show up where their work lands rather than on a page of their own:
 * the Launch card and activity feed on the Dashboard, the Concierge switch in Leads, Autopilot in Command Center.
 */

const STEP_ICON = { done: [Check, "bg-emerald-500 text-white"], skipped: [Minus, "bg-surface-2 text-muted"], failed: [X, "bg-rose-500 text-white"] };

function Steps({ steps, running }) {
  return (
    <ol className="space-y-2.5">
      <AnimatePresence initial={false}>
        {steps.map((s, i) => {
          const [Icon, tone] = STEP_ICON[s.status] || STEP_ICON.done;
          return (
            <motion.li key={i} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.35, ease }} className="flex gap-3">
              <span className={cx("mt-0.5 grid size-5 shrink-0 place-items-center rounded-full", tone)}><Icon className="size-3" strokeWidth={3} /></span>
              <span className="min-w-0 text-sm">
                <span className="font-medium text-strong">{s.label}</span>
                {s.detail && <span className="block text-xs text-muted">{s.detail}</span>}
              </span>
            </motion.li>
          );
        })}
      </AnimatePresence>
      {running && (
        <li className="flex items-center gap-3 text-sm text-muted">
          <CircleDashed className="size-5 animate-spin text-brand [animation-duration:2.4s]" /> Working on the next step…
        </li>
      )}
    </ol>
  );
}

const PLATFORMS = [["meta", "Meta"], ["google", "Google"], ["linkedin", "LinkedIn"]];

/** One link, brochure or sentence → product, page, ad drafts, voice assistant and follow-ups (the Launch Agent). */
export function LaunchCard({ initialWhat = "" } = {}) {
  const { data: docs } = useApi("/api/references?kind=document", []);
  const [f, setF] = useState({ what: initialWhat, reference_id: "", monthly_budget: "", platforms: ["meta"], publish: false });
  const [job, setJob] = useState(null);
  const [busy, setBusy] = useState(false);
  useAgentEvents((d) => { if (job && d.job.id === job.id) setJob(d.job); });
  useEffect(() => {  // coming back to a launch that's running (or just finished) shows it again
    get("/api/agents/jobs?kind=launch&limit=1").then(([j]) => {
      const fresh = j && Date.now() - parseServerDate(j.created_at).getTime() < 15 * 60 * 1000;
      if (j && (j.status === "queued" || j.status === "running" || fresh)) setJob(j);
    }).catch(() => {});
  }, []);

  const isUrl = /^(https?:\/\/)?[\w-]+(\.[\w-]+)+(\/\S*)?$/i.test(f.what.trim());
  const start = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const j = await post("/api/agents/launch", {
        url: isUrl ? f.what.trim() : "", description: isUrl ? "" : f.what.trim(), reference_id: f.reference_id ? Number(f.reference_id) : null,
        monthly_budget: Number(f.monthly_budget) || 0, platforms: f.platforms, publish: f.publish,
      });
      setJob(j);
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  const running = job && (job.status === "queued" || job.status === "running");
  useEffect(() => {  // live events update the steps; polling covers a dropped connection
    if (!running) return;
    const t = setInterval(() => get(`/api/agents/jobs/${job.id}`).then(setJob).catch(() => {}), 3000);
    return () => clearInterval(t);
  }, [running, job?.id]);

  return (
    <Card className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute -right-16 -top-20 size-64 rounded-full bg-[radial-gradient(circle,rgba(109,93,252,.18),transparent_65%)]" />
      <div className="relative flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-2xl bg-gradient-to-br from-brand to-brand-2 text-white"><Rocket className="size-5" /></span>
        <div className="min-w-0">
          <h2 className="font-semibold text-strong">Launch with AIMVA</h2>
          <p className="text-sm text-muted">Paste your website or describe what you sell. AIMVA builds the landing page, ad drafts, call-back assistant and follow-ups for you.</p>
        </div>
      </div>

      {!job ? (
        <form onSubmit={start} className="relative mt-4 space-y-3">
          <div className="relative">
            <Globe className="pointer-events-none absolute left-3.5 top-3.5 size-4 text-faint" />
            <textarea className="input min-h-[52px] pl-10" rows={2} required={!f.reference_id} maxLength={1000} value={f.what}
              onChange={(e) => setF({ ...f, what: e.target.value })}
              placeholder="yourwebsite.com, or “3 BHK flats in Kokapet from ₹1.2 Cr, ready by 2027”" />
          </div>
          <div className="grid gap-3 sm:grid-cols-3">
            <select className="input" value={f.reference_id} onChange={(e) => setF({ ...f, reference_id: e.target.value })} aria-label="Brochure">
              <option value="">No brochure</option>
              {docs.map((d) => <option key={d.id} value={d.id}>{d.filename}</option>)}
            </select>
            <input className="input" type="number" min="0" inputMode="numeric" placeholder="Monthly ad budget (₹)" value={f.monthly_budget}
              onChange={(e) => setF({ ...f, monthly_budget: e.target.value })} aria-label="Monthly ad budget" />
            <div className="flex items-center gap-1.5">
              {PLATFORMS.map(([v, l]) => {
                const on = f.platforms.includes(v);
                return (
                  <button key={v} type="button" aria-pressed={on} onClick={() => setF({ ...f, platforms: on ? f.platforms.filter((x) => x !== v) : [...f.platforms, v] })}
                    className={cx("rounded-full px-3 py-1.5 text-xs font-medium transition", on ? "bg-strong text-white" : "bg-surface-2 text-ink hover:bg-lavender")}>{l}</button>
                );
              })}
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm text-ink">
              <input type="checkbox" className="size-4 accent-violet-500" checked={f.publish} onChange={(e) => setF({ ...f, publish: e.target.checked })} />
              Put the page live straight away <span className="text-faint">(ads always wait for you)</span>
            </label>
            <Button type="submit" busy={busy}><Bot className="size-4" /> Do it for me</Button>
          </div>
        </form>
      ) : (
        <div className="relative mt-5">
          <Steps steps={job.steps || []} running={running} />
          {job.status === "done" && job.result?.next?.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease }} className="mt-5 rounded-2xl bg-surface-2/70 p-4">
              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">Left for you</p>
              <ul className="space-y-1.5">
                {job.result.next.map((n) => (
                  <li key={n.title}>
                    <Link to={n.link} className="group flex items-center justify-between gap-3 rounded-xl px-2 py-1.5 text-sm hover:bg-white">
                      <span><b className="font-semibold text-strong">{n.title}</b> <span className="text-muted">{n.detail}</span></span>
                      <ArrowRight className="size-4 shrink-0 text-faint transition group-hover:translate-x-0.5 group-hover:text-brand" />
                    </Link>
                  </li>
                ))}
              </ul>
            </motion.div>
          )}
          {!running && <button type="button" className="btn-ghost btn-sm mt-4" onClick={() => setJob(null)}>Launch something else</button>}
        </div>
      )}
    </Card>
  );
}

const KIND_TONE = { launch: "bg-violet-500", concierge: "bg-emerald-500", autopilot: "bg-sky-500", weekly_report: "bg-amber-500", page_fixer: "bg-pink-500" };

/** What the agents did for you lately. */
export function AgentActivity({ limit = 8 }) {
  const { data: jobs, reload } = useApi(`/api/agents/jobs?limit=${limit}`, []);
  useAgentEvents((d) => { if (d.type === "finished") reload(); });
  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 font-semibold text-strong"><Bot className="size-4 text-brand" /> Done for you</h2>
      </div>
      {jobs.length === 0 ? (
        <p className="text-sm text-muted">AIMVA's agents welcome new leads, follow up, check your campaigns every morning and tidy new pages. What they do shows up here.</p>
      ) : (
        <ul className="space-y-3">
          {jobs.map((j) => (
            <li key={j.id} className="flex gap-3">
              <span className={cx("mt-1.5 size-2 shrink-0 rounded-full", j.status === "failed" ? "bg-rose-500" : KIND_TONE[j.kind])} />
              <span className="min-w-0 text-sm">
                <span className="block truncate text-strong">{j.title}</span>
                <span className="text-xs text-faint">{j.agent} · {timeAgo(j.created_at)}</span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

/** On/off (and suggest/auto) for one agent, shown on the page whose work it does. */
export function AgentSwitch({ kind, title, text, modes }) {
  const { data: agents, setData } = useApi("/api/agents", []);
  const a = agents.find((x) => x.kind === kind);
  const [saving, setSaving] = useState(false);
  if (!a) return null;
  const save = async (patch) => {
    setSaving(true);
    try {
      const next = await put(`/api/agents/${kind}`, patch);
      setData((all) => all.map((x) => (x.kind === kind ? next : x)));
    } catch (e) { toast.error(e.message); } finally { setSaving(false); }
  };
  const state = !a.enabled ? "off" : modes ? a.mode : "on";
  const options = modes ? [["off", "Off"], ["suggest", modes.suggest], ["auto", modes.auto]] : [["off", "Off"], ["on", "On"]];
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl bg-surface px-4 py-3 shadow-[var(--shadow-soft)] max-sm:-mx-4 max-sm:rounded-none max-sm:shadow-[0_-1px_0_var(--color-line),0_1px_0_var(--color-line)]">
      <div className="flex min-w-0 items-center gap-3">
        <span className={cx("grid size-9 shrink-0 place-items-center rounded-xl", a.enabled ? "bg-emerald-500/15 text-emerald-600" : "bg-surface-2 text-faint")}>
          <Bot className="size-4" />
        </span>
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-strong">{title}</span>
          <span className="block text-xs text-muted">{text}{a.last_run_at && <> · <Clock className="inline size-3" /> last ran {timeAgo(a.last_run_at)}</>}</span>
        </span>
      </div>
      <div role="radiogroup" aria-label={title} className={cx("flex rounded-full bg-surface-2 p-0.5", saving && "opacity-60")}>
        {options.map(([v, l]) => (
          <button key={v} type="button" role="radio" aria-checked={state === v} disabled={saving}
            onClick={() => save(v === "off" ? { enabled: false } : modes ? { enabled: true, mode: v } : { enabled: true })}
            className={cx("rounded-full px-3 py-1 text-xs font-semibold transition", state === v ? "bg-white text-strong shadow-sm" : "text-muted hover:text-ink")}>{l}</button>
        ))}
      </div>
    </div>
  );
}

/** The concierge's planned follow-ups for one lead. */
export function FollowUps({ leadId }) {
  const { data } = useApi(`/api/agents/leads/${leadId}/follow-ups`, []);
  if (!data.length) return null;
  const label = { day2: "Day-2 follow-up", day7: "Day-7 follow-up" };
  return (
    <div className="rounded-2xl bg-surface-2/60 px-3 py-2.5 text-xs">
      <p className="mb-1 flex items-center gap-1.5 font-semibold text-strong"><Bot className="size-3.5 text-brand" /> Lead Concierge</p>
      <ul className="space-y-0.5 text-muted">
        {data.map((f) => (
          <li key={f.step} className="flex justify-between gap-2">
            <span>{label[f.step]}</span>
            <span className={cx(f.status === "sent" && "text-emerald-600", f.status === "skipped" && "text-faint")}>
              {f.status === "pending" ? parseServerDate(f.due_at).toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" })
                : f.status === "sent" ? "Sent" : f.note || "Skipped"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export async function runAgent(kind, body) {
  return post(`/api/agents/${kind}/run`, body || {});
}
