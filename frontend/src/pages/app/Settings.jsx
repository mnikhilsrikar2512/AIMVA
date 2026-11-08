import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, Download, ExternalLink, KeyRound, Link2, Palette, Settings as SettingsIcon, Trash2, Unplug } from "lucide-react";
import { toast } from "sonner";
import { Button, Card, Chip, Field, Modal, PageHeader, Spinner, Tabs, ListSkeleton } from "../../components/ui";
import { LoadError } from "../../components/LoadError";
import { del, get, patch, post } from "../../lib/api";
import { useAuth, useIsClient } from "../../lib/auth";
import { useAction, useApi } from "../../lib/hooks";
import { useOnboarding } from "../../components/AppLayout";
// Owner-only, and its own chunk: customers never download the AI providers screen.
const ProvidersPanel = lazy(() => import("../../components/ProvidersPanel"));
import { TeamPanel } from "../../components/Team";
import { AgentSwitch } from "../../components/Agents";

function Profile() {
  const { user, setUser } = useAuth();
  const onboarding = useOnboarding();
  // In a client workspace "Company" is that client's business; your name stays yours either way.
  const ws = user.workspace;
  const canRename = !ws || ["owner", "admin"].includes(ws.role);
  const [f, setF] = useState({ name: user.name, company: ws ? ws.name : user.company });
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [busy, run] = useAction();
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <h2 className="mb-4 font-semibold text-strong">Profile</h2>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => { const d = await patch("/api/auth/profile", canRename ? f : { name: f.name }); setUser({ ...user, ...d.user, workspace: d.workspace || null }); }, "Profile updated"); }}>
          <Field label="Name"><input className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
          <Field label={ws ? "Business name (this client)" : "Company"}><input className="input" value={f.company} disabled={!canRename} onChange={(e) => setF({ ...f, company: e.target.value })} /></Field>
          <Field label="Email" hint="Verified"><input className="input opacity-60" value={user.email} disabled /></Field>
          <Button type="submit" busy={busy}>Save</Button>
        </form>
      </Card>
      <Card>
        <h2 className="mb-4 font-semibold text-strong">Change password</h2>
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); run(async () => { await post("/api/auth/change-password", pw); setPw({ current_password: "", new_password: "" }); }, "Password changed. Other sessions were signed out."); }}>
          <Field label="Current password"><input className="input" type="password" autoComplete="current-password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} required /></Field>
          <Field label="New password" hint="At least 8 characters with letters and numbers/symbols."><input className="input" type="password" autoComplete="new-password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} required /></Field>
          <Button type="submit" busy={busy}>Update password</Button>
        </form>
      </Card>
      <YourData />
      {onboarding?.data?.dismissed && (
        <Card className="flex items-center justify-between gap-4 lg:col-span-2">
          <div><p className="font-semibold text-strong">Setup guide</p><p className="text-sm text-muted">Bring back the step-by-step checklist on your dashboard.</p></div>
          <Button variant="ghost" onClick={() => run(async () => onboarding.setData(await post("/api/onboarding/dismiss", { dismissed: false })), "Setup guide restored")}>Show again</Button>
        </Card>
      )}
    </div>
  );
}

// DPDP: people can take their data with them and erase their account. Both work on the signed-in person, whatever
// workspace is active, so a view-only client can use them too.
function YourData() {
  const { setUser } = useAuth();
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState(null);
  const [f, setF] = useState({ password: "", confirm_email: "" });
  const [busy, run] = useAction();
  const start = () => run(async () => { setPreview(await get("/api/account/delete-preview")); setF({ password: "", confirm_email: "" }); setOpen(true); });
  const n = (c) => `${c.leads} leads, ${c.sites} pages, ${c.campaigns} campaigns`;
  return (
    <Card className="lg:col-span-2">
      <h2 className="mb-1 font-semibold text-strong">Your data</h2>
      <p className="mb-4 text-sm text-muted">Download everything AIMVA holds for your account and the client workspaces you own, or delete your account for good.</p>
      <div className="flex flex-wrap gap-3">
        <a className="btn-ghost" href="/api/account/export" download><Download className="size-4" /> Download my data</a>
        <Button variant="danger" busy={busy && !open} onClick={start}><Trash2 className="size-4" /> Delete account</Button>
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="Delete your account?">
        {preview && (
          <form className="space-y-4" onSubmit={(e) => {
            e.preventDefault();
            run(async () => { await post("/api/account/delete", f); setOpen(false); setUser(null); window.location.assign("/"); }, "Your account has been deleted");
          }}>
            <p className="text-sm text-muted">This can't be undone. Download your data first if you want a copy.</p>
            <ul className="list-disc space-y-1 pl-5 text-sm text-strong">
              <li>Your own business: {n(preview.own)}.</li>
              {preview.workspaces_deleted.map((w) => <li key={w.id}>Client workspace {w.name}: {n(w)}.</li>)}
              {preview.connected.length > 0 && <li>Connected accounts are disconnected ({preview.connected.length}).</li>}
              {preview.paid_plan && <li>Your paid plan is cancelled.</li>}
            </ul>
            {preview.workspaces_kept.length > 0 && <p className="text-sm text-muted">Kept, because someone else also owns them: {preview.workspaces_kept.map((w) => w.name).join(", ")}. You just lose access.</p>}
            <Field label={`Type ${preview.email} to confirm`}><input className="input" autoComplete="off" value={f.confirm_email} onChange={(e) => setF({ ...f, confirm_email: e.target.value })} required /></Field>
            <Field label="Password"><input className="input" type="password" autoComplete="current-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} required /></Field>
            <Button type="submit" busy={busy} disabled={f.confirm_email.trim().toLowerCase() !== preview.email.toLowerCase()} className="!bg-rose-600 hover:!bg-rose-700">Delete everything</Button>
          </form>
        )}
      </Modal>
    </Card>
  );
}

