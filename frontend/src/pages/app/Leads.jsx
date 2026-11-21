import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { BadgeCheck, Download, FileSpreadsheet, MessageCircle, Phone, Plus, RefreshCw, Search, Users, Cloud } from "lucide-react";
import { Button, Chip, Empty, Field, Modal, PageHeader, Spinner, cx, ListSkeleton, IconButton } from "../../components/ui";
import { LoadError, LoadErrorBar } from "../../components/LoadError";
import { AgentSwitch } from "../../components/Agents";
import { del, patch, post } from "../../lib/api";
import { timeAgo, useAction, useApi } from "../../lib/hooks";
import { SOURCE_TONE } from "./Dashboard";
import LeadPanel from "../../components/LeadPanel";
import { DownloadMenu } from "../../components/DownloadMenu";
import { useLeadEvents } from "../../lib/live";
import { useAuth, useIsClient } from "../../lib/auth";
import { StoryLine } from "../../components/Story";

const STAGES = ["new", "contacted", "qualified", "won", "lost"];
const STAGE_LABEL = { new: "New", contacted: "Contacted", qualified: "Qualified", won: "Won", lost: "Lost" };
const SORT_KEY = "aimva:leads-sort";
const FILTER = "h-8 rounded-md bg-transparent px-2 text-sm text-ink hover:bg-surface-2 focus:bg-surface-2 focus:outline-none";
const readSort = () => { try { return localStorage.getItem(SORT_KEY) || "needs"; } catch { return "needs"; } };

/** Whether the automatic WhatsApp welcome really reached them. Silent when there was none to send. */
function WelcomeNote({ w }) {
  if (!w) return null;
  const ok = { sent: "Welcome sent", delivered: "Welcome delivered", read: "Welcome read" }[w.status];
  if (ok) return <span title="Lead Concierge sent this on WhatsApp">· {ok}</span>;
  return <span className="font-semibold text-warm" title={w.note || "Open the lead to send it yourself"}>· Welcome not sent{w.note ? `: ${w.note}` : ""}</span>;
}

/** "Waiting 14m": how long a lead has been waiting on the business. */
export const waited = (iso) => {
  const t = timeAgo(iso);
  return t === "just now" ? "Waiting, just now" : `Waiting ${t.replace(" ago", "")}`;
};

