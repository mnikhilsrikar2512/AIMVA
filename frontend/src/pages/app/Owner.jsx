import { useState } from "react";
import { Check, Gauge, LayoutTemplate, ShieldAlert, Sparkles, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Chip, Empty, PageHeader, Spinner, Stat, StatStrip, Tabs, ListSkeleton } from "../../components/ui";
import { post } from "../../lib/api";
import { timeAgo, useApi } from "../../lib/hooks";
import { summary } from "../../components/Templates";
import { useAuth } from "../../lib/auth";

const MODULE = { image: "Images", video: "Videos", website: "Websites", ads: "Ads", voice: "Voice", whatsapp: "WhatsApp" };

/** The template agent at platform level: what's used, what people change, where templates are missing. */
function TemplateReview() {
  const { data, setData, loading } = useApi("/api/admin/templates");
  const [busy, setBusy] = useState(false);
  const [deciding, setDeciding] = useState(null);
  if (loading || !data) return <div className="grid h-24 place-items-center"><Spinner className="size-5" /></div>;
  const review = async () => {
    setBusy(true);
    try {
      const r = await post("/api/admin/templates/review");
      setData((d) => ({ ...d, pending: r.pending }));
      toast(r.new ? `${r.new} new template suggestion${r.new === 1 ? "" : "s"} to review.` : "Nothing new to suggest right now.");
    } catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };
  const decide = async (t, action) => {
    setDeciding(t.id);
    try {
      await post(`/api/admin/templates/${t.id}/${action}`);
      setData((d) => ({ ...d, pending: d.pending.filter((x) => x.id !== t.id), published: action === "publish" ? [...d.published, t] : d.published }));
      toast.success(action === "publish" ? `“${t.name}” is now available to every user.` : "Dismissed");
    } catch (e) { toast.error(e.message); } finally { setDeciding(null); }
  };
  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h2 className="flex items-center gap-2 text-lg font-bold"><LayoutTemplate className="size-5 text-brand" /> Templates</h2>
          <p className="text-sm text-muted">{data.builtin} built-in · {data.published.length} published by you · {data.total_uses} uses so far</p></div>
        <Button onClick={review} busy={busy}><Sparkles className="size-4" /> Review templates now</Button>
      </div>
      {data.pending.length > 0 && (
        <div className="grid grid-cols-[minmax(0,1fr)] gap-3 md:grid-cols-2">
          {data.pending.map((t) => {
            const [line, meta] = summary(t.module, t.payload);
            return (
              <Card key={t.id} className="p-4">
                <div className="flex items-start justify-between gap-2"><p className="font-semibold text-strong">{t.name}</p><Chip tone="violet">{MODULE[t.module]}</Chip></div>
                <p className="mt-2 rounded-xl bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900"><Sparkles className="mr-1 inline size-3" />{t.reason}</p>
                <p className="mt-2 text-xs italic text-ink">{line}</p>{meta && <p className="text-xs text-faint">{meta}</p>}
                <div className="mt-3 flex gap-2">
                  <Button size="sm" busy={deciding === t.id} onClick={() => decide(t, "publish")}><Check className="size-3.5" /> Publish to everyone</Button>
                  <Button size="sm" variant="subtle" disabled={deciding === t.id} onClick={() => decide(t, "dismiss")}><X className="size-3.5" /> Dismiss</Button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <h3 className="mb-3 font-semibold text-strong">Most used, and what people change</h3>
          {data.usage.length === 0 ? <p className="text-sm text-muted">No templates used yet.</p> : (
            <ul className="divide-y divide-line text-sm">
              {data.usage.slice(0, 8).map((u) => (
                <li key={u.ref} className="py-2.5">
                  <div className="flex justify-between gap-2"><span className="truncate text-strong">{u.name} <span className="text-xs text-faint">· {MODULE[u.module]}</span></span>
                    <span className="shrink-0 font-semibold">{u.uses} use{u.uses === 1 ? "" : "s"} · {u.users} user{u.users === 1 ? "" : "s"}</span></div>
                  {u.most_edited.length > 0 && <p className="mt-0.5 text-xs text-muted">Changed most: {u.most_edited.map((m) => `${m.label} (${m.rate}%)`).join(", ")}</p>}
                </li>
              ))}
            </ul>
          )}
        </Card>
        <Card>
          <h3 className="mb-3 font-semibold text-strong">Gaps</h3>
          {data.coverage.length === 0 ? <p className="text-sm text-muted">Every industry your users are in has templates in every module.</p> : (
            <ul className="space-y-1.5 text-sm">
              {data.coverage.slice(0, 8).map((c) => <li key={c.industry + c.module} className="text-ink">{c.industry} · {MODULE[c.module]}: <span className="text-muted">no templates for {c.users} user{c.users === 1 ? "" : "s"}</span></li>)}
            </ul>
          )}
          {data.unused.length > 0 && <p className="mt-4 text-xs text-faint">Not used yet: {data.unused.slice(0, 6).map((u) => u.name).join(", ")}{data.unused.length > 6 ? ` and ${data.unused.length - 6} more` : ""}.</p>}
        </Card>
      </div>
    </section>
  );
}

const fmt = (v, suffix = "") => (v === null || v === undefined ? "—" : `${v}${suffix}`);

function Bar({ label, value, max, tone = "bg-brand" }) {
  return (
    <div>
      <div className="flex justify-between text-sm"><span className="text-ink">{label}</span><span className="font-semibold text-strong">{value}</span></div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-ink/[0.06]"><div className={`h-full rounded-full ${tone}`} style={{ width: `${max ? (100 * value) / max : 0}%` }} /></div>
    </div>
  );
}

/** Platform owner view: are people getting work they can use first time, and where does it go wrong? */
export default function Owner() {
  const { user } = useAuth();
  const [days, setDays] = useState("30");
  const { data: m, loading, error } = useApi(`/api/admin/metrics?days=${days}`);

  if (error) {
    return (
      <div>
        <PageHeader icon={Gauge} title="Quality & usage" subtitle="Platform-wide quality for owners." />
        <Card><Empty icon={ShieldAlert} title="Owners only" text={error.message} /></Card>
      </div>
    );
  }
  const w = m?.websites;
  const fb = m?.feedback;
  const maxReason = Math.max(1, ...(fb?.reasons || []).map((r) => r.count));
  const maxProv = Math.max(1, ...(m?.providers || []).map((p) => p.images + p.videos));

  return (
    <div>
      <PageHeader icon={Gauge} title="Quality & usage" subtitle="Is AIMVA producing work people can publish without fixing it?"
        actions={<Tabs value={days} onChange={setDays} tabs={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }, { value: "90", label: "90 days" }]} />} />
      {loading || !m ? <ListSkeleton /> : (
        <div className="space-y-6">
          <StatStrip>
            <Stat label="First-time-right" value={fmt(w.first_time_right, "%")} sub={`of ${w.published} published pages went live with no edits`} tone="green" />
            <Stat label="Regenerates per page" value={fmt(w.regenerate_rate)} sub={`${w.manual_edits} manual HTML edits`} tone="amber" />
            <Stat label="Time to publish" value={w.median_minutes_to_publish === null ? "—" : `${w.median_minutes_to_publish}m`} sub="median, create → live" tone="blue" />
            <Stat label="Active users" value={m.users.active} sub={`${m.users.total} total · ${m.users.new} new`} tone="violet" />
          </StatStrip>

          <StatStrip>
            <Stat label="Pages created" value={w.created} sub={`${w.ai_written} written by AI`} tone="pink" />
            <Stat label="Images" value={m.images.generated} sub={`${m.images.ad_sets} ad sets made`} tone="violet" />
            <Stat label="Videos" value={m.videos.generated} sub={m.videos.generated ? `${fmt(m.videos.fail_rate, "%")} failed` : "none yet"} tone="cyan" />
            <Stat label="Feedback" value={Object.values(fb.by_kind).reduce((n, k) => n + k.up + k.down, 0)}
              sub={Object.entries(fb.by_kind).filter(([, k]) => k.up + k.down).map(([kind, k]) => `${kind}s ${k.up}👍 ${k.down}👎`).join(" · ") || "no ratings yet"} tone="slate" />
          </StatStrip>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <h2 className="mb-4 text-lg font-bold">Why results miss</h2>
              {fb.reasons.length === 0 ? <p className="text-sm text-muted">No thumbs-down in this period.</p> : (
                <div className="space-y-3">{fb.reasons.map((r) => <Bar key={r.reason} label={r.reason} value={r.count} max={maxReason} tone="bg-rose-400" />)}</div>
              )}
              {fb.recent_negative.length > 0 && (
                <ul className="mt-5 divide-y divide-line">
                  {fb.recent_negative.map((r, i) => (
                    <li key={i} className="flex gap-3 py-2.5 text-sm">
                      <ThumbsDown className="mt-0.5 size-3.5 shrink-0 text-rose-500" />
                      <span className="min-w-0"><b className="text-strong">{r.reason}</b> <span className="text-muted">on a {r.kind}{r.note ? `: “${r.note}”` : ""}</span>
                        <span className="block text-xs text-faint">{timeAgo(r.at)}</span></span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card>
              <h2 className="mb-4 text-lg font-bold">Providers & models</h2>
              {m.providers.length === 0 ? <p className="text-sm text-muted">No generations in this period.</p> : (
                <div className="space-y-3">
                  {m.providers.map((p) => (
                    <Bar key={p.name} label={`${p.name}${p.failed ? ` · ${p.failed} failed` : ""}`} value={p.images + p.videos} max={maxProv} />
                  ))}
                </div>
              )}
              <h2 className="mb-3 mt-7 text-lg font-bold">Most active users</h2>
              {m.top_users.length === 0 ? <p className="text-sm text-muted">Nobody has generated anything yet.</p> : (
                <ul className="divide-y divide-line text-sm">
                  {m.top_users.map((u) => (
                    <li key={u.email} className="flex justify-between py-2"><span className="truncate text-ink">{u.email}</span><span className="font-semibold text-strong">{u.generations}</span></li>
                  ))}
                </ul>
              )}
            </Card>
          </div>
          {user?.is_admin && <TemplateReview />}  {/* publishing templates to everyone stays with owners */}
          <p className="flex items-center gap-2 text-xs text-faint"><ThumbsUp className="size-3.5" /> First-time-right counts published pages with no HTML edit, regenerate or restore. Raise it by improving playbooks for the reasons above.</p>
        </div>
      )}
    </div>
  );
}
