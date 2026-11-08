import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Download, ListChecks, ListPlus, Search, ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button, Chip, Empty, Field, IconButton, ListSkeleton, Modal, Notice, PageHeader, Spinner, Stat, StatStrip, Tabs, cx } from "../../components/ui";
import { api, get, post } from "../../lib/api";
import { parseServerDate, useApi } from "../../lib/hooks";
import { downloadBlob, stamp, toXlsx } from "../../lib/exporters";

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
const ROLE_LABEL = { owner: "Owner", manager: "Management", developer: "Development", support: "Support", accountant: "Accounts" };
const METER_LABEL = { images: "pictures", videos: "videos", voice_minutes: "call minutes", ai_actions: "AI writing runs", sites: "pages" };

const TASK_STATUS_WORD = { open: "to do", doing: "doing", done: "done", cancelled: "cancelled" };

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
    case "task.assign": return [d.from ? `handed “${d.title}” from ${d.from} to` : `assigned “${d.title}” to`, d.to];
    case "task.status": return [`marked “${d.title}”`, TASK_STATUS_WORD[d.to] || d.to];
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
  if (can("tasks.assign")) actions.push(["task", "Assign a task", "subtle"]);

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

      {dialog === "task" && <TaskDialog me={me} customer={{ id: p.id, name: p.name || p.email }} onClose={() => setDialog(null)} onDone={() => setDialog(null)} />}
      {dialog && dialog !== "task" && <ActionDialog kind={dialog} customer={c} me={me} onClose={() => setDialog(null)} onDone={(out) => { setData(out); setDialog(null); }} />}
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
  ["team.role", "Role changes"], ["team.remove", "Teammates removed"], ["task.assign", "Tasks assigned"], ["task.status", "Task updates"], ["template.publish", "Templates published"],
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
  ["Overview and assigning tasks", "tasks.assign"], ["Billing (read-only)", "billing.view"], ["Quality and usage numbers", "quality.view"], ["Whole action log", "activity.view_all"], ["Manage the team, AI keys, templates", "team.manage"],
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

