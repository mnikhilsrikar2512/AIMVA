import { useState } from "react";
import { motion } from "framer-motion";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Download, FileSpreadsheet, MessageCircle, Plus, RefreshCw, Search, Trash2, Users, Cloud } from "lucide-react";
import { Button, Card, Chip, Empty, Field, Modal, PageHeader, Spinner, TONES, cx, ListSkeleton, IconButton } from "../../components/ui";
import { LoadError, LoadErrorBar } from "../../components/LoadError";
import { AgentSwitch } from "../../components/Agents";
import { del, patch, post } from "../../lib/api";
import { timeAgo, useAction, useApi } from "../../lib/hooks";
import { SOURCE_TONE } from "./Dashboard";
import LeadPanel from "../../components/LeadPanel";
import { DownloadMenu } from "../../components/DownloadMenu";
import { useLeadEvents } from "../../lib/live";
import { useAuth, useIsClient } from "../../lib/auth";

const STAGES = ["new", "contacted", "qualified", "won", "lost"];
const STAGE_TONE = { new: "blue", contacted: "violet", qualified: "amber", won: "green", lost: "rose" };
const SORT_KEY = "aimva:leads-sort";
const readSort = () => { try { return localStorage.getItem(SORT_KEY) || "needs"; } catch { return "needs"; } };

/** "Waiting 14m": how long a lead has been waiting on the business. */
export const waited = (iso) => {
  const t = timeAgo(iso);
  return t === "just now" ? "Waiting, just now" : `Waiting ${t.replace(" ago", "")}`;
};

function ScoreBar({ score }) {
  const c = score >= 70 ? "bg-emerald-400" : score >= 40 ? "bg-amber-400" : "bg-slate-500";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 overflow-hidden rounded-full bg-ink/[0.06]"><motion.div className={cx("h-full rounded-full", c)} initial={{ width: 0 }} animate={{ width: `${score}%` }} transition={{ type: "spring", stiffness: 200, damping: 26 }} /></div>
      <span className="w-6 text-xs font-semibold text-strong">{score}</span>
    </div>
  );
}

function SyncPanel() {
  const { data: integrations, reload, error: integError } = useApi("/api/integrations", []);
  const [busy, run] = useAction();
  const google = integrations.find((i) => i.provider === "google");
  const ms = integrations.find((i) => i.provider === "microsoft");
  const [sheet, setSheet] = useState("");

  const Target = ({ integ, icon: Icon, title, target, children }) => (
    <div className="rounded-2xl bg-surface-2/60 p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5"><Icon className="size-5 text-amber-600" /><p className="font-semibold text-strong">{title}</p></div>
        {integ?.connected ? <Chip tone="green">Connected</Chip> : <Link to="/app/settings?tab=integrations" className="btn-ghost btn-sm">Connect</Link>}
      </div>
      {integ?.connected && (
        <div className="mt-3 space-y-3">
          {children}
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm text-muted">
              <input type="checkbox" className="accent-amber-400" checked={!!integ.meta?.auto_sync}
                onChange={(e) => run(async () => { await patch(`/api/integrations/${integ.provider}/meta`, { meta: { auto_sync: e.target.checked } }); reload(); })} />
              Auto-sync new leads
            </label>
            <IconButton label="Sync now" busy={busy} onClick={() => run(async () => { const r = await post(`/api/leads/sync/${target}`); return r; }, "Synced")}><RefreshCw className="size-4" /></IconButton>
          </div>
        </div>
      )}
    </div>
  );

  if (integError) return <LoadErrorBar what="your connections" onRetry={reload} />;
  return (
    <div className="space-y-3">
      <Target integ={google} icon={FileSpreadsheet} title="Google Sheets" target="google">
        <div className="flex gap-2">
          <input className="input" placeholder={google?.meta?.sheet_id || "Spreadsheet ID from the sheet URL"} value={sheet} onChange={(e) => setSheet(e.target.value)} />
          <Button size="sm" variant="ghost" className="h-10" disabled={!sheet} onClick={() => run(async () => { await patch("/api/integrations/google/meta", { meta: { sheet_id: sheet.trim() } }); setSheet(""); reload(); }, "Sheet saved")}>Save</Button>
        </div>
      </Target>
      <Target integ={ms} icon={Cloud} title="Microsoft OneDrive" target="onedrive">
        <p className="text-xs text-muted">Writes <code className="text-ink">/AIMVA/leads.csv</code> in your OneDrive.</p>
      </Target>
    </div>
  );
}

