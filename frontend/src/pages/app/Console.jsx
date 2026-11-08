import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Search, ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button, Chip, Empty, Field, IconButton, ListSkeleton, Modal, Notice, PageHeader, Spinner, Tabs, cx } from "../../components/ui";
import { get, post } from "../../lib/api";
import { parseServerDate, useApi } from "../../lib/hooks";

/* The AIMVA team console (docs/CONSOLE_DESIGN.md). What a role may do comes from /api/console/me;
   the server checks every action again, so a hidden button is never the only guard. */

const ago = (iso) => {
  if (!iso) return "—";
  const d = parseServerDate(iso), s = (Date.now() - d.getTime()) / 1000;
  if (s < 60) return "now";
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  if (s < 7 * 86400) return `${Math.floor(s / 86400)}d`;
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
};
const day = (iso) => (iso ? parseServerDate(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" }) : "—");
const inr = (n) => `₹${Number(n).toLocaleString("en-IN")}`;

const STATUS = {
  new: ["New", "text-muted"], trialing: ["Trial", "text-muted"], active: ["Active", "text-strong"],
  past_due: ["Past due", "text-warm"], expired: ["Expired", "text-warm"], cancelled: ["Cancelled", "text-muted"],
};
const ROLE_LABEL = { owner: "Owner", manager: "Management", developer: "Development", support: "Support" };
const METER_LABEL = { images: "pictures", videos: "videos", voice_minutes: "call minutes", ai_actions: "AI writing runs", sites: "pages" };

function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => { const t = setTimeout(() => setV(value), ms); return () => clearTimeout(t); }, [value, ms]);
  return v;
}

/** One staff log line in plain words. */
function describe(a) {
  const d = a.detail || {}, who = a.target || "";
  switch (a.action) {
    case "customer.view": return ["opened", who];
    case "credits.grant": return [`granted ${d.quantity} ${METER_LABEL[d.meter] || d.meter} to`, who];
    case "plan.change": return [`moved the plan from ${d.from} to ${d.to} for`, who];
    case "signin.unlock": return ["unlocked sign-in for", who];
    case "signin.revoke": return ["signed out everywhere", who];
    case "team.add": return [`added ${d.email} as`, ROLE_LABEL[d.role] || d.role];
    case "team.role": return [`changed ${d.email} from ${ROLE_LABEL[d.from] || d.from} to`, ROLE_LABEL[d.to] || d.to];
    case "team.remove": return [`removed ${d.email} from the team`, ""];
    case "template.publish": return ["published the template", d.name];
    case "template.dismiss": return ["dismissed the template", d.name];
    default: return [a.action, who];
  }
}

function LogRow({ a, onOpen }) {
  const [what, target] = describe(a);
  return (
    <li className="flex gap-3 py-3">
      <span className="w-11 shrink-0 pt-0.5 text-xs text-faint">{ago(a.at)}</span>
      <span className="min-w-0 flex-1 text-sm">
        <b className="font-semibold text-strong">{a.actor}</b> <span className="text-xs text-faint">{ROLE_LABEL[a.actor_role] || a.actor_role}</span>{" "}
        {what}{" "}
        {target && (a.target_id && onOpen
          ? <button type="button" className="font-medium text-brand hover:underline" onClick={() => onOpen(a.target_id)}>{target}</button>
          : <span className="font-medium text-strong">{target}</span>)}
        {a.reason && <span className="mt-0.5 block text-[13px] text-muted">“{a.reason}”</span>}
      </span>
    </li>
  );
}

