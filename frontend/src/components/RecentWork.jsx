// "Recent work": one list of what was made or happened lately — pictures, videos, calls, leads,
// campaigns and pages — newest first, one action each. Rows with hairlines, no cards.
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Globe, Megaphone, Phone, Play, UserRound } from "lucide-react";
import { Spinner, cx } from "./ui";
import { timeAgo, useApi } from "../lib/hooks";
import { useLeadEvents } from "../lib/live";
import { useIsClient } from "../lib/auth";
import { ListSkeleton } from "./ui";

const LABEL = { picture: "Picture", video: "Video", call: "Call", lead: "Lead", campaign: "Campaign", page: "Page" };
const ICON = { call: Phone, lead: UserRound, campaign: Megaphone, page: Globe };
const firstLine = (t = "", n = 90) => { const s = String(t).replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; };

export function RecentWork({ limit: initialLimit = 8 }) {
  const [limit, setLimit] = useState(initialLimit);
  const isClient = useIsClient();  // a client can open leads and pages; the rest is the agency's side
  const assets = useApi("/api/content/assets", []);
  const calls = useApi("/api/voice/calls", []);
  const leads = useApi("/api/leads", []);
  const camps = useApi("/api/campaigns", []);
  const sites = useApi("/api/sites", []);
  const sources = [assets, calls, leads, camps, sites];
  // Everything happening shows up here live: a new lead (and the call that follows) slides in at the top.
  useLeadEvents(() => { leads.reload(); calls.reload(); });
  const loading = sources.some((s) => s.loading);
  const failed = sources.filter((s) => s.error);

  const rows = useMemo(() => {
    const out = [];
    (assets.data || []).forEach((a) => out.push(a.kind === "video"
      ? { kind: "video", id: `v${a.id}`, at: a.created_at, to: `/app/videos?asset=${a.id}`, thumb: null, title: firstLine(a.prompt) || "Video",
          meta: a.status === "done" ? "Video" : a.status === "failed" ? "Didn't finish" : "Making it", go: a.status === "done" ? "Open" : null }
      : { kind: "picture", id: `i${a.id}`, at: a.created_at, to: `/app/images?asset=${a.id}`, thumb: a.url, title: firstLine(a.prompt) || "Picture", meta: "Picture", go: "Edit" }));
    (calls.data || []).forEach((c) => out.push({ kind: "call", id: `c${c.id}`, at: c.created_at, to: "/app/voice", title: `${c.channel === "phone" ? "Call to" : "Call with"} ${c.to_number || "a visitor"}`,
      meta: c.status === "completed" ? firstLine(c.transcript?.[c.transcript.length - 1]?.text || "Finished", 70) : c.status, go: "Transcript" }));
    (leads.data || []).slice(0, 30).forEach((l) => out.push({ kind: "lead", id: `l${l.id}`, at: l.created_at, to: `/app/leads?lead=${l.id}`, title: l.name || l.email || l.phone,
      meta: `${l.score >= 70 ? "Hot · " : ""}${l.source}${l.message ? ` · ${firstLine(l.message, 60)}` : ""}`, go: l.stage === "new" ? "Call" : "Open", hot: l.score >= 70 }));
    (camps.data || []).forEach((c) => out.push({ kind: "campaign", id: `k${c.id}`, at: c.created_at, to: `/app/ads/${c.platform}?view=work&id=${c.id}`, thumb: c.creative?.image_url, title: c.name,
      meta: `${c.status === "draft" ? "Draft" : c.status === "paused" ? "Paused" : "Running"} on ${c.platform}`, go: c.status === "draft" ? "Finish" : "Open" }));
    (sites.data || []).forEach((s) => out.push({ kind: "page", id: `s${s.id}`, at: s.updated_at, to: `/app/websites?site=${s.id}`, title: s.name,
      meta: s.published ? `Live · ${s.visits} visits` : "Not published yet", go: s.published ? "Open" : "Publish" }));
    return out.sort((a, b) => (a.at < b.at ? 1 : -1));
  }, [assets.data, calls.data, leads.data, camps.data, sites.data]);

  const all = rows;
  const shown = all.slice(0, limit);
  return (
    <section aria-labelledby="recent-h">
      <div className="mb-2 flex flex-col gap-1.5 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-2">
        <h2 id="recent-h" className="text-sm font-semibold text-strong">Recent</h2>
      </div>
      {loading ? <ListSkeleton rows={6} /> : (
        <>
          {failed.length > 0 && (
            <p className="mb-2 text-xs text-muted">Some items didn't load. <button className="font-medium text-brand hover:underline" onClick={() => failed.forEach((s) => s.reload())}>Try again</button></p>
          )}
          {shown.length === 0 && failed.length > 0 ? null : shown.length === 0 ? (
            <p className="border-y border-line py-6 text-center text-sm text-muted">
              Everything that happens shows up here: new leads, calls, pages, pictures and campaigns, newest first.
            </p>
          ) : (
            <ul className="border-t border-line">
              {shown.map((r) => {
                const Icon = ICON[r.kind];
                const opens = !isClient || /^\/app\/(leads|websites)/.test(r.to);
                const Row = opens ? Link : "div";
                return (
                  <li key={r.id} className="border-b border-line">
                    <Row to={opens ? r.to : undefined} className={cx("grid grid-cols-[32px_minmax(0,1fr)_auto] items-center gap-3 px-1 py-2 transition", opens && "hover:bg-surface-2")}>
                      <span className="relative grid size-8 place-items-center overflow-hidden rounded-md bg-surface-2 text-muted">
                        {r.thumb ? <img src={r.thumb} alt="" className="size-full object-cover" loading="lazy" onError={(e) => { e.currentTarget.style.display = "none"; }} />
                          : r.kind === "video" ? <Play className="size-3.5" /> : Icon ? <Icon className="size-4" /> : null}
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-medium text-strong">{r.title}</span>
                        <span className="block truncate text-xs text-muted"><span className="text-faint">{LABEL[r.kind]} · </span>{r.hot ? <span className="text-warm">{r.meta}</span> : r.meta}</span>
                      </span>
                      <span className="flex items-center gap-2 whitespace-nowrap text-xs text-muted">
                        <span className="hidden sm:inline">{timeAgo(r.at)}</span>
                        {opens && r.go && <span className="font-medium text-brand">{isClient ? "Open" : r.go}</span>}
                      </span>
                    </Row>
                  </li>
                );
              })}
            </ul>
          )}
          {all.length > shown.length && (
            <button type="button" className="btn-subtle btn-sm mt-2" onClick={() => setLimit((n) => n + 20)}>Show {Math.min(20, all.length - shown.length)} more</button>
          )}
        </>
      )}
    </section>
  );
}