const LEAD_COLS = [
  { key: "name", label: "Name" }, { key: "phone", label: "Phone" }, { key: "email", label: "Email" }, { key: "source", label: "Source" },
  { key: "stage", label: "Stage" }, { key: "score", label: "Score" }, { key: "value", label: "Value (₹)" },
  { key: "created_at", label: "Arrived", get: (l) => (l.created_at || "").replace("T", " ").slice(0, 16) }, { key: "message", label: "Message" },
];

export default function Leads() {
  const { user } = useAuth();
  const isClient = useIsClient();  // view-only clients don't manage sync destinations
  const business = user?.workspace?.name || user?.company || user?.name || "";
  const [q, setQ] = useState("");
  const [source, setSource] = useState("");
  const [stage, setStage] = useState("");
  const [sort, setSortState] = useState(readSort);
  const setSort = (v) => { setSortState(v); try { localStorage.setItem(SORT_KEY, v); } catch { /* private mode */ } };
  const { data: leads, setData, loading, reload, error } = useApi(`/api/leads?q=${encodeURIComponent(q)}&source=${source}&stage=${stage}&sort=${sort}`, []);
  const waiting = leads.filter((l) => l.needs_reply).length;
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", phone: "", message: "" });
  const [busy, run] = useAction();
  const [fresh, setFresh] = useState(() => new Set());
  useLeadEvents((d) => {
    reload();
    if (d.type !== "created") return;
    setFresh((s) => new Set(s).add(d.lead.id));
    setTimeout(() => setFresh((s) => { const n = new Set(s); n.delete(d.lead.id); return n; }), 6000);
  });
  const [params, setParams] = useSearchParams();
  const openId = Number(params.get("lead")) || null;
  const replying = params.get("reply") === "1";
  // J/K walk the list in the order it had when the panel opened, so replying (which re-sorts the list) doesn't skip anyone.
  const [navIds, setNavIds] = useState([]);
  const openLead = (id, reply = false, keepOrder = false) => {
    if (!keepOrder) setNavIds(leads.map((l) => l.id));
    setParams((p) => { const n = new URLSearchParams(p); n.set("lead", id); reply ? n.set("reply", "1") : n.delete("reply"); return n; });
  };
  const closeLead = () => setParams((p) => { const n = new URLSearchParams(p); n.delete("lead"); n.delete("reply"); return n; });
  // Delete with Undo instead of a confirm box: the row goes at once, the server delete waits 5 seconds.
  const removeLead = (l) => {
    setData((all) => all.filter((x) => x.id !== l.id));
    let undone = false;
    const t = setTimeout(() => { if (!undone) del(`/api/leads/${l.id}`).catch((e) => { toast.error(e.message); reload(); }); }, 5000);
    toast(`${l.name || "Lead"} deleted.`, { duration: 5000, action: { label: "Undo", onClick: () => { undone = true; clearTimeout(t); reload(); } } });
  };
  const update = (id, body) => run(async () => { const l = await patch(`/api/leads/${id}`, body); setData((all) => all.map((x) => (x.id === id ? l : x))); });

  return (
    <div>
      <PageHeader icon={Users} tone="amber" title="Leads"
        subtitle={waiting ? (isClient ? `${waiting} ${waiting === 1 ? "lead is" : "leads are"} waiting for a reply. They're at the top.` : `${waiting} ${waiting === 1 ? "lead is" : "leads are"} waiting on you. They're at the top.`) : "Everyone who asked, from every channel, scored and in one list."}
        actions={<>
          <DownloadMenu name="Leads" disabled={loading || !leads.length} reason={loading ? "Loading leads…" : q || source || stage ? "No leads match these filters" : undefined} csvHref="/api/leads/export.csv"
            excel={() => [{ name: "Leads", columns: LEAD_COLS, rows: leads }]}
            pdf={async (filename) => (await import("../../lib/reports/leads")).leadsReport({ leads, business, filters: { q, source, stage }, filename })} />
          {!isClient && <Button onClick={() => setAdding(true)}><Plus className="size-4" /> Add lead</Button>}
        </>} />
      {!isClient && <div className="mb-6">
        <AgentSwitch kind="concierge" title="Lead Concierge"
          text="Welcomes every new lead on WhatsApp within seconds, then follows up on day 2 and day 7 until they reply." />
      </div>}
      <div className="grid gap-6 2xl:grid-cols-[1fr_340px]">{/* laptops: the full table, sync below it */}
        <Card className="min-w-0 p-0 sm:p-0">
          <div className="grid grid-cols-2 gap-2 border-b border-line p-4 sm:flex sm:flex-row">
            <div className="relative col-span-2 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" />
              <input className="input pl-9" aria-label="Search leads" placeholder="Search name, email, phone" value={q} onChange={(e) => setQ(e.target.value)} />
            </div>
            <select className="input sm:w-36" aria-label="Filter by source" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">All sources</option>
              {Object.keys(SOURCE_TONE).map((s) => <option key={s}>{s}</option>)}
            </select>
            <select className="input sm:w-36" aria-label="Filter by stage" value={stage} onChange={(e) => setStage(e.target.value)}>
              <option value="">All stages</option>
              {STAGES.map((s) => <option key={s}>{s}</option>)}
            </select>
            <select className="input col-span-2 sm:w-40" aria-label="Order" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="needs">Waiting first</option>
              <option value="newest">Newest first</option>
            </select>
          </div>
          {!loading && error && leads.length > 0 && <LoadErrorBar what="the latest leads" onRetry={reload} />}
          {loading ? <ListSkeleton /> : error && leads.length === 0 ? (
            <LoadError error={error} what="your leads" onRetry={reload} />
          ) : leads.length === 0 ? (
            (q || source || stage) ? (
              <Empty filtered icon={Users} title="No leads match" text="Try fewer words, or clear the filters."
                action={<Button variant="ghost" onClick={() => { setQ(""); setSource(""); setStage(""); }}>Clear filters</Button>} />
            ) : (
              <Empty icon={Users} title="Your leads will land here" text="Everyone who fills your page form, answers an ad form, messages on WhatsApp or talks to your call assistant shows up here, scored and ready to call."
                action={<Link to="/app/websites" className="btn-primary">Make a page with a lead form</Link>}
                secondary={<Button variant="ghost" onClick={() => setAdding(true)}><Plus className="size-4" /> Add one yourself</Button>} />
            )
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm lg:min-w-[760px]">
                <thead className="text-left text-xs uppercase tracking-wide text-faint">
                  <tr className="border-b border-line">
                    <th className="px-3 py-3 font-medium sm:px-4">Lead</th><th className="hidden px-4 py-3 font-medium lg:table-cell">Source</th><th className="hidden px-4 py-3 font-medium sm:table-cell">Score</th>
                    <th className="px-3 py-3 font-medium sm:px-4">Stage</th><th className="hidden px-4 py-3 font-medium lg:table-cell">Value</th><th className="hidden px-4 py-3 font-medium lg:table-cell">Added</th><th><span className="sr-only">Actions</span></th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((l) => (
                    <motion.tr key={l.id} initial={fresh.has(l.id) ? { opacity: 0, x: -24 } : false} animate={{ opacity: 1, x: 0 }} transition={{ type: "spring", stiffness: 260, damping: 26 }} className={cx("border-b border-line align-top last:border-0 hover:bg-ink/[0.02]", openId === l.id && "bg-ink/[0.04]", fresh.has(l.id) && "animate-[flash_2s_ease-out]")}>
                      <td className="max-w-[190px] px-3 py-3 sm:max-w-[260px] sm:px-4">
                        <button className="text-left font-semibold text-strong hover:text-brand-2 hover:underline" onClick={() => openLead(l.id)}>{l.name || l.email || l.phone || "—"}</button>
                        {fresh.has(l.id) && <span className="ml-2 rounded-full bg-emerald-500/20 px-1.5 py-0.5 text-xs font-bold uppercase text-emerald-600">New</span>}
                        {(l.needs_reply || (l.language && l.language !== "en")) && (
                          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs">
                            {l.needs_reply && <span className="font-semibold text-warm" title="Nobody has answered them yet">{waited(l.waiting_since)}</span>}
                            {l.language && l.language !== "en" && <span className="text-muted" title="They write in this language; replies are drafted in it">{l.language_name}</span>}
                          </p>
                        )}
                        <p className="truncate text-xs text-muted">{[l.email, l.phone].filter(Boolean).join(" · ")}</p>
                        {l.message && <p className="mt-1 line-clamp-2 text-xs text-faint">{l.message}</p>}
                        {/* Small screens: the hidden columns' facts, in one line under the name. */}
                        <p className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted lg:hidden">
                          <Chip tone={SOURCE_TONE[l.source] || "slate"}>{l.source}</Chip>
                          <span className="sm:hidden">Score {l.score}</span>
                          <span>· {timeAgo(l.created_at)}</span>
                        </p>
                      </td>
                      <td className="hidden px-4 py-3 lg:table-cell"><Chip tone={SOURCE_TONE[l.source] || "slate"}>{l.source}</Chip></td>
                      <td className="hidden px-4 py-3 sm:table-cell"><ScoreBar score={l.score} /></td>
                      <td className="px-3 py-3 sm:px-4">
                        {isClient ? <Chip tone={STAGE_TONE[l.stage]}>{l.stage}</Chip> : <select aria-label={`Stage for ${l.name || l.email || "lead"}`} className={cx("chip cursor-pointer", TONES[STAGE_TONE[l.stage]].chip)} value={l.stage} onChange={(e) => update(l.id, { stage: e.target.value })}>
                          {STAGES.map((s) => <option key={s} value={s} className="bg-surface">{s}</option>)}
                        </select>}
                      </td>
                      <td className="hidden px-4 py-3 lg:table-cell">
                        {isClient ? <span className="text-xs text-ink">{l.value ? `₹${Number(l.value).toLocaleString("en-IN")}` : "—"}</span>
                          : <input type="number" min="0" defaultValue={l.value || ""} placeholder="0" className="input h-8 w-24 text-xs"
                          onBlur={(e) => Number(e.target.value) !== l.value && update(l.id, { value: Number(e.target.value) || 0 })} />}
                      </td>
                      <td className="hidden px-4 py-3 text-xs text-faint lg:table-cell">{timeAgo(l.created_at)}
                        {Object.keys(l.synced).length > 0 && <p className="mt-1 text-emerald-600/80">synced</p>}
                      </td>
                      <td className="px-2 py-3 sm:px-4">
                        <div className="flex items-center justify-end gap-1">
                          {l.phone && !isClient && (l.needs_reply
                            ? <Button size="sm" className="px-2 sm:px-3" aria-label="Reply" onClick={() => openLead(l.id, true)} title={`Reply on WhatsApp${l.language_name ? ` in ${l.language_name}` : ""}`}><MessageCircle className="size-3.5" /><span className="hidden sm:inline">Reply</span></Button>
                            : <IconButton label="Message on WhatsApp" onClick={() => openLead(l.id, true)}><MessageCircle className="size-4" /></IconButton>)}
                          {!isClient && <IconButton danger label="Delete lead" onClick={() => removeLead(l)}><Trash2 className="size-4" /></IconButton>}
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
        <div>
          {!isClient && <><h2 className="mb-3 font-semibold text-strong">Sync destinations</h2>
          <SyncPanel /></>}
        </div>
      </div>
      {openId && <LeadPanel leadId={openId} startReply={replying} onClose={closeLead} onChanged={reload}
        ids={navIds.length ? navIds : leads.map((l) => l.id)} onNavigate={(id, reply) => openLead(id, reply, true)} />}
      <Modal open={adding} onClose={() => setAdding(false)} title="Add lead">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => { await post("/api/leads", form); setAdding(false); setForm({ name: "", email: "", phone: "", message: "" }); reload(); }, "Lead added"); }}>
          <Field label="Name"><input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Email"><input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
            <Field label="Phone"><input className="input" type="tel" inputMode="tel" autoComplete="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} /></Field>
          </div>
          <Field label="Notes"><textarea className="input" rows={3} value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} /></Field>
          <Button type="submit" busy={busy}>Add lead</Button>
        </form>
      </Modal>
    </div>
  );
}