// ---- action dialog -----------------------------------------------------------------------------------------------
function ActionDialog({ kind, customer, me, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [meter, setMeter] = useState("images");
  const [quantity, setQuantity] = useState(10);
  const [days, setDays] = useState(14);
  const [plan, setPlan] = useState(customer?.billing?.plan === "trial" ? "starter" : customer?.billing?.plan || "starter");
  const [busy, setBusy] = useState(false);
  const capped = !me.permissions.includes("credits.grant_any");
  const p = customer?.profile || {};
  const name = p.name || p.email;

  const SPEC = {
    credits: { title: `Grant credits to ${name}`, sub: "Extra units on top of their plan, used up before the plan's own.", button: "Grant" },
    plan: { title: `Change ${name}'s plan`, sub: "Invoiced by you, no card needed. Starts a fresh 30-day period now.", button: "Change plan" },
    unlock: { title: "Unlock sign-in", sub: `They can try their password again now. ${p.failed_logins || 0} wrong tries so far.`, button: "Unlock" },
    "sign-out": { title: "Sign out everywhere", sub: "Every session they have ends. They sign in again with their password.", button: "Sign out everywhere" },
  };
  const s = SPEC[kind];
  if (!s) return null;
  const ok = reason.trim().length >= 5 && (kind !== "credits" || (quantity > 0 && days > 0));

  const submit = async (e) => {
    e.preventDefault();
    if (!ok) return;
    setBusy(true);
    try {
      const body = { reason: reason.trim(), ...(kind === "credits" ? { meter, quantity: Number(quantity), days: Number(days) } : {}), ...(kind === "plan" ? { plan } : {}) };
      const out = await post(`/api/console/customers/${p.id}/${kind}`, body);
      toast.success(kind === "credits" ? `Granted ${quantity} ${METER_LABEL[meter]} to ${name}.` : kind === "plan" ? `${name} is on ${me.plans.find((x) => x.id === plan)?.name}.`
        : kind === "unlock" ? `${name} can sign in again.` : `${name} is signed out everywhere.`);
      onDone(out);
    } catch (err) {
      toast.error(err.message);
    } finally { setBusy(false); }
  };

  return (
    <Modal open onClose={onClose} title={s.title}>
      <form onSubmit={submit} className="space-y-3">
        <p className="-mt-1 text-sm text-muted">{s.sub}</p>
        {kind === "credits" && (
          <>
            <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)] gap-2">
              <Field label="What">
                <select className="input" value={meter} onChange={(e) => setMeter(e.target.value)}>
                  {me.meters.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
                </select>
              </Field>
              <Field label="How many"><input className="input" type="number" min={1} max={capped ? me.support_credit_limit : 100000} value={quantity} onChange={(e) => setQuantity(e.target.value)} /></Field>
              <Field label="Days"><input className="input" type="number" min={1} max={capped ? me.support_credit_days : 365} value={days} onChange={(e) => setDays(e.target.value)} /></Field>
            </div>
            {capped && <p className="text-xs text-faint">Your role can grant up to {me.support_credit_limit}, for up to {me.support_credit_days} days.</p>}
          </>
        )}
        {kind === "plan" && (
          <Field label="Plan">
            <select className="input" value={plan} onChange={(e) => setPlan(e.target.value)}>
              {me.plans.map((x) => <option key={x.id} value={x.id}>{x.name}{x.price_inr ? ` · ${inr(x.price_inr)} a month` : ""}</option>)}
            </select>
          </Field>
        )}
        <Field label="Reason" hint="At least 5 characters. Goes in the team's log.">
          <textarea className="input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} placeholder="What happened? This goes in the log." autoFocus />
        </Field>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="subtle" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant={kind === "sign-out" ? "danger" : "primary"} busy={busy} disabled={!ok}>{s.button}</Button>
        </div>
      </form>
    </Modal>
  );
}

// ---- one customer --------------------------------------------------------------------------------------------------
function Section({ title, children }) {
  return <div className="min-w-0"><h3 className="mb-2 text-[13px] font-semibold text-strong">{title}</h3>{children}</div>;
}

