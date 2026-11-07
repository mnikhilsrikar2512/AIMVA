import { Component, createContext, useContext, useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { ForYou } from "./ForYou";
import { Compass, LayoutDashboard, LogOut, Menu, Plus, Search, Users, X } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "./shadcn/dialog";
import { AnimatePresence, MotionConfig, motion } from "framer-motion";
import { ease } from "./Motion";
import { useAuth } from "../lib/auth";
import { visibleNav } from "../lib/modules";
import { CommandPalette } from "./CommandPalette";
import { WorkspaceSwitcher } from "./Team";
import { Celebrations } from "./Celebrate";
import { useWorkspaceGuards } from "../lib/workspaces";
import { cx } from "./ui";
import { useApi } from "../lib/hooks";
import { LiveProvider, useLeadEvents, useLive } from "../lib/live";

const OnboardingContext = createContext(null);
export const useOnboarding = () => useContext(OnboardingContext);

import { Logo } from "./Logo";
export { Logo };  // moved to its own file so public pages can use it without the app shell

/**
 * Navigation. On desktop it's a 72px icon rail that expands over the page while hovered (or focused with the
 * keyboard) and collapses again on leave, so the page underneath never moves. On phones it's a drawer.
 */
function Sidebar({ onNavigate, expanded = true }) {
  const { user, logout } = useAuth();
  const onboarding = useOnboarding();
  const { unseen, connected } = useLive();
  const navigate = useNavigate();
  const label = cx("whitespace-nowrap transition-opacity duration-200", expanded ? "opacity-100" : "pointer-events-none opacity-0");
  const { pathname } = useLocation();
  const status = onboarding?.data;
  // The dot on Home only while the path to the first lead is still open (it lives on Home, nowhere else).
  const setup = status && !status.dismissed && !status.steps?.find((s) => s.key === "lead")?.done;
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 shrink-0 items-center overflow-hidden px-5">
        <Link to="/" className="flex items-center gap-2.5" aria-label="AIMVA home">
          <img src="/favicon.svg" alt="" className="size-8 shrink-0" />
          <span className={cx("font-display text-lg font-bold tracking-tight text-strong", label)}>AIMVA</span>
        </Link>
      </div>
      <WorkspaceSwitcher expanded={expanded} />
      <div className="px-3 pb-1">
        <button type="button" onClick={() => { onNavigate?.(); window.dispatchEvent(new CustomEvent("aimva:palette")); }} title={expanded ? undefined : "Search (Ctrl/Cmd+K)"}
          className="flex h-9 w-full items-center gap-3 rounded-full px-3.5 text-sm text-muted transition-colors hover:bg-ink/[0.04] hover:text-strong">
          <Search className="size-[18px] shrink-0 text-faint" />
          <span className={cx("flex-1 text-left", label)}>Search</span>
          <kbd className={cx("hidden text-xs text-faint md:inline", label)}>⌘K</kbd>
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 pb-4 [scrollbar-width:none]">
        {visibleNav(user).map((g, gi) => (
          <div key={g.group} role="group" aria-label={g.group}>
            {gi > 0 && <span className="mx-3 my-1 block h-px bg-line" aria-hidden="true" />}
            {g.items.filter((it) => it.rail !== false).map((it) => (
              <NavLink
                key={it.to}
                to={it.to}
                end={it.end}
                onClick={onNavigate}
                title={expanded ? undefined : it.label}
                className={({ isActive: a }) => { const isActive = it.match ? pathname.startsWith(it.match) : a; return (
                  cx(
                    "group relative flex h-[clamp(28px,4.1vh,40px)] items-center gap-3 rounded-full px-3.5 text-sm font-medium transition-colors",
                    isActive ? "text-strong" : "text-muted hover:bg-ink/[0.04] hover:text-strong"
                  )); }
                }
              >
                {({ isActive: a }) => { const isActive = it.match ? pathname.startsWith(it.match) : a; return (
                  <>
                    {/* The highlight glides to the new section, so you see where you went. */}
                    {isActive && <motion.span layoutId={onNavigate ? "nav-active-mobile" : "nav-active"} className="absolute inset-0 rounded-full bg-surface shadow-[var(--shadow-soft)]"
                      transition={{ type: "spring", stiffness: 420, damping: 36 }} />}
                    <span className="relative shrink-0">
                      <it.icon className={cx("size-[18px] transition-colors", isActive ? "text-brand" : "text-faint group-hover:text-muted")} />
                      {it.to === "/app/leads" && unseen > 0 && !expanded && <span className="absolute -right-1 -top-1 size-2 rounded-full bg-rose-500 ring-2 ring-bg" />}
                      {it.to === "/app" && setup && !expanded && <span className="absolute -right-1 -top-1 size-2 rounded-full bg-brand ring-2 ring-bg" />}
                    </span>
                    <span className={cx("relative flex-1", label)}>{it.label}</span>
                    {it.to === "/app" && setup && expanded && (
                      <span className="relative rounded-full bg-lavender px-1.5 text-xs font-bold leading-5 text-brand" title="Setup guide progress">{status.completed}/{status.total}</span>
                    )}
                    {it.to === "/app/leads" && unseen > 0 && expanded && (
                      <span key={unseen} className="relative min-w-5 rounded-full bg-rose-500 px-1.5 text-center text-xs font-bold leading-5 text-white animate-[pop_400ms_cubic-bezier(.3,1.6,.5,1)]"
                        aria-label={`${unseen} new leads`}>{unseen > 99 ? "99+" : unseen}</span>
                    )}
                  </>
                ); }}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="shrink-0 p-3">
        <div className={cx("flex items-center gap-3 overflow-hidden rounded-2xl py-2 transition-colors", expanded ? "bg-surface px-2.5 shadow-[var(--shadow-soft)]" : "px-1.5")}>
          <div className="grid size-9 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand to-brand-2 text-sm font-bold text-white" title={expanded ? undefined : user?.name}>
            {user?.name?.[0]?.toUpperCase() || "?"}
          </div>
          <div className={cx("min-w-0 flex-1", label)}>
            <p className="truncate text-sm font-semibold text-strong">{user?.name}</p>
            <p className="flex items-center gap-1.5 truncate text-xs text-faint" title={connected ? "Live updates on" : "Reconnecting…"}>
              <span className={cx("inline-block size-1.5 shrink-0 rounded-full", connected ? "bg-emerald-400" : "bg-amber-400 animate-pulse")} />
              <span className="truncate">{user?.email}</span>
            </p>
          </div>
          <button
            className={cx("btn-subtle btn-sm shrink-0", label)}
            title="Sign out"
            aria-label="Sign out"
            tabIndex={expanded ? 0 : -1}
            onClick={async () => {
              await logout();
              navigate("/");
            }}
          >
            <LogOut className="size-4" />
          </button>
        </div>
      </div>
    </div>
  );
}

/** Desktop rail: expands on hover/focus after a short pause (so passing the mouse over it doesn't flash it open). */
function Rail() {
  const [expanded, setExpanded] = useState(false);
  const timer = useRef(null);
  const set = (v, delay) => { clearTimeout(timer.current); timer.current = setTimeout(() => setExpanded(v), delay); };
  useEffect(() => () => clearTimeout(timer.current), []);
  const location = useLocation();
  useEffect(() => { setExpanded(false); }, [location.pathname]);
  return (
    <aside
      onMouseEnter={() => set(true, 120)}
      onMouseLeave={() => set(false, 180)}
      onFocus={() => set(true, 0)}
      onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) set(false, 0); }}
      className={cx("fixed inset-y-0 left-0 z-40 hidden overflow-hidden bg-bg transition-[width,box-shadow] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] md:block",
        expanded ? "w-64 shadow-[0_0_0_1px_var(--color-line),0_24px_60px_-20px_rgb(20_18_31/0.35)]" : "w-[72px] shadow-[1px_0_0_var(--color-line)]")}
      aria-label="Main navigation"
    >
      <div className="h-full w-64"><Sidebar expanded={expanded} /></div>
    </aside>
  );
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
 * with everything you make or send; "More" opens the full navigation drawer (workspace, settings, sign out).
 */
const CREATE_GROUPS = ["Make", "Reach"];
function MobileTabBar({ onMore }) {
  const { user } = useAuth();
  const { unseen } = useLive();
  const { pathname } = useLocation();
  const [creating, setCreating] = useState(false);
  useEffect(() => { setCreating(false); }, [pathname]);
  const nav = visibleNav(user);
  const has = (to) => nav.some((g) => g.items.some((it) => it.to === to));
  const create = nav.filter((g) => CREATE_GROUPS.includes(g.group)).flatMap((g) => g.items.filter((it) => it.rail !== false));
  const createActive = create.some((it) => pathname.startsWith(it.match || it.to));
  const tab = "relative flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 pt-1.5 pb-1 text-[12px] font-medium leading-none transition-[color,transform] active:scale-95";
  const Item = ({ to, end, icon: Icon, label, badge }) => (
    <NavLink to={to} end={end} className={({ isActive }) => cx(tab, isActive ? "text-strong" : "text-faint")}>
      {({ isActive }) => (<>
        <span className="relative grid h-7 w-12 place-items-center">
          {isActive && <motion.span layoutId="tab-active" className="absolute inset-0 rounded-full bg-surface-2" transition={{ type: "spring", stiffness: 420, damping: 36 }} />}
          <Icon className={cx("relative size-[19px]", isActive && "text-brand")} strokeWidth={isActive ? 2.2 : 1.8} />
          {badge > 0 && <span className="absolute right-1.5 top-0 min-w-[18px] rounded-full bg-rose-500 px-1 text-center text-xs font-bold leading-[18px] text-white" aria-label={`${badge} new`}>{badge > 9 ? "9+" : badge}</span>}
        </span>
        <span className="truncate">{label}</span>
      </>)}
    </NavLink>
  );
  return (
    <>
      <nav aria-label="Main navigation" className="z-30 flex shrink-0 border-t border-line bg-bg/95 px-1 backdrop-blur-xl md:hidden"
        style={{ paddingBottom: "max(env(safe-area-inset-bottom), 4px)" }}>
        <Item to="/app" end icon={LayoutDashboard} label="Home" />
        {has("/app/leads") && <Item to="/app/leads" icon={Users} label="Leads" badge={unseen} />}
        {create.length > 0 && (
          <button type="button" onClick={() => setCreating(true)} className={cx(tab, createActive ? "text-strong" : "text-faint")} aria-haspopup="dialog">
            <span className="grid h-7 w-12 place-items-center"><span className="grid size-7 place-items-center rounded-full bg-strong text-white"><Plus className="size-4" strokeWidth={2.4} /></span></span>
            <span>Create</span>
          </button>
        )}
        {has("/app/command") && <Item to="/app/command" icon={Compass} label="Results" />}
        <button type="button" onClick={onMore} className={cx(tab, "text-faint")} aria-label="More: all sections, workspace and account">
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
                <Link to={it.to} onClick={() => setCreating(false)} className="flex items-center gap-3.5 rounded-xl px-3 py-2.5 active:bg-ink/[0.05]">
                  <it.icon className="size-5 shrink-0 text-faint" strokeWidth={1.8} />
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

function WorkspaceGuards() { useWorkspaceGuards(); return null; }

export default function AppLayout() {
  const [open, setOpen] = useState(false);
  const [focus, toggleFocus] = useFocusMode();
  const location = useLocation();
  const onboarding = useApi("/api/onboarding");
  const { reload: reloadOnboarding } = onboarding;
  useEffect(() => { setOpen(false); document.getElementById("app-scroll")?.scrollTo({ top: 0 }); }, [location.pathname]);
  // While inside the app the browser window itself never scrolls (no rubber-band, no sideways drift).
  useEffect(() => {
    document.documentElement.classList.add("app-locked");
    return () => document.documentElement.classList.remove("app-locked");
  }, []);
  // Re-check progress whenever the user moves between modules.
  useEffect(() => { reloadOnboarding(); }, [location.pathname, reloadOnboarding]);

  return (
    <MotionConfig reducedMotion="user">
    <LiveProvider>
    <OnboardingContext.Provider value={onboarding}>
    <OnboardingLiveRefresh reload={reloadOnboarding} />
    <WorkspaceGuards />
    <CommandPalette onToggleFocus={toggleFocus} />
    <Celebrations onboarding={onboarding.data} />
    {/* The frame is locked to the screen: sidebar and header never move; only the content panel scrolls. */}
    <div className="relative flex h-dvh overflow-hidden bg-bg">
      <div className={cx("aura pointer-events-none absolute inset-x-0 top-0 h-[420px] opacity-50", !focus && "md:left-[72px]")} aria-hidden />
      {!focus && <Rail />}
      {focus && (
        <button type="button" onClick={toggleFocus} className="fixed bottom-4 left-4 z-40 hidden h-8 items-center gap-2 rounded-full bg-surface px-3 text-xs font-medium text-muted shadow-[var(--shadow-lift)] transition hover:text-strong md:inline-flex">
          Exit focus <kbd className="text-faint">{"\\"}</kbd>
        </button>
      )}

      <AnimatePresence>
        {open && (
          <motion.div className="fixed inset-0 z-50 md:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <div className="absolute inset-0 bg-strong/25 backdrop-blur-sm" onClick={() => setOpen(false)} />
            <motion.aside className="absolute inset-y-0 left-0 w-[min(18rem,85vw)] bg-bg shadow-2xl" style={{ paddingBottom: "env(safe-area-inset-bottom)" }} initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }}
              transition={{ type: "spring", stiffness: 360, damping: 36 }}>
              <button className="btn-subtle btn-sm absolute right-3 top-4 z-10" onClick={() => setOpen(false)} aria-label="Close menu">
                <X className="size-4" />
              </button>
              <Sidebar onNavigate={() => setOpen(false)} />
            </motion.aside>
          </motion.div>
        )}
      </AnimatePresence>

      <div className={cx("relative flex min-w-0 flex-1 flex-col", !focus && "md:pl-[72px]")}>
        {/* Phones: slim top bar (logo, search, For you); navigation lives in the bottom tab bar. */}
        <header className="z-20 flex h-12 shrink-0 items-center gap-1 border-b border-line bg-bg/90 px-4 backdrop-blur-xl md:hidden">
          <Logo to="/app" />
          <button type="button" className="btn-subtle btn-sm ml-auto px-2" aria-label="Search" title="Search"
            onClick={() => window.dispatchEvent(new CustomEvent("aimva:palette"))}>
            <Search className="size-[18px]" />
          </button>
          <ForYou />
        </header>
        {/* Desktop: the For you bell sits top-right on every page. */}
        <div className={cx("absolute right-4 top-3 z-30 hidden rounded-lg bg-bg/85 backdrop-blur lg:right-5", focus ? "md:hidden" : "md:block")}><ForYou /></div>
        <div id="app-scroll" className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain [scrollbar-gutter:stable]">
          <main className={cx("relative mx-auto px-4 pt-5 pb-8 sm:px-6 sm:py-6 lg:px-10 lg:py-10", focus ? "max-w-[96rem]" : "max-w-6xl 2xl:max-w-7xl")}>
            <ModuleBoundary path={location.pathname}>
              <motion.div key={location.pathname} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease }}>
                <Outlet />
              </motion.div>
            </ModuleBoundary>
          </main>
        </div>
        <MobileTabBar onMore={() => setOpen(true)} />
      </div>
    </div>
      </OnboardingContext.Provider>
    </LiveProvider>
    </MotionConfig>
  );
}
