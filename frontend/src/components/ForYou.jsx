// "For you": one place, reachable from every page, for what needs the owner (Next steps)
// and what AIMVA did on its own (Updates). Pages don't repeat these lists.
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Bell, ArrowUpRight, Bot, TrendingUp, X } from "lucide-react";
import { toast } from "sonner";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "./shadcn/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "./shadcn/tabs";
import { Spinner, cx } from "./ui";
import { post } from "../lib/api";
import { timeAgo, useApi } from "../lib/hooks";
import { useAgentEvents, useLeadEvents } from "../lib/live";
import { useIsClient } from "../lib/auth";

const DOT = { high: "bg-warm", medium: "bg-amber-500", low: "bg-line-strong" };
const SEEN_KEY = "aimva_updates_seen_at";
const readSeen = () => { try { return localStorage.getItem(SEEN_KEY) || ""; } catch { return ""; } };
const writeSeen = (v) => { try { localStorage.setItem(SEEN_KEY, v); } catch { /* storage blocked */ } };

function useForYou() {
  const recs = useApi("/api/command/overview?days=7");
  const jobs = useApi("/api/agents/jobs?limit=20", []);
  useLeadEvents(() => recs.reload());
  useAgentEvents((d) => { if (d.type === "finished") jobs.reload(); });
  return { recs, jobs };
}