function CustomerPane({ id, me, onBack, onOpen }) {
  const { data: c, setData, loading, error, reload } = useApi(id ? `/api/console/customers/${id}` : null);
  const [dialog, setDialog] = useState(null);
  const can = (perm) => me.permissions.includes(perm);
  if (!id) return <p className="py-24 text-center text-sm text-faint">Pick someone on the left.</p>;
  if (error) return <Notice tone="rose" icon={AlertTriangle} action={<Button size="sm" variant="ghost" onClick={reload}>Retry</Button>}>{error.message}</Notice>;
  if (loading || !c) return <ListSkeleton rows={6} />;

  const p = c.profile, b = c.billing, u = c.usage;
  const isTeam = !!p.staff_role, ownerOnly = isTeam && me.role !== "owner";
  const person = p.kind === "person";
  const alerts = [
    p.locked && `Sign-in locked after ${p.failed_logins} wrong passwords`,
    !p.verified && "Email not verified yet",
    b.status === "past_due" && "Renewal payment failed",
    b.status === "expired" && "No active plan",
    u.calls.failed_30d && `${u.calls.failed_30d} call${u.calls.failed_30d === 1 ? "" : "s"} failed in the last 30 days`,
    u.whatsapp.failed_30d && `${u.whatsapp.failed_30d} WhatsApp message${u.whatsapp.failed_30d === 1 ? "" : "s"} failed to send`,
    u.pictures_videos.failed_30d && `${u.pictures_videos.failed_30d} picture${u.pictures_videos.failed_30d === 1 ? "" : "s"} or video${u.pictures_videos.failed_30d === 1 ? "" : "s"} failed`,
  ].filter(Boolean);
  const recent = [
    ["Leads", u.leads.last_30d, u.leads.opted_out ? `${u.leads.opted_out} opted out` : ""],
    ["Calls", u.calls.last_30d, u.calls.failed_30d ? `${u.calls.failed_30d} failed` : ""],
    ["WhatsApp messages", u.whatsapp.last_30d, u.whatsapp.failed_30d ? `${u.whatsapp.failed_30d} failed` : ""],
    ["Pictures and videos", u.pictures_videos.last_30d, u.pictures_videos.failed_30d ? `${u.pictures_videos.failed_30d} failed` : ""],
    ["Pages", `${u.pages.published} live`, `${u.pages.total} in all`],
    ["Campaigns", `${u.campaigns.active} running`, `${u.campaigns.total} in all`],
  ];
  const actions = ownerOnly ? [] : [
    can("signin.unlock") && person && p.locked && ["unlock", "Unlock sign-in", "primary"],
    can("credits.grant") && ["credits", "Grant credits", "ghost"],
    can("plan.change") && ["plan", "Change plan", "ghost"],
    can("signin.revoke") && person && ["sign-out", "Sign out everywhere", "subtle"],
  ].filter(Boolean);

  return (
    <div>
      <button type="button" onClick={onBack} className="mb-3 inline-flex items-center gap-1.5 text-sm text-muted hover:text-strong lg:hidden"><ArrowLeft className="size-4" /> All customers</button>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="flex flex-wrap items-center gap-2 text-[22px] font-bold leading-tight">{p.name || p.email}{isTeam && <Chip tone="violet">Team · {ROLE_LABEL[p.staff_role]}</Chip>}</h2>
          <p className="mt-1 text-[13px] text-muted">{person ? p.email : "Client workspace"}{p.company && p.company !== p.name ? ` · ${p.company}` : ""} · joined {day(p.created_at)} · #{p.id}</p>
        </div>
        <p className="text-right text-[13px]"><b className="text-strong">{b.plan_name}</b><br />
          <span className="text-faint">{b.trial_days_left !== null ? `${b.trial_days_left} days left` : b.processor === "manual" ? `Invoiced · renews ${day(b.period_end)}` : `Renews ${day(b.period_end)}`}</span></p>
      </div>

      {alerts.length > 0 && (
        <ul className="mt-4 space-y-1.5">
          {alerts.map((a) => <li key={a} className="flex items-center gap-2 rounded-xl bg-warm-soft px-3 py-2 text-[13px] text-warm"><AlertTriangle className="size-3.5 shrink-0" />{a}</li>)}
        </ul>
      )}

      {actions.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {actions.map(([k, label, variant]) => <Button key={k} size="sm" variant={variant} onClick={() => setDialog(k)}>{label}</Button>)}
        </div>
      )}
      {ownerOnly && <p className="mt-3 text-xs text-faint">This is a teammate's account. Only an owner can change it.</p>}

      <div className="mt-6 grid gap-x-8 gap-y-6 md:grid-cols-2">
        <Section title="Usage this period">
          <ul className="divide-y divide-line">
            {b.usage.filter((m) => m.meter !== "sites" || m.used).map((m) => {
              const pct = m.limit ? Math.min(100, Math.round((100 * m.used) / m.limit)) : 0;
              return (
                <li key={m.meter} className="py-2">
                  <div className="flex justify-between gap-2 text-[13px]"><span className="truncate">{m.label}</span><span className="shrink-0 font-semibold text-strong">{m.used} / {m.limit ?? "no limit"}</span></div>
                  {m.limit ? <div className="mt-1.5 h-[3px] rounded-full bg-surface-2"><div className={cx("h-full rounded-full", pct > 85 ? "bg-warm" : "bg-brand")} style={{ width: `${pct}%` }} /></div> : null}
                </li>
              );
            })}
          </ul>
        </Section>
        <Section title="Last 30 days">
          <ul className="divide-y divide-line">
            {recent.map(([label, n, note]) => (
              <li key={label} className="flex justify-between gap-2 py-2 text-[13px]"><span>{label}</span>
                <span className="text-right"><b className="text-strong">{n}</b>{note && <span className={cx("ml-1.5", /failed/.test(note) ? "text-warm" : "text-faint")}>{note}</span>}</span></li>
            ))}
          </ul>
        </Section>
        <Section title={person ? "Workspaces" : "Members"}>
          {(person ? c.workspaces : c.members).length === 0 && c.invites.length === 0 ? <p className="text-[13px] text-faint">{person ? "Only their own account." : "No members."}</p> : (
            <ul className="divide-y divide-line">
              {person
                ? c.workspaces.map((w) => <li key={w.id} className="flex justify-between gap-2 py-2 text-[13px]"><button type="button" className="truncate text-brand hover:underline" onClick={() => onOpen(w.id)}>{w.name}</button><span className="text-faint">{w.role}</span></li>)
                : c.members.map((m) => <li key={m.email} className="flex justify-between gap-2 py-2 text-[13px]"><span className="truncate">{m.email}</span><span className="text-faint">{m.role}</span></li>)}
              {c.invites.map((i) => <li key={i.email} className="flex justify-between gap-2 py-2 text-[13px] text-faint"><span className="truncate">{i.email}</span><span>{i.role} · invited</span></li>)}
            </ul>
          )}
          <h3 className="mb-2 mt-5 text-[13px] font-semibold text-strong">Connected</h3>
          {c.connected.length ? <div className="flex flex-wrap gap-1.5">{c.connected.map((k) => <Chip key={k}>{k}</Chip>)}</div> : <p className="text-[13px] text-faint">Nothing connected.</p>}
          {c.credits.length > 0 && (<>
            <h3 className="mb-2 mt-5 text-[13px] font-semibold text-strong">Extra credits</h3>
            <ul className="divide-y divide-line">
              {c.credits.map((g, i) => <li key={i} className="py-2 text-[13px]"><span className="text-strong">{g.quantity} {METER_LABEL[g.meter] || g.meter}</span> <span className="text-faint">until {day(g.expires_at)}</span>{g.note && <span className="block text-xs text-faint">{g.note}</span>}</li>)}
            </ul>
          </>)}
        </Section>
        <Section title="History">
          {c.history.length === 0 ? <p className="text-[13px] text-faint">Nobody on the team has changed anything here.</p> : (
            <ul className="divide-y divide-line">{c.history.map((a) => <LogRow key={a.id} a={a} />)}</ul>
          )}
        </Section>
      </div>

      {dialog && <ActionDialog kind={dialog} customer={c} me={me} onClose={() => setDialog(null)} onDone={(out) => { setData(out); setDialog(null); }} />}
    </div>
  );
}