function SyncPanel() {
  const { data: integrations, reload, error: integError } = useApi("/api/integrations", []);
  const [busy, run] = useAction();
  const google = integrations.find((i) => i.provider === "google");
  const ms = integrations.find((i) => i.provider === "microsoft");
  const [sheet, setSheet] = useState("");

  const Target = ({ integ, icon: Icon, title, target, children }) => (
    <div className="rounded-2xl bg-surface-2/60 p-4">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2.5"><Icon className="size-5 text-warm" /><p className="font-semibold text-strong">{title}</p></div>
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
  const [source, setSource] = useState(() => new URLSearchParams(window.location.search).get("source") || "");  // other screens link to "their" leads
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
      <PageHeader title="Leads"
        subtitle={waiting ? (isClient ? `${waiting} ${waiting === 1 ? "lead is" : "leads are"} waiting for a reply. They're at the top.` : `${waiting} ${waiting === 1 ? "lead is" : "leads are"} waiting on you. They're at the top.`) : "Everyone who asked, from every channel, scored and in one list."}
        actions={<>
          <DownloadMenu name="Leads" disabled={loading || !leads.length} reason={loading ? "Loading leads…" : q || source || stage ? "No leads match these filters" : undefined} csvHref="/api/leads/export.csv"
            excel={() => [{ name: "Leads", columns: LEAD_COLS, rows: leads }]}
            pdf={async (filename) => (await import("../../lib/reports/leads")).leadsReport({ leads, business, filters: { q, source, stage }, filename })} />
          {!isClient && <Button onClick={() => setAdding(true)}><Plus className="size-4" /> Add lead</Button>}
        </>} />
      <StoryLine module="leads" className="sm:-mt-6" />
      {!isClient && <div className="mb-6">
        <AgentSwitch kind="concierge" title="Lead Concierge"
          text="Welcomes every new lead on WhatsApp within seconds, then follows up on day 2 and day 7 until they reply." />
      </div>}
      {/* After Attio: one edge-to-edge table, no card around it; the row opens the drawer, which has its own URL. */}
      <div className="-mx-4 sm:-mx-6 lg:-mx-8">
        <div className="flex flex-wrap items-center gap-2 border-y border-line px-4 py-2 sm:px-6 lg:px-8">
          <div className="relative min-w-[12rem] flex-1">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-faint" />
            <input className="h-8 w-full rounded-md bg-transparent pl-8 pr-2 text-sm text-strong placeholder:text-muted focus:bg-surface-2 focus:outline-none" aria-label="Search leads" placeholder="Search name, email, phone" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <select className={FILTER} aria-label="Filter by source" value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">All sources</option>
            {Object.keys(SOURCE_TONE).map((s) => <option key={s}>{s}</option>)}
          </select>
          <select className={FILTER} aria-label="Filter by status" value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="">Any status</option>
            {STAGES.map((s) => <option key={s} value={s}>{STAGE_LABEL[s]}</option>)}
          </select>
          <select className={FILTER} aria-label="Order" value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="needs">Waiting first</option>
            <option value="newest">Newest first</option>
          </select>
        </div>
        {!loading && error && leads.length > 0 && <LoadErrorBar what="the latest leads" onRetry={reload} />}
        {loading ? <div className="px-4 sm:px-6 lg:px-8"><ListSkeleton /></div> : error && leads.length === 0 ? (
          <div className="px-4 sm:px-6 lg:px-8"><LoadError error={error} what="your leads" onRetry={reload} /></div>
        ) : leads.length === 0 ? (
          (q || source || stage) ? (
            <Empty filtered icon={Users} title="No leads match" text="Try fewer words, or clear the filters."
              action={<Button variant="ghost" onClick={() => { setQ(""); setSource(""); setStage(""); }}>Clear filters</Button>} />
          ) : (
            <Empty className="px-4 sm:px-6 lg:px-8" icon={Users} title="Your leads will land here" text="Everyone who fills your page form, answers an ad form, messages on WhatsApp or talks to your call assistant shows up here, ready to call."
              action={<Link to="/app/websites" className="btn-primary">Make a page with a lead form</Link>}
              secondary={<Button variant="ghost" onClick={() => setAdding(true)}><Plus className="size-4" /> Add one yourself</Button>} />
          )
        ) : (
          <>
            <table className="w-full table-fixed text-sm">
              <thead className="hidden bg-surface-2 text-left text-xs font-medium text-muted md:table-header-group">
                <tr className="h-8 border-b border-line">
                  <th scope="col" className="w-[22%] pl-4 font-medium sm:pl-6 lg:pl-8">Name</th>
                  <th scope="col" className="w-[11%] font-medium">Source</th>
                  <th scope="col" className="hidden w-[10%] font-medium lg:table-cell">Language</th>
                  <th scope="col" className="w-[13%] font-medium">Status</th>
                  <th scope="col" className="font-medium">Last message</th>
                  {!isClient && <th scope="col" className="w-[112px] pr-4 sm:pr-6 lg:pr-8"><span className="sr-only">Actions</span></th>}
                </tr>
              </thead>
              <tbody>
                {leads.map((l) => (
                  <tr key={l.id} onClick={() => openLead(l.id)}
                    className={cx("group flex cursor-pointer flex-wrap items-center gap-x-2 border-b border-line px-4 py-2 hover:bg-surface-2/60 md:table-row md:h-10 md:p-0", openId === l.id && "bg-accent-soft/60 hover:bg-accent-soft/60", fresh.has(l.id) && "bg-accent-soft/40")}>
                    <td className="min-w-0 flex-1 truncate md:pl-4 sm:md:pl-6 lg:pl-8">
                      <button type="button" className="max-w-full truncate text-left font-medium text-strong hover:underline" onClick={(e) => { e.stopPropagation(); openLead(l.id); }}>{l.name || l.email || l.phone || "—"}</button>
                      {l.needs_reply && <span className="ml-2 hidden text-xs font-medium text-warm md:inline" title="Nobody has answered them yet">{waited(l.waiting_since)}</span>}
                      {l.opted_out && <span className="ml-2 text-xs font-medium text-danger" title="They replied STOP: no WhatsApp or calls">Opted out</span>}
                    </td>
                    <td className="hidden truncate text-ink md:table-cell">{l.source}</td>
                    <td className="hidden truncate text-ink lg:table-cell">{l.language_name || (l.language === "en" ? "English" : "")}</td>
                    <td className="hidden truncate md:table-cell">
                      <span className={cx(l.stage === "won" ? "font-medium text-brand" : "text-ink")}>{STAGE_LABEL[l.stage] || l.stage}{l.stage === "won" && l.value ? ` · ₹${Number(l.value).toLocaleString("en-IN")}` : ""}</span>
                      {l.score >= 70 && l.stage === "new" && <span className="ml-1.5 text-xs font-medium text-warm">hot</span>}
                    </td>
                    <td className="order-3 w-full truncate text-xs text-muted md:order-none md:w-auto md:text-sm md:text-ink">
                      <span className="md:hidden">{l.needs_reply ? <span className="font-medium text-warm">{waited(l.waiting_since)}</span> : STAGE_LABEL[l.stage] || l.stage} · {l.source} · </span>
                      {l.message || <span className="text-muted">No message</span>}
                      <span className="ml-2 text-xs text-muted">{timeAgo(l.created_at)}</span>
                      <span className="ml-1 text-xs text-muted"><WelcomeNote w={l.welcome} /></span>
                    </td>
                    {!isClient && (
                      <td className="order-2 md:order-none md:pr-4 sm:md:pr-6 lg:pr-8" onClick={(e) => e.stopPropagation()}>
                        <span className="flex items-center justify-end gap-0.5">
                          {/* Icons only; a lead who is waiting gets the reply icon in brand colour. */}
                          {l.phone && !l.opted_out && (
                            <IconButton label={l.needs_reply ? `Reply on WhatsApp${l.language_name ? ` in ${l.language_name}` : ""}` : "Message on WhatsApp"}
                              className={cx(l.needs_reply && "!text-brand")} onClick={() => openLead(l.id, true)}><MessageCircle className="size-4" strokeWidth={l.needs_reply ? 2.4 : 2} /></IconButton>)}
                          {l.phone && !l.opted_out && <IconButton label={`Call ${l.name || "them"}`} href={`tel:${l.phone}`}><Phone className="size-4" /></IconButton>}
                          {!["won", "lost"].includes(l.stage) ? <IconButton label="They bought: mark as won" onClick={() => { update(l.id, { stage: "won" }); openLead(l.id); }}><BadgeCheck className="size-4" /></IconButton>
                            : <span aria-hidden className="w-8" />}
                        </span>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="px-4 py-3 text-xs text-muted sm:px-6 lg:px-8">{leads.length} {leads.length === 1 ? "lead" : "leads"}{waiting ? ` · ${waiting} waiting` : ""}</p>
          </>
        )}
      </div>
      {!isClient && (
        <section className="mt-12 max-w-3xl">
          <h2 className="mb-3 text-base font-semibold text-strong">Send leads somewhere else too</h2>
          <SyncPanel />
        </section>
      )}
      {openId && <LeadPanel leadId={openId} startReply={replying} onClose={closeLead} onChanged={reload} onDelete={(l) => { closeLead(); removeLead(l); }}
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
