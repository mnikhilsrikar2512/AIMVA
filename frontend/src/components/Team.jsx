// Working together on a project (design.md 3.6): Admin and Editor, invited per project. Agency client access is gone.
// Solo owners never see team UI unless they open Settings → Team.
import { useState } from "react";
import { Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button, Empty, ListSkeleton, Spinner } from "./ui";
import { del, post } from "../lib/api";
import { useApi } from "../lib/hooks";
import { useAuth } from "../lib/auth";
import { ROLE_HINT, ROLE_LABEL, useWorkspaces } from "../lib/workspaces";

/** Settings → Team. */
export function TeamPanel() {
  const { user } = useAuth();
  const { active, reload: reloadWs, error: wsError } = useWorkspaces();
  const viewOnly = active?.role === "client";  // clients don't see or manage the team list
  const members = useApi(active && !viewOnly ? `/api/workspaces/${active.id}/members` : null, null);
  const [f, setF] = useState({ email: "", role: "editor" });
  const [busy, setBusy] = useState(false);
  if (wsError) return <Empty compact icon={UserPlus} title="Teams aren't switched on yet" text={wsError.status === 404 ? "This server doesn't have teams yet. Update the AIMVA backend to invite people." : "The team didn't load."} action={wsError.status === 404 ? null : <Button variant="ghost" size="sm" onClick={reloadWs}>Try again</Button>} />;
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
  if (viewOnly) return <p className="max-w-2xl text-sm text-muted">The project's owner decides who works on it. Ask them if someone needs access.</p>;
  return (
    <div className="max-w-2xl space-y-8">
      <section>
        <h2 className="text-sm font-semibold text-strong">{`People working on ${active.own ? "this project" : active.name}`}</h2>
        <p className="mt-1 text-sm text-muted">{m.length <= 1 && !inv.length ? "Just you for now. Invite a partner, a receptionist who answers leads, or whoever does your marketing." : "Everyone here sees the same pages, campaigns and leads."}</p>
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
              <option value="editor">Editor</option><option value="admin">Admin</option>
            </select>
            <Button type="submit" busy={busy}><UserPlus className="size-4" /> Invite</Button>
          </form>
          <p className="mt-2 text-xs text-muted">{ROLE_LABEL[f.role]}: {ROLE_HINT[f.role]}</p>
        </section>
      )}

    </div>
  );
}