// ---- customers ------------------------------------------------------------------------------------------------------
function Customers({ me }) {
  const [params, setParams] = useSearchParams();
  const selected = params.get("c") ? Number(params.get("c")) : null;
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("all");
  const [status, setStatus] = useState("all");
  const [limit, setLimit] = useState(50);
  const dq = useDebounced(q);
  const path = `/api/console/customers?${new URLSearchParams({ q: dq, kind, status, limit })}`;
  const { data, loading, error, reload } = useApi(path);
  const open = (id) => setParams((p) => { const n = new URLSearchParams(p); if (id) n.set("c", id); else n.delete("c"); return n; });
  const filtered = dq || kind !== "all" || status !== "all";

  return (
    <div className="flex flex-col gap-5 lg:flex-row lg:items-start">
      <section aria-label="Customers" className={cx("card min-w-0 lg:w-[380px] lg:shrink-0", selected && "hidden lg:block")}>
        <div className="space-y-2.5 p-3.5 pb-2.5">
          <label className="relative block">
            <span className="sr-only">Search customers</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" />
            <input className="input pl-9" type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search email, name, company or id" />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <Tabs value={kind} onChange={setKind} tabs={[{ value: "all", label: "All" }, { value: "person", label: "People" }, { value: "workspace", label: "Workspaces" }]} />
            <label className="ml-auto"><span className="sr-only">Plan status</span>
              <select className="h-8 rounded-lg bg-transparent px-2 text-xs text-muted ring-1 ring-line-strong" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="all">Any status</option>
                {Object.entries(STATUS).map(([k, [label]]) => <option key={k} value={k}>{label}</option>)}
              </select>
            </label>
          </div>
        </div>
        {error ? (
          <div className="p-4"><Notice tone="rose" icon={AlertTriangle} action={<Button size="sm" variant="ghost" onClick={reload}>Retry</Button>}>{error.message}</Notice></div>
        ) : loading || !data ? <div className="p-3.5"><ListSkeleton rows={7} /></div> : data.items.length === 0 ? (
          <Empty compact filtered={filtered} icon={Search} title={filtered ? `No one matches${dq ? ` “${dq}”` : " those filters"}.` : "No customers yet."}
            action={filtered ? <Button size="sm" variant="ghost" onClick={() => { setQ(""); setKind("all"); setStatus("all"); }}>Clear</Button> : null} />
        ) : (
          <>
            <ul className="divide-y divide-line border-t border-line">
              {data.items.map((r) => {
                const [label, tone] = STATUS[r.status] || [r.status, "text-muted"];
                return (
                  <li key={r.id}>
                    <button type="button" onClick={() => open(r.id)} aria-current={selected === r.id ? "true" : undefined}
                      className={cx("flex w-full items-center gap-3 px-3.5 py-2.5 text-left hover:bg-surface-2/60", selected === r.id && "bg-surface-2")}>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center gap-1.5 truncate text-sm font-semibold text-strong">{r.name || r.email}{r.staff_role && <Chip tone="violet" className="!px-1.5 !py-0">Team</Chip>}</span>
                        <span className="block truncate text-xs text-faint">{r.kind === "workspace" ? `Client workspace${r.agency ? ` · run by ${r.agency}` : ""}` : r.email}</span>
                      </span>
                      <span className="shrink-0 text-right">
                        <span className={cx("block text-xs font-semibold", tone)}>{label}</span>
                        <span className="block text-xs text-faint">{r.leads} lead{r.leads === 1 ? "" : "s"} · {ago(r.last_activity)}</span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <p className="px-3.5 py-3 text-xs text-faint">
              {data.items.length} of {data.total}
              {data.items.length < data.total && <> · <button type="button" className="text-brand hover:underline" onClick={() => setLimit((l) => Math.min(200, l + 50))}>Show more</button></>}
            </p>
          </>
        )}
      </section>
      <section aria-label="Customer" className={cx("card card-pad min-w-0 flex-1", !selected && "hidden lg:block")}>
        <CustomerPane key={selected} id={selected} me={me} onBack={() => open(null)} onOpen={open} />
      </section>
    </div>
  );
}

// ---- activity -------------------------------------------------------------------------------------------------------
const ACTIONS = [
  ["", "Every action"], ["credits.grant", "Credits granted"], ["plan.change", "Plan changes"], ["signin.unlock", "Sign-ins unlocked"],
  ["signin.revoke", "Signed out everywhere"], ["customer.view", "Customers opened"], ["team.add", "Teammates added"],
  ["team.role", "Role changes"], ["team.remove", "Teammates removed"], ["template.publish", "Templates published"],
];

function Activity({ me, onOpen }) {
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const dActor = useDebounced(actor);
  const { data, setData, loading, error, reload } = useApi(`/api/console/activity?${new URLSearchParams({ action, actor: dActor })}`);
  const [more, setMore] = useState(false);
  const all = me.permissions.includes("activity.view_all");
  const older = async () => {
    setMore(true);
    try {
      const r = await get(`/api/console/activity?${new URLSearchParams({ action, actor: dActor, before: data.next })}`);
      setData((d) => ({ ...r, items: [...d.items, ...r.items] }));
    } catch (e) { toast.error(e.message); } finally { setMore(false); }
  };
  return (
    <div className="max-w-4xl">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <label><span className="sr-only">Action</span>
          <select className="h-9 rounded-lg bg-surface px-2.5 text-sm ring-1 ring-line-strong" value={action} onChange={(e) => setAction(e.target.value)}>
            {ACTIONS.filter(([k]) => all || !k.startsWith("team") && !k.startsWith("template")).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        <label><span className="sr-only">Teammate email</span>
          <input className="input !h-9 !w-56" value={actor} onChange={(e) => setActor(e.target.value)} placeholder="Teammate email" type="email" />
        </label>
        <span className="text-xs text-faint">{all ? "Every change the team makes, with the reason they gave." : "What the team did on customer accounts."}</span>
      </div>
      {error ? <Notice tone="rose" icon={AlertTriangle} action={<Button size="sm" variant="ghost" onClick={reload}>Retry</Button>}>{error.message}</Notice>
        : loading || !data ? <ListSkeleton rows={8} /> : data.items.length === 0 ? (
          <Empty compact filtered={!!(action || dActor)} icon={ShieldCheck} title={action || dActor ? "Nothing matches." : "Nothing in the log yet."}
            text={action || dActor ? null : "Every change someone on the team makes will show here."} />
        ) : (
          <div className="card px-4 sm:px-5">
            <ul className="divide-y divide-line">{data.items.map((a) => <LogRow key={a.id} a={a} onOpen={onOpen} />)}</ul>
            {data.more && <div className="border-t border-line py-3"><Button size="sm" variant="subtle" busy={more} onClick={older}>Show older</Button></div>}
          </div>
        )}
    </div>
  );
}

// ---- team -----------------------------------------------------------------------------------------------------------
const PERM_ROWS = [
  ["Look up customers", "customers.view"], ["Grant credits", "credits.grant"], ["Grant any amount", "credits.grant_any"],
  ["Change a plan", "plan.change"], ["Unlock a sign-in", "signin.unlock"], ["Sign a customer out everywhere", "signin.revoke"],
  ["Quality and usage numbers", "quality.view"], ["Whole action log", "activity.view_all"], ["Manage the team, AI keys, templates", "team.manage"],
];

function Team() {
  const { data, setData, loading, error, reload } = useApi("/api/console/team");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("support");
  const [busy, setBusy] = useState(null);
  const act = async (key, fn, msg) => {
    setBusy(key);
    try { setData(await fn()); if (msg) toast.success(msg); return true; } catch (e) { toast.error(e.message); return false; } finally { setBusy(null); }
  };
  if (error) return <Notice tone="rose" icon={AlertTriangle} action={<Button size="sm" variant="ghost" onClick={reload}>Retry</Button>}>{error.message}</Notice>;
  if (loading || !data) return <ListSkeleton rows={5} />;
  const assignable = data.roles.filter((r) => r.assignable);
  const stateTone = (s) => (s === "active" ? "text-ink" : "text-warm");
  const stateLabel = { active: "Active", "not verified": "Not verified", "hasn't signed up": "Hasn't signed up" };

  return (
    <div className="max-w-4xl space-y-6">
      <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => {
        e.preventDefault();
        if (!email.trim()) return;
        act("add", () => post("/api/console/team", { email: email.trim(), role }), `${email.trim()} added as ${ROLE_LABEL[role]}.`).then((ok) => ok && setEmail(""));
      }}>
        <label className="min-w-0 flex-1 basis-60"><span className="sr-only">Email</span>
          <input className="input" type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="teammate@company.com" required />
        </label>
        <label><span className="sr-only">Role</span>
          <select className="input !w-auto" value={role} onChange={(e) => setRole(e.target.value)}>
            {assignable.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </select>
        </label>
        <Button type="submit" busy={busy === "add"}><UserPlus className="size-4" /> Add teammate</Button>
      </form>
      <p className="-mt-3 text-xs text-faint">Their role counts once they sign up and verify this email.</p>

      <div>
        <h2 className="mb-1 text-[13px] font-semibold text-strong">Owners</h2>
        <p className="mb-2 text-xs text-faint">Set on the server (ADMIN_EMAILS). The app can't add or remove owners.</p>
        <ul className="card divide-y divide-line px-4 sm:px-5">
          {data.owners.map((o) => (
            <li key={o.email} className="flex flex-wrap items-center gap-2 py-3 text-sm">
              <span className="min-w-0 flex-1 truncate">{o.name && <b className="font-semibold text-strong">{o.name} </b>}<span className="text-muted">{o.email}</span></span>
              <span className={cx("text-xs", stateTone(o.state))}>{stateLabel[o.state]}</span>
            </li>
          ))}
        </ul>
      </div>

      <div>
        <h2 className="mb-2 text-[13px] font-semibold text-strong">Teammates</h2>
        {data.members.length === 0 ? <p className="text-sm text-faint">No one yet. Add your management, development and support people above.</p> : (
          <ul className="card divide-y divide-line px-4 sm:px-5">
            {data.members.map((m) => (
              <li key={m.id} className="flex flex-wrap items-center gap-x-3 gap-y-2 py-2.5 text-sm">
                <span className="min-w-0 flex-1 basis-56 truncate">{m.name && <b className="font-semibold text-strong">{m.name} </b>}<span className="text-muted">{m.email}</span></span>
                <span className={cx("text-xs", stateTone(m.state))}>{stateLabel[m.state]}</span>
                <label><span className="sr-only">Role for {m.email}</span>
                  <select className="h-8 rounded-lg bg-surface px-2 text-[13px] ring-1 ring-line-strong" value={m.role} disabled={busy === m.id}
                    onChange={(e) => act(m.id, () => post(`/api/console/team/${m.id}/role`, { role: e.target.value }), `${m.email} is now ${ROLE_LABEL[e.target.value]}.`)}>
                    {assignable.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
                  </select>
                </label>
                <IconButton label={`Remove ${m.email}`} danger busy={busy === `rm${m.id}`}
                  onClick={() => { if (window.confirm(`Remove ${m.email} from the team? They lose console access at once.`)) act(`rm${m.id}`, () => post(`/api/console/team/${m.id}/remove`), `${m.email} removed.`); }}>
                  <Trash2 className="size-4" />
                </IconButton>
              </li>
            ))}
          </ul>
        )}
      </div>

      <details className="group">
        <summary className="cursor-pointer text-[13px] font-semibold text-strong">What each role can do</summary>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[560px] text-[13px]">
            <thead><tr className="text-left text-muted"><th className="py-1.5 pr-3 font-semibold">Can do</th>{data.roles.map((r) => <th key={r.id} className="px-2 py-1.5 font-semibold">{r.label}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">
              {PERM_ROWS.map(([label, perm]) => (
                <tr key={perm}><td className="py-1.5 pr-3 text-strong">{label}</td>
                  {data.roles.map((r) => <td key={r.id} className={cx("px-2 py-1.5", r.can.includes(perm) ? "text-strong" : "text-faint")}>{r.can.includes(perm) ? (perm === "credits.grant" && !r.can.includes("credits.grant_any") ? "Small" : "Yes") : "No"}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}

// ---- page -----------------------------------------------------------------------------------------------------------
export default function Console() {
  const { data: me, error } = useApi("/api/console/me");
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const tab = params.get("tab") || "customers";
  const tabs = useMemo(() => [
    { value: "customers", label: "Customers" }, { value: "activity", label: "Activity" },
    ...(me?.permissions.includes("team.manage") ? [{ value: "team", label: "Team" }] : []),
  ], [me]);
  const setTab = (t) => setParams((p) => { const n = new URLSearchParams(p); n.set("tab", t); if (t !== "customers") n.delete("c"); return n; });
  const openCustomer = (id) => setParams(new URLSearchParams({ tab: "customers", c: String(id) }));

  useEffect(() => {
    if (error?.status === 403) { toast("Your role on the AIMVA team changed. Ask an owner.", { id: "console-role" }); navigate("/app", { replace: true }); }
  }, [error, navigate]);

  return (
    <div>
      <PageHeader icon={ShieldCheck} title="Team console" subtitle="Find a customer, see what's wrong, fix it on record."
        actions={me && <Chip tone="violet">{me.role_label}</Chip>} />
      {!me ? (error && error.status !== 403 ? <Notice tone="rose" icon={AlertTriangle}>{error.message}</Notice> : <div className="grid h-40 place-items-center"><Spinner className="size-5" /></div>) : (
        <>
          <div className="mb-5"><Tabs value={tab} onChange={setTab} tabs={tabs} /></div>
          {tab === "activity" ? <Activity me={me} onOpen={openCustomer} /> : tab === "team" && me.permissions.includes("team.manage") ? <Team /> : <Customers me={me} />}
        </>
      )}
    </div>
  );
}
