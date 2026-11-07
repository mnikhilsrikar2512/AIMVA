// Working alone or together (design.md section 7). Solo owners never see this unless they open Settings → Team.
import { useState } from "react";
import { Check, ChevronsUpDown, Plus, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button, Empty, Field, ListSkeleton, Modal, Spinner, cx } from "./ui";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "./shadcn/dropdown-menu";
import { api, del, patch, post } from "../lib/api";
import { useApi } from "../lib/hooks";
import { useAuth } from "../lib/auth";
import { ROLE_HINT, ROLE_LABEL, switchWorkspace, useWorkspaces } from "../lib/workspaces";

/** "Add a client": creates a workspace for another business and switches to it. */
export function AddClientDialog({ open, onClose }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const w = await post("/api/workspaces", { name: name.trim() });
      toast.success(`${w.name} added.`);
      await switchWorkspace(w.id, w.name);
    } catch (err) { toast.error(err.message); setBusy(false); }
  };
  return (
    <Modal open={open} onClose={onClose} title="Add a client">
      <form onSubmit={submit} className="space-y-4">
        <p className="text-sm text-muted">Each client gets their own pages, campaigns, leads and results. You can switch between them from the top of the menu.</p>
        <Field label="Business name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Skyline Homes" required autoFocus maxLength={160} /></Field>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-subtle" onClick={onClose}>Cancel</button>
          <Button type="submit" busy={busy} disabled={!name.trim()}>Add and open</Button>
        </div>
      </form>
    </Modal>
  );
}

