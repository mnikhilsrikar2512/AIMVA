// The Projects window (design.md 3.5): every business or idea the person runs, as the app's only card grid.
// Flat cards: the project's latest work on top (4:3), then its name, one line of the idea, who's waiting, last activity.
// No shadow, gradient, icon or hover lift. "New project" is the screen's one rani button.
import { useEffect, useState } from "react";
import { MoreHorizontal, Plus } from "lucide-react";
import { toast } from "sonner";
import { Button, Field, Modal, PageHeader, cx } from "../../components/ui";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../../components/shadcn/dropdown-menu";
import { Tooltip } from "../../components/shadcn/tooltip";
import { LoadError } from "../../components/LoadError";
import { api, patch, post } from "../../lib/api";
import { parseServerDate } from "../../lib/hooks";
import { openProject, useProjects } from "../../lib/projects";

function lastActive(iso) {
  const d = parseServerDate(iso);
  if (Number.isNaN(d.getTime())) return "";
  const days = Math.floor((new Date().setHours(0, 0, 0, 0) - new Date(d).setHours(0, 0, 0, 0)) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return d.toLocaleDateString(undefined, { weekday: "long" });
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

/** A project with nothing made yet: a faint sketch of a page, not an illustration. */
function PageSketch() {
  return (
    <div aria-hidden className="flex size-full flex-col gap-2 p-6 opacity-70">
      <span className="h-2 w-1/3 rounded-full bg-line-strong" />
      <span className="mt-3 h-4 w-3/4 rounded-full bg-line-strong" />
      <span className="h-4 w-1/2 rounded-full bg-line-strong" />
      <span className="mt-auto h-7 w-24 rounded-md bg-line-strong" />
    </div>
  );
}

function ProjectCard({ p, onRename, onArchive, onDelete }) {
  const [opening, setOpening] = useState(false);
  const [broken, setBroken] = useState(false);
  const open = async () => {
    if (opening) return;
    setOpening(true);
    try { await openProject(p, "/app"); } catch (e) { toast.error(e.message); setOpening(false); }
  };
  const canManage = ["owner", "admin"].includes(p.role);
  return (
    <li className="group relative flex flex-col overflow-hidden rounded-[10px] border border-line bg-surface transition-colors hover:border-line-strong">
      <button type="button" onClick={open} aria-busy={opening || undefined} className="flex flex-1 flex-col text-left outline-offset-[-2px]">
        <span className="block aspect-[4/3] w-full overflow-hidden border-b border-line bg-surface-2">
          {p.thumbnail && !broken ? <img src={p.thumbnail} alt="" loading="lazy" className="size-full object-cover" onError={() => setBroken(true)} /> : <PageSketch />}
        </span>
        <span className="block px-4 pb-4 pt-3 pr-12">
          <span className="block truncate text-[15px] font-semibold text-strong">{p.name}</span>
          {p.idea && <span className="mt-0.5 block truncate text-sm text-muted">{p.idea}</span>}
          <span className="mt-2 block text-xs text-muted">
            {p.waiting > 0 && <span className="font-medium text-warm">{p.waiting} waiting for you · </span>}
            {opening ? "Opening…" : lastActive(p.last_activity)}
          </span>
        </span>
      </button>
      {canManage && (
        <DropdownMenu>
          <Tooltip content="More">
            <DropdownMenuTrigger asChild>
              <button type="button" aria-label={`More for ${p.name}`} className="btn-subtle btn-sm absolute bottom-3 right-2 w-8 px-0"><MoreHorizontal className="size-4" /></button>
            </DropdownMenuTrigger>
          </Tooltip>
          <DropdownMenuContent>
            <DropdownMenuItem onSelect={() => onRename(p)}>Rename</DropdownMenuItem>
            {!p.own && <DropdownMenuItem onSelect={() => onArchive(p, !p.archived)}>{p.archived ? "Restore" : "Archive"}</DropdownMenuItem>}
            {!p.own && p.role === "owner" && <><DropdownMenuSeparator /><DropdownMenuItem danger onSelect={() => onDelete(p)}>Delete…</DropdownMenuItem></>}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </li>
  );
}

function RenameDialog({ project, onClose, onDone }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setName(project?.name || ""); }, [project]);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try { await patch(`/api/projects/${project.id}`, { name: name.trim() }); onDone(); onClose(); } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  return (
    <Modal open={!!project} onClose={onClose} title="Rename project">
      <form onSubmit={submit} className="space-y-4">
        <Field label="Name"><input className="input" value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={160} required autoFocus /></Field>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-subtle" onClick={onClose}>Cancel</button>
          <Button type="submit" busy={busy} disabled={name.trim().length < 2}>Save</Button>
        </div>
      </form>
    </Modal>
  );
}

/** Delete is money and public pages, so it confirms by typing the name (the server checks it too). */
function DeleteDialog({ project, onClose, onDone }) {
  const [typed, setTyped] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setTyped(""); }, [project]);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api(`/api/projects/${project.id}`, { method: "DELETE", body: { confirm_name: typed.trim() } });
      toast(`${project.name} deleted.`);
      onDone(); onClose();
    } catch (err) { toast.error(err.message); } finally { setBusy(false); }
  };
  const matches = typed.trim().toLowerCase() === (project?.name || "").trim().toLowerCase();
  return (
    <Modal open={!!project} onClose={onClose} title={`Delete ${project?.name || "project"}?`}>
      <form onSubmit={submit} className="space-y-4">
        <p className="text-sm text-ink">Its pages come down and its campaigns are paused first. Then its pictures, videos, leads and replies are deleted. This can't be undone.</p>
        <Field label={`Type ${project?.name || ""} to confirm`}><input className="input" value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus autoComplete="off" /></Field>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-subtle" onClick={onClose}>Keep it</button>
          <Button type="submit" variant="danger" busy={busy} disabled={!matches}>Delete project</Button>
        </div>
      </form>
    </Modal>
  );
}

