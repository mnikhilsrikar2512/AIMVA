// Ctrl/Cmd+K: go anywhere, make anything, find a lead by name, jump to a project. Also "All tools" in the rail.
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowRight, Bell, Building2, Compass, Eye, Keyboard, LogOut, Plus, Rocket, SquareStack, UserPlus, UserRound } from "lucide-react";
import { CommandDialog, CommandGroup, CommandItem } from "./shadcn/command";
import { useAuth } from "../lib/auth";
import { get } from "../lib/api";
import { visibleNav } from "../lib/modules";
import { moduleHref, openProject, useProjects } from "../lib/projects";
import { post } from "../lib/api";


export function CommandPalette({ onToggleFocus }) {
  const [open, setOpen] = useState(false);
  const [leads, setLeads] = useState(null);
  const [search, setSearch] = useState("");
  useEffect(() => { if (!open) setSearch(""); }, [open]);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const { list } = useProjects();
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
  // The search doubles as the general prompt (design.md v3 7.1): a request opens the module it belongs to, with the
  // request as that module's prompt. It never says where or why; the page title shows it.
  const q = search.trim();
  const ask = () => run(async () => { const r = await post("/api/route", { text: q }); navigate(moduleHref(r.module, r.prompt)); });
  const askItem = q && !isClient && (
    <CommandGroup heading="Make it" value="make-it">
      <CommandItem value={`ask ${q}`} onSelect={ask}><ArrowRight /> <span className="flex-1 truncate">{q}</span></CommandItem>
    </CommandGroup>
  );
  const sentence = q.split(/\s+/).length >= 3;  // a request, not a name: offer it first so Enter runs it
  const run = (fn) => { setOpen(false); setTimeout(() => Promise.resolve().then(fn).catch((e) => toast.error(e.message)), 50); };

  return (
    <>
      <CommandDialog open={open} onOpenChange={setOpen} search={search} onSearch={setSearch} placeholder="Ask for something, go to a page, or find a lead…">
        {sentence && askItem}
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
        <CommandGroup heading="Projects" value="projects">
          {list.length > 1 && <CommandItem value="all projects window businesses" onSelect={() => go("/app/projects")}><SquareStack /> All projects</CommandItem>}
          {list.length > 1 && list.filter((p) => !p.active).map((p) => (
            <CommandItem key={p.id} value={`open project ${p.name}`} onSelect={() => run(() => openProject(p))}>
              <Building2 /> {p.name}
            </CommandItem>
          ))}
          <CommandItem value="new project business idea start" onSelect={() => run(async () => { await post("/api/projects", {}); window.location.assign("/start?new=1"); })}><Plus /> New project</CommandItem>
          {!isClient && <CommandItem value="invite someone team member colleague" onSelect={() => go("/app/settings?tab=team")}><UserPlus /> Invite someone</CommandItem>}
        </CommandGroup>
        {!sentence && askItem}
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
    </>
  );
}