/** Under the logo in the rail. Hidden until there is more than one workspace. */
export function WorkspaceSwitcher({ expanded = true }) {
  const { list, active } = useWorkspaces();
  const [adding, setAdding] = useState(false);
  if (list.length < 2 || !active) return null;
  const initial = (active.name || "?")[0].toUpperCase();
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" title={expanded ? undefined : `Working in ${active.name}`}
            className="mx-3 mb-2 flex h-9 w-[calc(100%-1.5rem)] items-center gap-2.5 rounded-lg px-2 text-left text-sm transition hover:bg-ink/[0.04]">
            <span className={cx("grid size-6 shrink-0 place-items-center rounded-md text-xs font-semibold", active.own ? "bg-surface-2 text-strong" : "bg-warm-soft text-warm")}>{initial}</span>
            <span className={cx("min-w-0 flex-1 truncate font-medium text-strong transition-opacity", expanded ? "opacity-100" : "opacity-0")}>{active.own ? "My business" : active.name}</span>
            <ChevronsUpDown className={cx("size-3.5 shrink-0 text-muted transition-opacity", expanded ? "opacity-100" : "opacity-0")} />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="w-60">
          <DropdownMenuLabel>Switch to</DropdownMenuLabel>
          {list.map((w) => (
            <DropdownMenuItem key={w.id} onSelect={() => { if (!w.active) switchWorkspace(w.id, w.own ? "your own account" : w.name).catch((e) => toast.error(e.message)); }}>
              <span className="min-w-0 flex-1 truncate">{w.own ? "My business" : w.name}</span>
              {!w.own && <span className="text-xs text-muted">{ROLE_LABEL[w.role] || w.role}</span>}
              {w.active && <Check />}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => setAdding(true)}><Plus /> Add a client</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <AddClientDialog open={adding} onClose={() => setAdding(false)} />
    </>
  );
}

/** Settings → Team. */
export function TeamPanel() {
  const { user } = useAuth();
  const { active, list, reload: reloadWs, error: wsError } = useWorkspaces();
  const members = useApi(active ? `/api/workspaces/${active.id}/members` : null, null);
  const [f, setF] = useState({ email: "", role: "editor" });
  const [busy, setBusy] = useState(false);
  const [adding, setAdding] = useState(false);
  if (wsError) return <Empty compact icon={UserPlus} title="Teams aren't switched on yet" text={wsError.status === 404 ? "This server doesn't have teams yet. Update the AIMVA backend to invite people and add clients." : "The team didn't load."} action={wsError.status === 404 ? null : <Button variant="ghost" size="sm" onClick={reloadWs}>Try again</Button>} />;
  if (!active) return <ListSkeleton rows={3} />;
  const canManage = ["owner", "admin"].includes(active.role);
  const m = members.data?.members || [];
  const inv = members.data?.invites || [];

  const invite = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await post(`/api/workspaces/${active.id}/invites`, { email: f.email.trim(), role: f.role });
      toast.success(`Invite sent to ${f.email.trim()}.`);
      setF({ ...f, email: "" });
      members.reload();
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  const remove = async (path, label) => {
    try { await del(path); toast(`${label} removed.`); members.reload(); } catch (err) { toast.error(err.message); }
  };
  const setApproval = async (on) => {
    try { await patch(`/api/workspaces/${active.id}`, { require_approval: on }); reloadWs(); toast(on ? "The client approves before anything goes live." : "Approval switched off."); }
    catch (err) { toast.error(err.message); }
  };

  return (
    <div className="max-w-2xl space-y-8">
      <section>
        <h2 className="text-sm font-semibold text-strong">{active.own ? "People in your business" : `People working on ${active.name}`}</h2>
        <p className="mt-1 text-sm text-muted">{m.length <= 1 && !inv.length ? "Just you for now. Invite a colleague, or the client themselves, when you want help or a second pair of eyes." : "Everyone here sees the same pages, campaigns and leads."}</p>
        {members.error ? (
          <p className="mt-3 text-sm text-muted">The team didn't load. <button className="font-medium text-brand hover:underline" onClick={members.reload}>Try again</button></p>
        ) : members.loading ? <div className="grid h-16 place-items-center"><Spinner className="size-5" /></div> : (
          <ul className="mt-3 border-t border-line">
            {m.map((p) => (
              <li key={`m${p.id}`} className="flex items-center gap-3 border-b border-line py-2.5">
                <span className="grid size-7 place-items-center rounded-full bg-surface-2 text-xs font-semibold text-strong">{(p.name || p.email || "?")[0].toUpperCase()}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium text-strong">{p.name || p.email}{p.email === user.email && <span className="font-normal text-muted"> (you)</span>}</span>
                  {p.name && <span className="block truncate text-xs text-muted">{p.email}</span>}
                </span>
                <span className="text-xs text-muted">{ROLE_LABEL[p.role] || p.role}</span>
                {canManage && p.role !== "owner" && p.email !== user.email && (
                  <button className="btn-subtle btn-sm px-2" aria-label={`Remove ${p.name || p.email}`} onClick={() => remove(`/api/workspaces/${active.id}/members/${p.id}`, p.name || p.email)}><Trash2 className="size-4" /></button>
                )}
              </li>
            ))}
            {inv.map((i) => (
              <li key={`i${i.id}`} className="flex items-center gap-3 border-b border-line py-2.5">
                <span className="grid size-7 place-items-center rounded-full border border-dashed border-line-strong text-xs text-muted">?</span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink">{i.email} <span className="text-muted">· invited</span></span>
                <span className="text-xs text-muted">{ROLE_LABEL[i.role] || i.role}</span>
                {canManage && <button className="btn-subtle btn-sm" onClick={() => remove(`/api/workspaces/${active.id}/invites/${i.id}`, `Invite for ${i.email}`)}>Cancel</button>}
              </li>
            ))}
          </ul>
        )}
      </section>

      {canManage && (
        <section>
          <h2 className="text-sm font-semibold text-strong">Invite someone</h2>
          <form onSubmit={invite} className="mt-3 flex flex-col gap-2 sm:flex-row">
            <input className="input sm:flex-1" type="email" required placeholder="name@company.com" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} aria-label="Email" />
            <select className="input sm:w-36" value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} aria-label="Role">
              <option value="editor">Editor</option><option value="admin">Admin</option><option value="client">Client</option>
            </select>
            <Button type="submit" busy={busy}><UserPlus className="size-4" /> Invite</Button>
          </form>
          <p className="mt-2 text-xs text-muted">{ROLE_LABEL[f.role]}: {ROLE_HINT[f.role]}</p>
        </section>
      )}

      {canManage && !active.own && (
        <section className="flex items-start justify-between gap-4 border-t border-line pt-6">
          <div>
            <h2 className="text-sm font-semibold text-strong">Ask {active.name} before anything goes live</h2>
            <p className="mt-1 text-sm text-muted">Publish and Launch become "Send for approval". The client approves or asks for changes from their bell.</p>
          </div>
          <button type="button" role="switch" aria-checked={!!active.require_approval} onClick={() => setApproval(!active.require_approval)}
            className={cx("relative mt-1 h-6 w-10 shrink-0 rounded-full transition", active.require_approval ? "bg-strong" : "bg-line-strong")}>
            <span className={cx("absolute top-0.5 size-5 rounded-full bg-white shadow transition-all", active.require_approval ? "left-[18px]" : "left-0.5")} />
          </button>
        </section>
      )}

      {active.own && list.length < 2 && (
        <section className="border-t border-line pt-6">
          <h2 className="text-sm font-semibold text-strong">Working for other businesses?</h2>
          <p className="mt-1 text-sm text-muted">Agencies and freelancers can keep each client separate, with their own pages, campaigns, leads and results.</p>
          <button className="btn-ghost btn-sm mt-3" onClick={() => setAdding(true)}><Plus className="size-4" /> Add a client</button>
        </section>
      )}
      <AddClientDialog open={adding} onClose={() => setAdding(false)} />
    </div>
  );
}

