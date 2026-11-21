import { Component, createContext, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, matchPath, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { ForYou } from "./ForYou";
import { ArrowLeft, Compass, LayoutDashboard, LayoutGrid, LogOut, Menu, PanelLeftClose, PanelLeftOpen, Plus, Search, Settings, SquareStack, Users, X } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "./shadcn/dialog";
import { Sheet, SheetContent, SheetTitle } from "./shadcn/sheet";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "./shadcn/dropdown-menu";
import { Tooltip } from "./shadcn/tooltip";
import { MotionConfig } from "framer-motion";
import { useAuth } from "../lib/auth";
import { NAV, visibleNav } from "../lib/modules";
import { CommandPalette } from "./CommandPalette";
import { Celebrations } from "./Celebrate";
import { useProjectGuards, useProjects, MODULE_ROUTES } from "../lib/projects";
import { PageTitleContext, cx } from "./ui";
import { useApi } from "../lib/hooks";
import { recordOrigin, useGoToOrigin } from "../lib/nav";
import { LiveProvider, useLeadEvents, useLive } from "../lib/live";

const OnboardingContext = createContext(null);
export const useOnboarding = () => useContext(OnboardingContext);
const ProjectsContext = createContext({ list: [], active: null });
export const useProjectsContext = () => useContext(ProjectsContext);

import { Logo } from "./Logo";
import { StoryProvider } from "./Story";
export { Logo };  // moved to its own file so public pages can use it without the app shell

const ALL_ITEMS = NAV.flatMap((g) => g.items);
const byTo = (to) => ALL_ITEMS.find((it) => it.to === to);

/**
 * The rail's items (design.md 4.1). A project set up through /start shows its revealed modules in reveal order, a
 * hairline, then Leads and Results. Accounts from before /start keep today's rail in today's order.
 */
export function railGroups(user, project) {
  const nav = visibleNav(user);
  const allowed = new Set(nav.flatMap((g) => g.items.map((it) => it.to)));
  const revealed = (project?.modules || []).map((k) => byTo(MODULE_ROUTES[k])).filter((it) => it && allowed.has(it.to));
  if (!revealed.length) {
    return nav.map((g) => ({ group: g.group, items: g.items.filter((it) => it.rail !== false && it.to !== "/app/settings") })).filter((g) => g.items.length);
  }
  return [
    { group: "Home", items: [byTo("/app")] },
    { group: "Your modules", items: revealed },
    { group: "See", items: ["/app/leads", "/app/command"].map(byTo).filter((it) => allowed.has(it.to)) },
  ];
}

const RAIL_KEY = "aimva_rail_pinned";
function usePinned() {
  const [pinned, setPinned] = useState(() => { try { return localStorage.getItem(RAIL_KEY) === "1"; } catch { return false; } });
  useEffect(() => { try { localStorage.setItem(RAIL_KEY, pinned ? "1" : "0"); } catch { /* storage blocked */ } }, [pinned]);
  return [pinned, setPinned];
}

/**
 * A rail entry. Open rail: icon and label in a row. Narrow rail: icon with a small word under it (owner decision
 * 2026-11-21: phones and first-time owners can't rely on hover tooltips). `state.rail` marks a fresh start, so the
 * header shows no "back to" link after a rail click.
 */
function RailLink({ it, expanded, onNavigate, badge }) {
  const { pathname } = useLocation();
  // Active state is worked out here, not through NavLink's className function: the tooltip wrapper merges classes
  // as strings, which turned that function into text and left the marker unpositioned (a cyan line down the rail).
  const isActive = it.match ? pathname.startsWith(it.match) : !!matchPath({ path: it.to, end: !!it.end }, pathname);
  const link = (
    <Link to={it.to} state={{ rail: true }} onClick={onNavigate} aria-current={isActive ? "page" : undefined}
      className={cx("relative flex rounded-md font-medium",
        expanded ? "h-10 items-center gap-3 px-3.5 text-sm" : "flex-col items-center justify-center gap-1 px-0 py-2 text-[12px] leading-none tracking-[-0.01em]",
        isActive ? "bg-white/[0.06] text-bg" : "text-bg/70 hover:bg-white/[0.06] hover:text-bg")}>
      {/* Active: a still 3px cyan bar on the left edge (bright cyan is allowed on the dark rail only). */}
      {isActive && <span aria-hidden className={cx("absolute left-0 w-[3px] rounded-r bg-peach", expanded ? "top-2 bottom-2" : "top-3 bottom-3")} />}
      <span className="relative shrink-0">
        <it.icon className={cx("size-[18px]", isActive && "text-brand-on-dark")} />
        {badge > 0 && !expanded && <span className="absolute -right-1 -top-1 size-2 rounded-full bg-accent-on-dark ring-2 ring-strong" aria-hidden />}
      </span>
      <span className={expanded ? "flex-1 truncate" : "w-full truncate text-center"}>{expanded ? it.label : (it.short || it.label)}</span>
      {badge > 0 && expanded && <span className="min-w-5 rounded-full bg-accent-on-dark px-1.5 text-center text-xs font-bold leading-5 text-strong" aria-label={`${badge} new`}>{badge > 99 ? "99+" : badge}</span>}
      {badge > 0 && !expanded && <span className="sr-only">, {badge} new</span>}
    </Link>
  );
  return link;
}

function RailButton({ icon: Icon, label, expanded, onClick, pressed }) {
  const btn = (
    <button type="button" onClick={onClick} aria-label={expanded ? undefined : label} aria-pressed={pressed}
      className={cx("flex h-10 w-full items-center gap-3 rounded-md text-sm font-medium text-bg/70 hover:bg-white/[0.06] hover:text-bg", expanded ? "px-3.5" : "justify-center")}>
      <Icon className="size-[18px] shrink-0" />{expanded && <span className="flex-1 truncate text-left">{label}</span>}
    </button>
  );
  return expanded ? btn : <Tooltip content={label} side="right">{btn}</Tooltip>;
}

/**
 * Navigation on pine. Desktop: a 64px icon rail that a pin button opens to 240px with labels (remembered); it never
 * opens on hover. Phones: the same content in a drawer from the "More" tab.
 */
function Sidebar({ onNavigate, expanded = true, pinned, onPin }) {
  const { user } = useAuth();
  const { unseen } = useLive();
  const { list, active } = useProjectsContext();
  const groups = railGroups(user, active);
  return (
    <div className={cx("flex h-full flex-col bg-strong text-bg [&_:focus-visible]:outline-brand-on-dark", expanded ? "px-2" : "px-1")}>
      <div className={cx("flex h-14 shrink-0 items-center", expanded ? "px-2.5" : "justify-center")}>
        <Link to="/app" className="flex items-center gap-2.5" aria-label="AIMVA home" onClick={onNavigate}>
          <img src="/logo-on-dark.svg" alt="" className="size-7 shrink-0" />
          {expanded && <span className="font-display text-base font-bold tracking-tight text-bg">AIMVA</span>}
        </Link>
      </div>
      <nav className="flex-1 overflow-y-auto overflow-x-hidden pb-4 [scrollbar-width:none]" aria-label="Main navigation">
        {list.length >= 2 && (
          <div className="mb-1 border-b border-white/10 pb-1">
            <RailLink it={{ to: "/app/projects", label: "Projects", icon: SquareStack }} expanded={expanded} onNavigate={onNavigate} />
          </div>
        )}
        {groups.map((g, gi) => (
          <div key={g.group} role="group" aria-label={g.group}>
            {gi > 0 && <span className="mx-2 my-1 block h-px bg-white/10" aria-hidden="true" />}
            {g.items.map((it) => <RailLink key={it.to} it={it} expanded={expanded} onNavigate={onNavigate} badge={it.to === "/app/leads" ? unseen : 0} />)}
          </div>
        ))}
      </nav>
      <div className="shrink-0 space-y-0.5 border-t border-white/10 py-2">
        <RailButton icon={LayoutGrid} label="All tools (Ctrl/Cmd+K)" expanded={expanded} onClick={() => { onNavigate?.(); window.dispatchEvent(new CustomEvent("aimva:palette")); }} />
        <RailLink it={{ to: "/app/settings", label: "Settings", icon: Settings }} expanded={expanded} onNavigate={onNavigate} />
        {onPin && <RailButton icon={pinned ? PanelLeftClose : PanelLeftOpen} label={pinned ? "Collapse menu" : "Keep menu open"} expanded={expanded} pressed={pinned} onClick={onPin} />}
      </div>
    </div>
  );
}

function Rail({ pinned, setPinned }) {
  return (
    <aside className={cx("fixed inset-y-0 left-0 z-40 hidden md:block", pinned ? "w-60" : "w-20")} aria-label="Main navigation">
      <Sidebar expanded={pinned} pinned={pinned} onPin={() => setPinned(!pinned)} />
    </aside>
  );
}

/** Header right side: search, bell, account. The person's name and email live here, not in the rail. */
function AccountMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <DropdownMenu>
      <Tooltip content="Account">
        <DropdownMenuTrigger asChild>
          <button type="button" aria-label="Account" className="grid size-9 place-items-center rounded-md hover:bg-surface-2">
            <span className="grid size-7 place-items-center rounded-full bg-surface-2 text-xs font-semibold text-strong ring-1 ring-line">{user?.name?.[0]?.toUpperCase() || "?"}</span>
          </button>
        </DropdownMenuTrigger>
      </Tooltip>
      <DropdownMenuContent className="w-60">
        <DropdownMenuLabel>
          <span className="block truncate text-sm font-medium text-strong">{user?.name}</span>
          <span className="block truncate">{user?.email}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate("/app/settings")}><Settings /> Settings</DropdownMenuItem>
        <DropdownMenuItem onSelect={async () => { await logout(); navigate("/"); }}><LogOut /> Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Shown only when live updates have been down for a while, never as a decorative dot. */