export default function Projects() {
  const [showArchived, setShowArchived] = useState(false);
  const open = useProjects(false);
  const archived = useProjects(true);
  const { list, loading, error, reload } = showArchived ? archived : open;
  const [renaming, setRenaming] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [creating, setCreating] = useState(false);
  useEffect(() => { document.title = "Projects · AIMVA"; return () => { document.title = "AIMVA"; }; }, []);
  const refresh = () => { open.reload(); archived.reload(); };

  const create = async () => {
    setCreating(true);
    try {
      await post("/api/projects", {});  // opens the new project; /start fills it in
      window.location.assign("/start?new=1");
    } catch (err) { toast.error(err.message); setCreating(false); }
  };
  const setArchived = async (p, on) => {
    try {
      await patch(`/api/projects/${p.id}`, { archived: on });
      refresh();
      toast(on ? `${p.name} archived.` : `${p.name} is back.`, on ? { action: { label: "Undo", onClick: () => setArchived(p, false) } } : undefined);
    } catch (err) { toast.error(err.message); }
  };

  return (
    <div>
      {/* The title lives in the app header; only the one action stays on the page. */}
      <PageHeader title={showArchived ? "Archived projects" : "Projects"}
        actions={!showArchived && <Button variant="accent" busy={creating} onClick={create}><Plus className="size-4" /> New project</Button>} />

      {error && !list.length ? <LoadError error={error} what="your projects" onRetry={reload} />
        : loading ? (
          <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3" aria-label="Loading">
            {[0, 1, 2].map((i) => <li key={i} className="aspect-[4/4.2] rounded-[10px] border border-line bg-surface-2/60" />)}
          </ul>
        ) : !list.length ? (
          <p className="text-sm text-muted">{showArchived ? "Nothing archived." : "No projects yet."}</p>
        ) : (
          <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {list.map((p) => <ProjectCard key={p.id} p={p} onRename={setRenaming} onArchive={setArchived} onDelete={setDeleting} />)}
          </ul>
        )}

      {(showArchived || archived.list.length > 0) && (
        <button type="button" className={cx("mt-8 text-sm font-medium text-brand hover:underline")} onClick={() => setShowArchived((v) => !v)}>
          {showArchived ? "Back to projects" : `Archived (${archived.list.length})`}
        </button>
      )}
      <RenameDialog project={renaming} onClose={() => setRenaming(null)} onDone={refresh} />
      <DeleteDialog project={deleting} onClose={() => setDeleting(null)} onDone={refresh} />
    </div>
  );
}