// ---- tasks ----------------------------------------------------------------------------------------------------------
const TASK_STATUS = { open: "To do", doing: "Doing", done: "Done", cancelled: "Cancelled" };
const dueLabel = (d) => (d ? new Date(`${d}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "");

function TaskDialog({ me, customer, onClose, onDone }) {
  const [title, setTitle] = useState("");
  const [note, setNote] = useState("");
  const [assignee, setAssignee] = useState(me.team.find((t) => t.email !== me.email)?.email || me.email);
  const [due, setDue] = useState("");
  const [high, setHigh] = useState(false);
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const t = await post("/api/console/tasks", { title: title.trim(), note: note.trim(), assignee, priority: high ? "high" : "normal",
        due_on: due || null, customer_id: customer?.id ?? null });
      toast.success(`Assigned to ${t.assignee_name || t.assignee}.`);
      onDone?.(t);
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  return (
    <Modal open onClose={onClose} title={customer ? `Assign a task about ${customer.name}` : "Assign a task"}>
      <form onSubmit={submit} className="space-y-3">
        <Field label="What needs doing"><input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Call them about the failed images" autoFocus required minLength={3} maxLength={200} /></Field>
        <div className="grid grid-cols-2 gap-2">
          <Field label="Who">
            <select className="input" value={assignee} onChange={(e) => setAssignee(e.target.value)}>
              {me.team.map((t) => <option key={t.email} value={t.email}>{t.name || t.email}{t.email === me.email ? " (you)" : ""} · {ROLE_LABEL[t.role]}</option>)}
            </select>
          </Field>
          <Field label="Due"><input className="input" type="date" value={due} onChange={(e) => setDue(e.target.value)} /></Field>
        </div>
        <Field label="Details" hint="Optional."><textarea className="input" rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={high} onChange={(e) => setHigh(e.target.checked)} /> Urgent</label>
        <div className="flex justify-end gap-2 pt-1">
          <Button type="button" variant="subtle" onClick={onClose}>Cancel</Button>
          <Button type="submit" busy={busy} disabled={title.trim().length < 3}>Assign</Button>
        </div>
      </form>
    </Modal>
  );
}

function TaskRow({ t, me, onChange, onOpen, showAssignee }) {
  const [busy, setBusy] = useState(false);
  const manager = me.permissions.includes("tasks.assign");
  const set = async (body, msg) => {
    setBusy(true);
    try { onChange(await api(`/api/console/tasks/${t.id}`, { method: "PATCH", body })); if (msg) toast.success(msg); }
    catch (e) { toast.error(e.message); } finally { setBusy(false); }
  };
  const active = t.status === "open" || t.status === "doing";
  return (
    <li className="flex flex-wrap items-start gap-x-3 gap-y-2 py-3">
      <input type="checkbox" aria-label={`Mark “${t.title}” done`} className="mt-1 size-4 accent-[var(--color-strong)]" checked={t.status === "done"} disabled={busy || t.status === "cancelled"}
        onChange={(e) => set({ status: e.target.checked ? "done" : "open" }, e.target.checked ? "Done." : null)} />
      <span className="min-w-0 flex-1 basis-64 text-sm">
        <span className={cx("font-medium", t.status === "done" ? "text-faint line-through" : "text-strong")}>{t.title}</span>
        {t.priority === "high" && active && <span className="ml-2 text-xs font-semibold text-warm">Urgent</span>}
        <span className="mt-0.5 block text-xs text-faint">
          {showAssignee && <>{t.assignee_name || t.assignee} · </>}
          {t.customer && <>about <button type="button" className="text-brand hover:underline" onClick={() => onOpen(t.customer_id)}>{t.customer}</button> · </>}
          {t.due_on && <span className={cx(t.overdue && "font-semibold text-warm")}>{t.overdue ? "overdue, " : ""}due {dueLabel(t.due_on)} · </span>}
          from {t.created_by_name || t.created_by}
        </span>
        {t.note && <span className="mt-1 block whitespace-pre-line text-[13px] text-muted">{t.note}</span>}
      </span>
      <span className="flex items-center gap-1.5">
        <label><span className="sr-only">Status</span>
          <select className="h-8 rounded-lg bg-surface px-2 text-[13px] ring-1 ring-line-strong" value={t.status} disabled={busy}
            onChange={(e) => set({ status: e.target.value })}>
            {Object.entries(TASK_STATUS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
          </select>
        </label>
        {manager && active && (
          <label><span className="sr-only">Assigned to</span>
            <select className="h-8 max-w-40 rounded-lg bg-surface px-2 text-[13px] ring-1 ring-line-strong" value={t.assignee} disabled={busy}
              onChange={(e) => set({ assignee: e.target.value }, "Reassigned.")}>
              {me.team.map((m) => <option key={m.email} value={m.email}>{m.name || m.email}</option>)}
            </select>
          </label>
        )}
      </span>
    </li>
  );
}

function Tasks({ me, onOpen }) {
  const manager = me.permissions.includes("tasks.assign");
  const [params] = useSearchParams();
  const [scope, setScope] = useState(manager && params.get("scope") === "all" ? "all" : "mine");
  const [status, setStatus] = useState("active");
  const [who, setWho] = useState("");
  const [assigning, setAssigning] = useState(false);
  const qs = new URLSearchParams({ scope, status, ...(scope === "all" && who ? { assignee: who } : {}) });
  const { data, setData, loading, error, reload } = useApi(`/api/console/tasks?${qs}`);
  const replace = (t) => setData((d) => {
    const fits = (status === "active") === (t.status === "open" || t.status === "doing") || status === "all";
    const stillMine = scope !== "mine" || t.assignee === me.email;
    return { ...d, items: fits && stillMine ? d.items.map((x) => (x.id === t.id ? t : x)) : d.items.filter((x) => x.id !== t.id) };
  });
  return (
    <div className="max-w-4xl">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {manager && <Tabs value={scope} onChange={setScope} tabs={[{ value: "mine", label: "Mine" }, { value: "all", label: "Everyone's" }]} />}
        <label><span className="sr-only">Show</span>
          <select className="h-9 rounded-lg bg-surface px-2.5 text-sm ring-1 ring-line-strong" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="active">To do and doing</option><option value="done">Done and cancelled</option><option value="all">All</option>
          </select>
        </label>
        {manager && scope === "all" && (
          <label><span className="sr-only">Person</span>
            <select className="h-9 rounded-lg bg-surface px-2.5 text-sm ring-1 ring-line-strong" value={who} onChange={(e) => setWho(e.target.value)}>
              <option value="">Everyone</option>
              {me.team.map((m) => <option key={m.email} value={m.email}>{m.name || m.email}</option>)}
            </select>
          </label>
        )}
        {manager && <Button size="sm" className="ml-auto" onClick={() => setAssigning(true)}><ListPlus className="size-4" /> Assign a task</Button>}
      </div>
      {error ? <Notice tone="rose" icon={AlertTriangle} action={<Button size="sm" variant="ghost" onClick={reload}>Retry</Button>}>{error.message}</Notice>
        : loading || !data ? <ListSkeleton rows={5} /> : data.items.length === 0 ? (
          <Empty compact icon={ListChecks} title={status === "active" ? (scope === "mine" ? "Nothing on your list." : "No open tasks.") : "Nothing here yet."}
            text={scope === "mine" && status === "active" ? (manager ? "Tasks you assign to yourself show here too." : "When an owner or manager gives you a task, it shows here.") : null} />
        ) : (
          <ul className="card divide-y divide-line px-4 sm:px-5">
            {data.items.map((t) => <TaskRow key={t.id} t={t} me={me} onChange={replace} onOpen={onOpen} showAssignee={scope === "all"} />)}
          </ul>
        )}
      {assigning && <TaskDialog me={me} onClose={() => setAssigning(false)} onDone={() => { setAssigning(false); reload(); }} />}
    </div>
  );
}

// ---- overview -------------------------------------------------------------------------------------------------------
const ACTION_WORD = { "credits.grant": "credits", "plan.change": "plan changes", "signin.unlock": "unlocks", "signin.revoke": "sign-outs",
  "task.status": "task updates", "task.assign": "tasks assigned", "team.add": "team changes", "team.role": "role changes", "team.remove": "removals",
  "template.publish": "templates", "template.dismiss": "templates" };

function Overview({ me, onTab }) {
  const [days, setDays] = useState("7");
  const { data: o, loading, error, reload } = useApi(`/api/console/overview?days=${days}`);
  if (error) return <Notice tone="rose" icon={AlertTriangle} action={<Button size="sm" variant="ghost" onClick={reload}>Retry</Button>}>{error.message}</Notice>;
  if (loading || !o) return <ListSkeleton rows={6} />;
  const p = o.platform, f = p.failed;
  const needs = [
    p.past_due && [`${p.past_due} customer${p.past_due === 1 ? "" : "s"} past due`, "customers"],
    p.trials_ending && [`${p.trials_ending} trial${p.trials_ending === 1 ? "" : "s"} end within 7 days`, "customers"],
    p.locked_signins && [`${p.locked_signins} locked sign-in${p.locked_signins === 1 ? "" : "s"}`, "customers"],
    f.calls && [`${f.calls} call${f.calls === 1 ? "" : "s"} failed`, null],
    f.whatsapp && [`${f.whatsapp} WhatsApp message${f.whatsapp === 1 ? "" : "s"} failed`, null],
    f.pictures_videos && [`${f.pictures_videos} picture${f.pictures_videos === 1 ? "" : "s"} or video${f.pictures_videos === 1 ? "" : "s"} failed`, null],
  ].filter(Boolean);
  const overdue = o.team.reduce((n, r) => n + r.tasks.overdue, 0);
  return (
    <div className="max-w-5xl space-y-7">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[13px] font-semibold text-strong">How the platform is doing</h2>
        <Tabs value={days} onChange={setDays} tabs={[{ value: "7", label: "7 days" }, { value: "30", label: "30 days" }]} />
      </div>
      <StatStrip className="-mt-4">
        <Stat label="Active accounts" value={p.active_accounts} sub={`of ${p.customers} customers and ${p.workspaces} client workspaces`} tone="violet" />
        <Stat label="New customers" value={p.new_customers} sub={`last ${o.days} days`} tone="green" />
        <Stat label="Leads captured" value={p.leads} sub={`for customers, last ${o.days} days`} tone="blue" />
        <Stat label="Paying" value={p.paying} sub={`${p.past_due} past due`} tone="amber" />
      </StatStrip>
      {needs.length > 0 && (
        <div>
          <h3 className="mb-2 text-[13px] font-semibold text-strong">Needs someone</h3>
          <ul className="space-y-1.5">
            {needs.map(([text, tab]) => (
              <li key={text} className="flex items-center gap-2 rounded-xl bg-warm-soft px-3 py-2 text-[13px] text-warm">
                <AlertTriangle className="size-3.5 shrink-0" /><span className="flex-1">{text}</span>
                {tab && <button type="button" className="text-xs font-semibold underline-offset-2 hover:underline" onClick={() => onTab(tab)}>Look</button>}
              </li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[13px] font-semibold text-strong">What the team is doing <span className="font-normal text-faint">· last {o.days} days{overdue ? ` · ${overdue} overdue` : ""}</span></h2>
          <Button size="sm" variant="ghost" onClick={() => onTab("tasks", "all")}><ListChecks className="size-4" /> All tasks</Button>
        </div>
        <div className="card overflow-x-auto px-4 sm:px-5">
          <table className="w-full min-w-[640px] text-[13px]">
            <thead><tr className="text-left text-xs text-muted">
              <th className="py-2.5 pr-3 font-semibold">Person</th><th className="px-2 font-semibold">Open tasks</th><th className="px-2 font-semibold">Done</th>
              <th className="px-2 font-semibold">Changes made</th><th className="px-2 font-semibold">Customers opened</th><th className="px-2 font-semibold">Last active</th>
            </tr></thead>
            <tbody className="divide-y divide-line">
              {o.team.map((r) => (
                <tr key={r.email}>
                  <td className="py-2.5 pr-3"><span className="block font-semibold text-strong">{r.name || r.email}</span><span className="text-xs text-faint">{r.role_label}</span></td>
                  <td className="px-2">{r.tasks.open + r.tasks.doing}{r.tasks.doing ? <span className="text-faint"> · {r.tasks.doing} doing</span> : null}{r.tasks.overdue ? <span className="font-semibold text-warm"> · {r.tasks.overdue} overdue</span> : null}</td>
                  <td className="px-2">{r.tasks.done}</td>
                  <td className="px-2">{r.actions}{r.top.length > 0 && <span className="block text-xs text-faint">{r.top.map(([k, n]) => `${n} ${ACTION_WORD[k] || k}`).join(", ")}</span>}</td>
                  <td className="px-2">{r.customers_opened}</td>
                  <td className="px-2 text-muted">{r.last_active ? ago(r.last_active) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-faint">Counts what people do in this console. Work done elsewhere (code, calls, email) shows only through the tasks they close.</p>
      </div>
    </div>
  );
}

// ---- billing (read-only) --------------------------------------------------------------------------------------------
function Billing({ onOpen }) {
  const [days, setDays] = useState("30");
  const [status, setStatus] = useState("");
  const { data: b, loading, error, reload } = useApi(`/api/console/billing?days=${days}`);
  if (error) return <Notice tone="rose" icon={AlertTriangle} action={<Button size="sm" variant="ghost" onClick={reload}>Retry</Button>}>{error.message}</Notice>;
  if (loading || !b) return <ListSkeleton rows={6} />;
  const t = b.totals, subs = b.subscriptions.filter((s) => !status || s.status === status);
  const download = () => {
    const subCols = [
      { key: "name", label: "Customer" }, { key: "email", label: "Email" }, { key: "plan_name", label: "Plan" },
      { key: "price_inr", label: "Monthly (INR)" }, { label: "Status", get: (r) => STATUS[r.status]?.[0] || r.status },
      { label: "Billed by", get: (r) => (r.processor === "manual" ? "Invoice" : r.processor || "—") },
      { label: "Period start", get: (r) => day(r.period_start) }, { label: "Period end", get: (r) => day(r.period_end) }, { key: "note", label: "Note" },
    ];
    const credCols = [
      { label: "Given on", get: (r) => day(r.at) }, { key: "customer", label: "Customer" }, { label: "What", get: (r) => METER_LABEL[r.meter] || r.meter },
      { key: "quantity", label: "Units" }, { label: "Expires", get: (r) => day(r.expires_at) }, { key: "note", label: "Reason" },
    ];
    downloadBlob(toXlsx([{ name: "Plans", columns: subCols, rows: b.subscriptions }, { name: `Credits ${b.days} days`, columns: credCols, rows: b.credits }]),
      `aimva-billing-${stamp()}.xlsx`);
  };
  return (
    <div className="max-w-5xl space-y-6">
      {!b.live_payments && (
        <Notice tone="amber" icon={AlertTriangle}>Payments aren't live yet. These are list prices from each account's plan, not money received. There are no GST invoices in AIMVA yet.</Notice>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[13px] font-semibold text-strong">Plans and revenue</h2>
        <Button size="sm" variant="ghost" onClick={download} disabled={!b.subscriptions.length}><Download className="size-4" /> Excel</Button>
      </div>
      <StatStrip className="-mt-3">
        <Stat label="Monthly revenue" value={inr(t.mrr_inr)} sub="active paid plans, list price" tone="green" />
        <Stat label="Past due" value={inr(t.past_due_inr)} sub={`${t.by_status.past_due || 0} account${t.by_status.past_due === 1 ? "" : "s"}`} tone="amber" />
        <Stat label="On trial" value={t.by_status.trialing || 0} sub={`${t.by_status.expired || 0} expired`} tone="violet" />
        <Stat label="Invoiced by you" value={t.invoiced} sub="active plans with no card" tone="blue" />
      </StatStrip>
      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <label><span className="sr-only">Status</span>
            <select className="h-9 rounded-lg bg-surface px-2.5 text-sm ring-1 ring-line-strong" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Every status</option>
              {Object.entries(STATUS).filter(([k]) => k !== "new").map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
            </select>
          </label>
          <span className="text-xs text-faint">{subs.length} account{subs.length === 1 ? "" : "s"}</span>
        </div>
        {subs.length === 0 ? <p className="text-sm text-faint">No accounts with that status.</p> : (
          <div className="card overflow-x-auto px-4 sm:px-5">
            <table className="w-full min-w-[640px] text-[13px]">
              <thead><tr className="text-left text-xs text-muted">
                <th className="py-2.5 pr-3 font-semibold">Customer</th><th className="px-2 font-semibold">Plan</th><th className="px-2 text-right font-semibold">Monthly</th>
                <th className="px-2 font-semibold">Status</th><th className="px-2 font-semibold">Billed by</th><th className="px-2 font-semibold">Period ends</th>
              </tr></thead>
              <tbody className="divide-y divide-line">
                {subs.map((s) => {
                  const [label, tone] = STATUS[s.status] || [s.status, "text-muted"];
                  return (
                    <tr key={s.id}>
                      <td className="py-2.5 pr-3"><button type="button" className="text-left font-medium text-strong hover:underline" onClick={() => onOpen(s.id)}>{s.name || s.email}</button>
                        <span className="block text-xs text-faint">{s.email || "Client workspace"}</span></td>
                      <td className="px-2">{s.plan_name}</td>
                      <td className="px-2 text-right tabular-nums">{s.price_inr ? inr(s.price_inr) : "—"}</td>
                      <td className={cx("px-2 font-semibold", tone)}>{label}</td>
                      <td className="px-2 text-muted">{s.processor === "manual" ? "Invoice" : s.processor || "—"}</td>
                      <td className="px-2 text-muted">{day(s.period_end)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div>
        <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-[13px] font-semibold text-strong">Credits given away <span className="font-normal text-faint">· last {b.days} days</span></h2>
          <Tabs value={days} onChange={setDays} tabs={[{ value: "30", label: "30 days" }, { value: "90", label: "90 days" }, { value: "365", label: "Year" }]} />
        </div>
        {b.credits.length === 0 ? <p className="text-sm text-faint">No goodwill credits in this period.</p> : (
          <ul className="card divide-y divide-line px-4 sm:px-5">
            {b.credits.map((g, i) => (
              <li key={i} className="flex flex-wrap gap-x-3 py-2.5 text-[13px]">
                <span className="w-16 shrink-0 text-faint">{ago(g.at)}</span>
                <span className="min-w-0 flex-1"><b className="font-semibold text-strong">{g.quantity} {METER_LABEL[g.meter] || g.meter}</b> to{" "}
                  <button type="button" className="text-brand hover:underline" onClick={() => onOpen(g.customer_id)}>{g.customer}</button>
                  {g.note && <span className="block text-xs text-muted">{g.note}</span>}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ---- page -----------------------------------------------------------------------------------------------------------
export default function Console() {
  const { data: me, error } = useApi("/api/console/me");
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const lead = me?.permissions.includes("overview.view");
  const money = me?.permissions.includes("billing.view");
  const tab = params.get("tab") || (lead ? "overview" : me?.role === "accountant" ? "billing" : "tasks");
  const tabs = useMemo(() => [
    ...(me?.permissions.includes("overview.view") ? [{ value: "overview", label: "Overview" }] : []),
    ...(me?.role === "accountant" ? [{ value: "billing", label: "Billing" }] : []),
    { value: "tasks", label: "Tasks" }, { value: "customers", label: "Customers" },
    ...(me?.permissions.includes("billing.view") && me?.role !== "accountant" ? [{ value: "billing", label: "Billing" }] : []),
    { value: "activity", label: "Activity" },
    ...(me?.permissions.includes("team.manage") ? [{ value: "team", label: "Team" }] : []),
  ], [me]);
  const setTab = (t, scope) => setParams((p) => {
    const n = new URLSearchParams(p); n.set("tab", t);
    if (t !== "customers") n.delete("c");
    if (scope) n.set("scope", scope); else n.delete("scope");
    return n;
  });
  const page = tab === "overview" && lead ? <Overview me={me} onTab={setTab} />
    : tab === "billing" && money ? <Billing onOpen={(id) => openCustomer(id)} />
    : tab === "tasks" ? <Tasks key="tasks" me={me} onOpen={(id) => openCustomer(id)} />
    : tab === "activity" ? <Activity me={me} onOpen={(id) => openCustomer(id)} />
    : tab === "team" && me?.permissions.includes("team.manage") ? <Team />
    : <Customers me={me} />;
  const openCustomer = (id) => setParams(new URLSearchParams({ tab: "customers", c: String(id) }));

  useEffect(() => {
    if (error?.status === 403) { toast("Your role on the AIMVA team changed. Ask an owner.", { id: "console-role" }); navigate("/", { replace: true }); }
  }, [error, navigate]);

  return (
    <div>
      <PageHeader icon={ShieldCheck} title="Team console" subtitle="See how the platform is doing, hand out the work, and fix customer problems on record."
        actions={me && <Chip tone="violet">{me.role_label}</Chip>} />
      {!me ? (error && error.status !== 403 ? <Notice tone="rose" icon={AlertTriangle}>{error.message}</Notice> : <div className="grid h-40 place-items-center"><Spinner className="size-5" /></div>) : (
        <>
          <div className="mb-5"><Tabs value={tab} onChange={setTab} tabs={tabs} /></div>
          {page}
        </>
      )}
    </div>
  );
}