function ConnectionBar() {
  const { connected } = useLive();
  const [down, setDown] = useState(false);
  useEffect(() => {
    if (connected) { setDown(false); return undefined; }
    const t = setTimeout(() => setDown(true), 10000);
    return () => clearTimeout(t);
  }, [connected]);
  if (!down) return null;
  return <p role="status" className="shrink-0 bg-warm-soft px-4 py-1.5 text-center text-xs text-warm">Live updates are reconnecting. New leads may take a moment to appear.</p>;
}

class ModuleBoundary extends Component {
  state = { error: null };
  static getDerivedStateFromError(error) {
    return { error };
  }
  componentDidUpdate(prev) {
    if (prev.path !== this.props.path && this.state.error) this.setState({ error: null });
  }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card card-pad text-center">
        <p className="font-semibold text-strong">This module hit an error.</p>
        <p className="mt-1 text-sm text-muted">{String(this.state.error.message || this.state.error)}</p>
        <button className="btn-ghost mt-4" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}

/**
 * Phones: a bottom tab bar within thumb reach. Home, Leads and Results are one tap; "Create" opens a short sheet
 * with everything you make or send; "More" opens the full navigation drawer. The active tab is still: no gliding pill.
 */
function MobileTabBar({ onMore }) {
  const { user } = useAuth();
  const { unseen } = useLive();
  const { active } = useProjectsContext();
  const { pathname } = useLocation();
  const [creating, setCreating] = useState(false);
  useEffect(() => { setCreating(false); }, [pathname]);
  const nav = visibleNav(user);
  const has = (to) => nav.some((g) => g.items.some((it) => it.to === to));
  const groups = railGroups(user, active);
  const create = groups.flatMap((g) => g.items).filter((it) => !["/app", "/app/leads", "/app/command"].includes(it.to));
  const createActive = create.some((it) => pathname.startsWith(it.match || it.to));
  const tab = "relative flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 pt-1.5 pb-1 text-[12px] font-medium leading-none";
  const Item = ({ to, end, icon: Icon, label, badge }) => (
    <NavLink to={to} end={end} state={{ rail: true }} className={({ isActive }) => cx(tab, isActive ? "text-strong" : "text-muted")}>
      {({ isActive }) => (<>
        <span className={cx("relative grid h-7 w-12 place-items-center rounded-full", isActive && "bg-lavender")}>
          <Icon className={cx("relative size-[19px]", isActive && "text-brand")} strokeWidth={isActive ? 2.2 : 1.8} />
          {badge > 0 && <span className="absolute right-1.5 top-0 min-w-[18px] rounded-full bg-accent px-1 text-center text-xs font-bold leading-[18px] text-accent-ink" aria-label={`${badge} new`}>{badge > 9 ? "9+" : badge}</span>}
        </span>
        <span className="truncate">{label}</span>
      </>)}
    </NavLink>
  );
  return (
    <>
      <nav aria-label="Main navigation" className="z-30 flex shrink-0 border-t border-line bg-bg px-1 md:hidden"
        style={{ paddingBottom: "max(env(safe-area-inset-bottom), 4px)" }}>
        <Item to="/app" end icon={LayoutDashboard} label="Home" />
        {has("/app/leads") && <Item to="/app/leads" icon={Users} label="Leads" badge={unseen} />}
        {create.length > 0 && (
          <button type="button" onClick={() => setCreating(true)} className={cx(tab, createActive ? "text-strong" : "text-muted")} aria-haspopup="dialog">
            <span className="grid h-7 w-12 place-items-center"><span className="grid size-7 place-items-center rounded-full bg-strong text-white"><Plus className="size-4" strokeWidth={2.4} /></span></span>
            <span>Create</span>
          </button>
        )}
        {has("/app/command") && <Item to="/app/command" icon={Compass} label="Results" />}
        <button type="button" onClick={onMore} className={cx(tab, "text-muted")} aria-label="More: all sections, projects and account">
          <span className="grid h-7 w-12 place-items-center"><Menu className="size-[19px]" strokeWidth={1.8} /></span>
          <span>More</span>
        </button>
      </nav>
      <Dialog open={creating} onOpenChange={setCreating}>
        <DialogContent aria-describedby={undefined} className="md:hidden">
          <div className="mx-auto mt-2 h-1 w-9 rounded-full bg-line-strong" aria-hidden="true" />
          <DialogTitle className="px-5 pt-3 pb-1 text-sm text-muted">Create or send</DialogTitle>
          <ul className="px-2 pb-3">
            {create.map((it) => (
              <li key={it.to}>
                <Link to={it.to} state={{ rail: true }} onClick={() => setCreating(false)} className="flex items-center gap-3.5 rounded-md px-3 py-2.5 active:bg-ink/[0.05]">
                  <it.icon className="size-5 shrink-0 text-muted" strokeWidth={1.8} />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[15px] font-medium text-strong">{it.label}</span>
                    {it.desc && <span className="block truncate text-xs text-muted">{it.desc}</span>}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </DialogContent>
      </Dialog>
    </>
  );
}

// Re-check onboarding progress when a lead arrives (the "first lead" step can complete live).
function OnboardingLiveRefresh({ reload }) {
  useLeadEvents(() => reload());
  return null;
}

const FOCUS_KEY = "aimva_focus_mode";
function useFocusMode() {
  const [on, setOn] = useState(() => { try { return localStorage.getItem(FOCUS_KEY) === "1"; } catch { return false; } });
  useEffect(() => {
    document.documentElement.classList.toggle("focus-mode", on);
    try { localStorage.setItem(FOCUS_KEY, on ? "1" : "0"); } catch { /* storage blocked */ }
    return () => document.documentElement.classList.remove("focus-mode");
  }, [on]);
  useEffect(() => {
    const onKey = (e) => {
      const t = e.target;
      if (e.key !== "\\" || e.metaKey || e.ctrlKey || e.altKey || t.isContentEditable || /INPUT|TEXTAREA|SELECT/.test(t.tagName)) return;
      if (document.querySelector("[role=dialog]")) return;
      e.preventDefault(); setOn((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return [on, () => setOn((v) => !v)];
}

function ProjectGuards() { useProjectGuards(); return null; }

/** The section a path belongs to, for the header when a page doesn't name itself. */
function sectionTitle(pathname) {
  if (pathname === "/app/projects") return "Projects";
  const hit = ALL_ITEMS.filter((it) => it.to !== "/app" && pathname.startsWith(it.match || it.to)).sort((a, b) => b.to.length - a.to.length)[0];
  return hit ? hit.label : pathname === "/app" || pathname === "/app/" ? "Home" : "";
}

/**
 * Where you came from and where the scroll was (plan S7, 2026-11-21). Opening another screen from a link (not the
 * rail) remembers the screen you were on, so the header can offer "← Home". Back restores the list's scroll position;
 * a new screen starts at the top; a step inside the same screen (a tab, a filter, an open item) keeps the scroll.
 */
const SCROLL_KEY = "aimva_scroll";
function useNavMemory() {
  const location = useLocation();
  const navType = useNavigationType();
  const prev = useRef(null);
  const prevIdx = useRef(null);
  const [origin, setOrigin] = useState(null);
  useLayoutEffect(() => {
    const el = document.getElementById("app-scroll");
    const p = prev.current;
    let saved = {};
    try { saved = JSON.parse(sessionStorage.getItem(SCROLL_KEY) || "{}"); } catch { /* storage blocked */ }
    if (p && el) { saved[p.key] = el.scrollTop; try { sessionStorage.setItem(SCROLL_KEY, JSON.stringify(saved)); } catch { /* storage blocked */ } }
    setOrigin(recordOrigin({ prev: p, prevIdx: prevIdx.current, location, navType, sectionOf: sectionTitle, labelOf: (path) => sectionTitle(path) || "Back" }));
    if (el && p && p.pathname !== location.pathname) {
      const to = navType === "POP" ? saved[location.key] || 0 : 0;
      el.scrollTo({ top: to });
      if (to) {  // lists load after the screen: keep trying for a moment until they are tall enough
        let n = 0;
        const again = () => { if (el.scrollTop < to - 2 && n++ < 20) { el.scrollTo({ top: to }); setTimeout(again, 50); } };
        setTimeout(again, 50);
      }
    }
    prev.current = location;
    prevIdx.current = window.history.state?.idx ?? null;
  }, [location, navType]);
  return origin;
}

/** "← Home": back to exactly where you came from, scroll and open item included. Hidden after a rail click. */
function BackTo({ origin, className }) {
  const go = useGoToOrigin();
  if (!origin) return null;
  return (
    <button type="button" onClick={() => go(origin)} className={cx("inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-1 text-sm font-medium text-muted hover:bg-surface-2 hover:text-strong", className)}>
      <ArrowLeft className="size-4" /> {origin.label}
    </button>
  );
}

/** "Dr. Rao's Dental / Leads": which business, then which page. The only title on the page (design.md v3 section 4). */
function HeaderTitle({ title }) {
  const { list, active } = useProjectsContext();
  const { pathname } = useLocation();
  const page = title || sectionTitle(pathname);
  const showProject = active && list.length >= 2 && pathname !== "/app/projects";
  return (
    <h1 className="flex min-w-0 items-baseline gap-2 text-[20px] font-semibold leading-none text-strong">
      {showProject && <><Link to="/app/projects" className="truncate text-muted hover:text-strong" title="All projects">{active.name}</Link><span className="text-line-strong" aria-hidden>/</span></>}
      <span className="truncate">{page}</span>
    </h1>
  );
}

export default function AppLayout() {
  const [open, setOpen] = useState(false);
  const [focus, toggleFocus] = useFocusMode();
  const [pinned, setPinned] = usePinned();
  const location = useLocation();
  const onboarding = useApi("/api/onboarding");
  const projects = useProjects();
  const { reload: reloadOnboarding } = onboarding;
  useEffect(() => { setOpen(false); }, [location.pathname]);
  const origin = useNavMemory();
  // While inside the app the browser window itself never scrolls (no rubber-band, no sideways drift).
  useEffect(() => {
    document.documentElement.classList.add("app-locked");
    return () => document.documentElement.classList.remove("app-locked");
  }, []);
  // Re-check progress whenever the user moves between modules.
  useEffect(() => { reloadOnboarding(); }, [location.pathname, reloadOnboarding]);
  const railW = focus ? "" : pinned ? "md:pl-60" : "md:pl-20";
  const [pageTitle, setPageTitle] = useState(null);

  return (
    <MotionConfig reducedMotion="always">
    <LiveProvider>
    <ProjectsContext.Provider value={{ list: projects.list, active: projects.active, reload: projects.reload, loading: projects.loading }}>
    <OnboardingContext.Provider value={onboarding}>
    <OnboardingLiveRefresh reload={reloadOnboarding} />
    <ProjectGuards />
    <CommandPalette onToggleFocus={toggleFocus} />
    <Celebrations onboarding={onboarding.data} />
    {/* The frame is locked to the screen: rail and header never move; only the content panel scrolls. */}
    <div className="relative flex h-dvh overflow-hidden bg-bg">
      {!focus && <Rail pinned={pinned} setPinned={setPinned} />}
      {focus && (
        <button type="button" onClick={toggleFocus} className="fixed bottom-4 left-4 z-40 hidden h-8 items-center gap-2 rounded-full bg-surface px-3 text-xs font-medium text-muted shadow-[var(--shadow-lift)] hover:text-strong md:inline-flex">
          Exit focus <kbd className="text-muted">{"\\"}</kbd>
        </button>
      )}

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" className="w-[min(18rem,85vw)] border-0 bg-strong md:hidden" style={{ paddingBottom: "env(safe-area-inset-bottom)" }}>
          <SheetTitle className="sr-only">Menu</SheetTitle>
          <Sidebar onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>

      <div className={cx("relative flex min-w-0 flex-1 flex-col", railW)}>
        {/* Phones: slim top bar (logo, search, bell); navigation lives in the bottom tab bar. */}
        <header className="z-20 flex h-12 shrink-0 items-center gap-2 border-b border-line bg-bg px-4 md:hidden">
          {origin ? <BackTo origin={origin} className="-ml-1.5" /> : <img src="/logo.svg" alt="" className="size-7 shrink-0" />}
          <span className="min-w-0 truncate text-base font-semibold text-strong">{pageTitle || sectionTitle(location.pathname)}</span>
          <button type="button" className="btn-subtle btn-sm ml-auto px-2" aria-label="Search" title="Search"
            onClick={() => window.dispatchEvent(new CustomEvent("aimva:palette"))}>
            <Search className="size-[18px]" />
          </button>
          <ForYou />
        </header>
        {/* Desktop: 56px header, no border. Project name left; search, bell and account right. */}
        {!focus && (
          <header className="z-20 hidden h-14 shrink-0 items-center gap-2 border-b border-line px-8 md:flex">
            <BackTo origin={origin} className="-ml-2 mr-1" />
            <HeaderTitle title={pageTitle} />
            <div className="ml-auto flex items-center gap-1">
              <Tooltip content="Ask or search (Ctrl/Cmd+K)">
                <button type="button" className="grid size-9 place-items-center rounded-md text-muted hover:bg-surface-2 hover:text-strong" aria-label="Ask or search"
                  onClick={() => window.dispatchEvent(new CustomEvent("aimva:palette"))}><Search className="size-[18px]" /></button>
              </Tooltip>
              <ForYou />
              <AccountMenu />
            </div>
          </header>
        )}
        <ConnectionBar />
        <div id="app-scroll" className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain [scrollbar-gutter:stable]">
          <main className={cx("relative px-4 pt-5 pb-8 sm:px-6 sm:py-6 lg:px-8 lg:pb-12 lg:pt-8", focus && "mx-auto max-w-[96rem]")}>
            <PageTitleContext.Provider value={setPageTitle}>
            <StoryProvider>
              <ModuleBoundary path={location.pathname}>
                <Outlet />
              </ModuleBoundary>
            </StoryProvider>
            </PageTitleContext.Provider>
          </main>
        </div>
        <MobileTabBar onMore={() => setOpen(true)} />
      </div>
    </div>
      </OnboardingContext.Provider>
    </ProjectsContext.Provider>
    </LiveProvider>
    </MotionConfig>
  );
}
