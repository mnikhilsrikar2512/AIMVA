// Ctrl/Cmd+K: go anywhere, make anything, find a lead by name, switch client. The power-user way around the rail.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell, Building2, Compass, Eye, Keyboard, LogOut, Plus, Rocket, UserPlus, UserRound } from "lucide-react";
import { CommandDialog, CommandGroup, CommandItem } from "./shadcn/command";
import { AddClientDialog } from "./Team";
import { useAuth } from "../lib/auth";
import { get } from "../lib/api";
import { visibleNav } from "../lib/modules";
import { switchWorkspace, useWorkspaces } from "../lib/workspaces";


export function CommandPalette({ onToggleFocus }) {
  const [open, setOpen] = useState(false);
  const [leads, setLeads] = useState(null);
  const [adding, setAdding] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { list } = useWorkspaces();
  const isClient = user?.workspace?.role === "client";

  useEffect(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); setOpen((v) => !v); }
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("aimva:palette", onOpen);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("aimva:palette", onOpen); };
  }, []);
  // Leads are fetched when the palette opens, so typing a name finds them.
  useEffect(() => { if (open && !leads) get("/api/leads").then((l) => setLeads(l.slice(0, 200))).catch(() => setLeads([])); }, [open, leads]);

  const go = (to) => { setOpen(false); navigate(to); };
  const run = (fn) => { setOpen(false); setTimeout(fn, 50); };

  return (
    <>
      <CommandDialog open={open} onOpenChange={setOpen} placeholder="Go to, make, or find a lead…">
        {!isClient && (
          <CommandGroup heading="Make" value="make">
            <CommandItem value="launch from a link do it for me" onSelect={() => go("/app?launch=1")}><Rocket /> Launch from a link or a sentence</CommandItem>
            <CommandItem value="new page landing" onSelect={() => go("/app/websites")}><Plus /> New page</CommandItem>
            <CommandItem value="new picture image" onSelect={() => go("/app/images")}><Plus /> New picture</CommandItem>
            <CommandItem value="new video" onSelect={() => go("/app/videos")}><Plus /> New video</CommandItem>
            <CommandItem value="new campaign ad" onSelect={() => go("/app/ads/meta")}><Plus /> New campaign</CommandItem>
          </CommandGroup>
        )}
        <CommandGroup heading="Go to" value="go-to">
          {visibleNav(user).flatMap((g) => g.items).map((it) => (
            <CommandItem key={it.to} value={`${it.label} ${it.keywords || ""} ${it.desc || ""}`} onSelect={() => go(it.to)}>
              <it.icon /> <span className="flex-1">{it.label}</span>{it.desc && <span className="truncate text-xs text-muted">{it.desc}</span>}
            </CommandItem>
          ))}
        </CommandGroup>
        {leads?.length > 0 && (
          <CommandGroup heading="Leads" value="leads">
            {leads.map((l) => (
              <CommandItem key={l.id} value={`lead ${l.name || ""} ${l.email || ""} ${l.phone || ""}`} onSelect={() => go(`/app/leads?lead=${l.id}`)}>
                <UserRound /> <span className="flex-1 truncate">{l.name || l.email || l.phone}</span><span className="text-xs text-muted">{l.source}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        <CommandGroup heading="Workspace" value="workspace">
          {list.length > 1 && list.filter((w) => !w.active).map((w) => (
            <CommandItem key={w.id} value={`switch to ${w.own ? "my business own account" : w.name}`} onSelect={() => run(() => switchWorkspace(w.id, w.own ? "your own account" : w.name))}>
              <Building2 /> Switch to {w.own ? "my business" : w.name}
            </CommandItem>
          ))}
          {!isClient && <CommandItem value="add a client agency workspace" onSelect={() => run(() => setAdding(true))}><Plus /> Add a client</CommandItem>}
          {!isClient && <CommandItem value="invite someone team member colleague" onSelect={() => go("/app/settings?tab=team")}><UserPlus /> Invite someone</CommandItem>}
        </CommandGroup>
        <CommandGroup heading="View" value="view">
          <CommandItem value="next steps updates notifications bell" onSelect={() => run(() => window.dispatchEvent(new CustomEvent("aimva:foryou")))}><Bell /> <span className="flex-1">Next steps and updates</span><kbd className="text-xs text-muted">N</kbd></CommandItem>
          <CommandItem value="focus mode hide menu full width" onSelect={() => run(onToggleFocus)}><Eye /> <span className="flex-1">Focus mode</span><kbd className="text-xs text-muted">\</kbd></CommandItem>
          <CommandItem value="product tour how it works guide help" onSelect={() => go("/tour")}><Compass /> <span className="flex-1">Product tour</span></CommandItem>
          <CommandItem value="keyboard shortcuts help" onSelect={() => {}} className="cursor-default">
            <Keyboard /> <span className="flex-1 text-muted">Shortcuts</span>
            <span className="text-xs text-muted"><kbd>⌘K</kbd> this · <kbd>N</kbd> for you · <kbd>\</kbd> focus · <kbd>Esc</kbd> close</span>
          </CommandItem>
          <CommandItem value="sign out log out" onSelect={() => run(async () => { await logout(); navigate("/"); })}><LogOut /> Sign out</CommandItem>
        </CommandGroup>
      </CommandDialog>
      <AddClientDialog open={adding} onClose={() => setAdding(false)} />
    </>
  );
}