function Integrations() {
  const { data, loading, reload, error } = useApi("/api/integrations", []);
  const [keyFor, setKeyFor] = useState(null);
  const [values, setValues] = useState({});
  const [busy, run] = useAction();

  const connect = (i) => {
    if (i.type === "api_key") { setValues({}); setKeyFor(i); return; }
    run(async () => { window.location.href = (await get(`/api/integrations/${i.provider}/connect`)).url; });
  };

  if (loading) return <ListSkeleton />;
  if (error && !data.length) return <LoadError error={error} what="your connections" onRetry={reload} />;
  const groups = [
    ["Advertising & data", ["meta", "google", "linkedin", "microsoft"]],
    ["Messaging & voice", ["whatsapp", "twilio"]],
    ["AIMVA engines (owner only)", data.filter((i) => i.platform).map((i) => i.provider)],
    ["Hosting", ["netlify", "vercel", "cloudflare", "github"]],
  ];
  return (
    <div className="space-y-8">
      {groups.filter(([, keys]) => data.some((i) => keys.includes(i.provider))).map(([title, keys]) => (
        <section key={title}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-faint">{title}</h2>
          <div className="card divide-y divide-line px-5 sm:px-6">
            {data.filter((i) => keys.includes(i.provider)).map((i) => (
              <div key={i.provider} className="flex items-center justify-between gap-4 py-4">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-strong">{i.label}</p>
                    {i.connected && <CheckCircle2 className="size-4 text-emerald-600" />}
                  </div>
                  <p className="mt-0.5 text-xs text-muted">
                    {i.connected ? `Connected${i.meta?.phone_number_id ? ` · number ${i.meta.phone_number_id}` : ""}` :
                      i.app_configured ? (i.type === "oauth" ? "Sign in with OAuth" : "Paste an API key") :
                        <span className="text-amber-600/80">Not available yet</span>}
                  </p>
                  <a href={i.docs} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs text-brand-2 hover:underline">Setup guide <ExternalLink className="size-3" /></a>
                </div>
                {i.connected ? (
                  <Button variant="ghost" size="sm" onClick={() => confirm(`Disconnect ${i.label}?`) && run(async () => { await del(`/api/integrations/${i.provider}`); reload(); }, "Disconnected")}>
                    <Unplug className="size-3.5" /> Disconnect
                  </Button>
                ) : (
                  <Button size="sm" disabled={!i.app_configured} onClick={() => connect(i)}>
                    {i.type === "oauth" ? <Link2 className="size-3.5" /> : <KeyRound className="size-3.5" />} Connect
                  </Button>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}
      <Modal open={!!keyFor} onClose={() => setKeyFor(null)} title={`Connect ${keyFor?.label}`}>
        <form className="space-y-4" onSubmit={(e) => {
          e.preventDefault();
          run(async () => { await post(`/api/integrations/${keyFor.provider}/key`, { values }); setKeyFor(null); reload(); }, "Connected");
        }}>
          {keyFor?.fields.map((f) => (
            <Field key={f} label={f.replace(/_/g, " ")} hint={keyFor.hints?.[f]}>
              <input className="input font-mono" type={/token|key|secret/.test(f) ? "password" : "text"} autoComplete="off"
                value={values[f] || ""} onChange={(e) => setValues({ ...values, [f]: e.target.value })} required />
            </Field>
          ))}
          <p className="text-xs text-faint">Keys are encrypted at rest on your AIMVA server and never sent back to the browser.</p>
          <Button type="submit" busy={busy}>Save & connect</Button>
        </form>
      </Modal>
    </div>
  );
}

export default function Settings() {
  const [params, setParams] = useSearchParams();
  const { user } = useAuth();
  const owner = !!user?.is_admin;  // AI providers are the platform owner's business, not the customer's
  const isClient = useIsClient();   // view-only clients don't manage connected accounts
  const tab = (params.get("tab") === "providers" && !owner ? "profile" : params.get("tab")) || "profile";
  useEffect(() => {
    if (params.get("connected")) toast.success(`${params.get("connected")} connected`);
    if (params.get("error")) toast.error(`Connection failed: ${params.get("error")}`);
  }, [params]);
  return (
    <div>
      <PageHeader icon={SettingsIcon} tone="slate" title="Settings" subtitle="Your profile, team and connected accounts."
        actions={<Link to="/app/brand" className="btn-ghost"><Palette className="size-4" /> Brand kit</Link>} />
      <div className="mb-6"><Tabs value={tab} onChange={(v) => setParams({ tab: v })} tabs={[{ value: "profile", label: "Profile" }, { value: "team", label: "Team" }, ...(isClient ? [] : [{ value: "integrations", label: "Accounts" }]), ...(owner ? [{ value: "providers", label: "AI providers" }] : [])]} /></div>
      {tab === "profile" && !isClient && <div className="mb-6"><AgentSwitch kind="lead_alerts" title="Lead alerts" text="Email me the moment a new lead arrives, with a one-tap WhatsApp reply." /></div>}
      {tab === "profile" ? <Profile /> : tab === "team" ? <TeamPanel /> : tab === "providers" ? <Suspense fallback={<ListSkeleton />}><ProvidersPanel /></Suspense> : isClient ? <Profile /> : <Integrations />}
      <p className="mt-10 flex items-center gap-2 text-xs text-faint"><Chip>v1.0</Chip> AIMVA</p>
    </div>
  );
}