function NextSteps({ recs, onGo }) {
  const { data, error, reload, setData } = recs;
  const [busy, setBusy] = useState(null);
  if (error) return (
    <div className="px-1 py-6 text-center text-sm text-muted">
      Next steps didn't load. <button className="font-medium text-brand hover:underline" onClick={reload}>Try again</button>
    </div>
  );
  if (!data) return <div className="grid h-24 place-items-center"><Spinner className="size-5" /></div>;
  const items = data.recommendations || [];
  if (!items.length) return (
    <div className="px-1 py-8 text-center">
      <p className="font-medium text-strong">You're all caught up</p>
      <p className="mt-1 text-sm text-muted">New suggestions show up here when something needs you.</p>
    </div>
  );
  // Same as pressing the button in the Command Center: the server runs the action (e.g. the voice agent calls).
  const accept = async (r, alt = false) => {
    setBusy(r.key);
    try {
      const res = await post(`/api/command/recommendations/${encodeURIComponent(r.key)}/decide?days=7`, { decision: "accepted", alt });
      toast.success(res.result || "Done.");
      setData({ ...data, recommendations: items.filter((x) => x.key !== r.key) });
    } catch (e) { toast.error(e.message); } finally { setBusy(null); }
  };
  const snooze = async (r) => {
    setData({ ...data, recommendations: items.filter((x) => x.key !== r.key) });
    try { await post(`/api/command/recommendations/${encodeURIComponent(r.key)}/decide?days=7`, { decision: "snoozed" }); toast("Hidden for a week."); }
    catch (e) { toast.error(e.message); reload(); }
  };
  const dismiss = async (r) => {
    setData({ ...data, recommendations: items.filter((x) => x.key !== r.key) });
    try { await post(`/api/command/recommendations/${encodeURIComponent(r.key)}/decide?days=7`, { decision: "dismissed" }); toast("Dismissed for 30 days."); }
    catch (e) { toast.error(e.message); reload(); }
  };
  // "scroll" actions point at a section of Results (#campaigns, #product-3); open Results there.
  const linkFor = (a) => (a?.type === "open" && a.to?.startsWith("/") ? a.to : a?.type === "scroll" ? `/app/command${a.to?.startsWith("#") ? a.to : ""}` : null);
  return (
    <ul className="border-t border-line">
      {items.map((r, i) => {
        const runs = r.action && !["open", "scroll"].includes(r.action.type);
        const to = linkFor(r.action) || "/app/command";
        const altLink = r.alt && linkFor(r.alt);
        const label = r.action?.label || "Review";
        const primary = cx("btn-sm", i === 0 ? "btn-primary" : "btn-ghost");
        return (
          <li key={r.key} className="flex gap-3 border-b border-line py-3">
            <span className={cx("mt-1.5 size-2 shrink-0 rounded-full", DOT[r.priority] || DOT.low)} aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-strong">{r.title}</p>
              {r.why && <p className="mt-0.5 line-clamp-2 text-xs text-muted">{r.why}</p>}
              {r.impact && <p className="mt-1 inline-flex items-center gap-1 text-xs font-semibold text-emerald-700"><TrendingUp className="size-3.5" />{r.impact}</p>}
              <div className="mt-2 flex flex-wrap items-center gap-1.5">
                {runs
                  ? <button type="button" className={primary} disabled={busy === r.key} onClick={() => accept(r)}>{busy === r.key && <Spinner />}{label}</button>
                  : <Link to={to} onClick={onGo} className={primary}>{label}</Link>}
                {r.alt && (altLink
                  ? <Link to={altLink} onClick={onGo} className="btn-ghost btn-sm">{r.alt.label}</Link>
                  : <button type="button" className="btn-ghost btn-sm" disabled={busy === r.key} onClick={() => accept(r, true)}>{r.alt.label}</button>)}
                <button type="button" className="btn-subtle btn-sm" onClick={() => snooze(r)} title="Hide for a week">Not now</button>
                <button type="button" className="btn-subtle btn-sm px-2" onClick={() => dismiss(r)} title="Dismiss for 30 days" aria-label="Dismiss for 30 days"><X className="size-3.5" /></button>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

function Updates({ jobs, seenAt }) {
  const { data, error, reload, loading } = jobs;
  if (error) return <div className="px-1 py-6 text-center text-sm text-muted">Updates didn't load. <button className="font-medium text-brand hover:underline" onClick={reload}>Try again</button></div>;
  if (loading) return <div className="grid h-24 place-items-center"><Spinner className="size-5" /></div>;
  if (!data.length) return <p className="px-1 py-8 text-center text-sm text-muted">AIMVA's agents welcome new leads, follow up, check your campaigns every morning and tidy new pages. What they do shows up here.</p>;
  return (
    <ul className="border-t border-line">
      {data.map((j) => (
        <li key={j.id} className="flex gap-3 border-b border-line py-3">
          <Bot className={cx("mt-0.5 size-4 shrink-0", j.status === "failed" ? "text-danger" : "text-muted")} aria-hidden />
          <div className="min-w-0 flex-1">
            <p className="text-sm text-strong">{j.title}</p>
            <p className="mt-0.5 text-xs text-muted">{j.status === "failed" ? "Didn't finish" : j.agent} · {timeAgo(j.created_at)}</p>
          </div>
          {seenAt < j.created_at && <span className="mt-1.5 size-2 shrink-0 rounded-full bg-brand" aria-label="New" />}
        </li>
      ))}
    </ul>
  );
}

export function ForYou({ className }) {
  const [open, setOpen] = useState(false);
  const btn = useRef(null);
  const [tab, setTab] = useState("next");
  const [seenAt, setSeenAt] = useState(readSeen);
  const { recs, jobs } = useForYou();
  const isClient = useIsClient();
  const location = useLocation();
  useEffect(() => { setOpen(false); }, [location.pathname]);
  // N opens the panel from anywhere, unless the person is typing.
  useEffect(() => {
    const onKey = (e) => {
      const t = e.target;
      if (e.key.toLowerCase() !== "n" || e.metaKey || e.ctrlKey || e.altKey || t.isContentEditable || /INPUT|TEXTAREA|SELECT/.test(t.tagName)) return;
      if (document.querySelector("[role=dialog]") && !open) return;
      if (!btn.current?.offsetParent) return;  // the hidden twin (phone vs desktop bell) stays quiet
      e.preventDefault(); setOpen((v) => !v);
    };
    // Two bells exist (phone header, desktop corner); only the one on screen answers "open For you".
    const onOpen = () => { if (btn.current?.offsetParent) setOpen(true); };
    window.addEventListener("keydown", onKey);
    window.addEventListener("aimva:foryou", onOpen);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("aimva:foryou", onOpen); };
  }, [open]);
  const nNext = isClient ? 0 : recs.data?.recommendations?.length || 0;  // a view-only member can't run suggestions
  const nNew = (jobs.data || []).filter((j) => seenAt < j.created_at).length;
  const count = nNext + nNew;
  const onOpenChange = (v) => {
    setOpen(v);
    if (!v && tab === "updates") { const now = new Date().toISOString(); writeSeen(now); setSeenAt(now); }
  };
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <button ref={btn} type="button" onClick={() => setOpen(true)} title="Next steps and updates (N)"
        aria-label={`Next steps and updates${count ? `, ${count} new` : ""}`}
        className={cx("relative grid size-9 place-items-center rounded-lg text-muted transition hover:bg-surface-2 hover:text-strong", className)}>
        <Bell className="size-[18px]" />
        {count > 0 && <span aria-hidden className="absolute -right-0.5 -top-0.5 min-w-[18px] rounded-full bg-strong px-1 text-center text-xs font-semibold leading-[18px] text-white ring-2 ring-bg">{count > 9 ? "9+" : count}</span>}
      </button>
      <SheetContent className="max-w-[400px]">
        <div className="border-b border-line px-4 py-3 pr-12">
          <SheetTitle>For you</SheetTitle>
          <SheetDescription className="sr-only">What needs you and what AIMVA did for you.</SheetDescription>
        </div>
        <Tabs value={tab} onValueChange={(v) => { setTab(v); if (v !== "updates") { const now = new Date().toISOString(); writeSeen(now); setSeenAt(now); } }} className="flex min-h-0 flex-1 flex-col">
          <div className="px-4 pt-3">
            <TabsList className="w-full">
              <TabsTrigger value="next" className="flex-1">Next steps{nNext ? <span className="ml-1 text-faint">{nNext}</span> : null}</TabsTrigger>
              <TabsTrigger value="updates" className="flex-1">Updates{nNew ? <span className="ml-1 text-faint">{nNew}</span> : null}</TabsTrigger>
            </TabsList>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 pt-2">
            <TabsContent value="next">{isClient ? (
              <p className="px-1 py-8 text-center text-sm text-muted">You can view this project. Next steps go to the people who run it.</p>
            ) : <NextSteps recs={recs} onGo={() => setOpen(false)} />}</TabsContent>
            <TabsContent value="updates"><Updates jobs={jobs} seenAt={seenAt} /></TabsContent>
          </div>
        </Tabs>
        <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-xs text-muted">
          <span className="max-md:invisible">Press <kbd>N</kbd> on any page</span>
          <Link to="/app/command" onClick={() => setOpen(false)} className="inline-flex items-center gap-1 font-medium text-brand hover:underline">Results <ArrowUpRight className="size-3.5" /></Link>
        </div>
      </SheetContent>
    </Sheet>
  );
}
